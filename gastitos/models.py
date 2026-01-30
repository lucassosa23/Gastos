from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from datetime import datetime
from django.db.models import Sum
from decimal import Decimal
import calendar

class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    foto = models.ImageField(upload_to='perfiles/', blank=True, null=True)
    telefono = models.CharField(max_length=15, blank=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    profesion = models.CharField(max_length=100, blank=True)
    salario_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    saldo_base = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Saldo base personalizado establecido por el usuario")
    
    def __str__(self):
        return f"Perfil de {self.user.username}"
    
    @property
    def saldo_disponible(self):
        # Calcular gastos del mes actual
        now = datetime.now()
        mes_actual = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        total_gastos_mes = self.user.gasto_set.filter(
            fecha__gte=mes_actual
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0')
        
        # Si hay un saldo_base establecido, usarlo como base; sino usar salario_mensual
        base = self.saldo_base if self.saldo_base is not None else self.salario_mensual
        
        # Devolver el saldo disponible (base - gastos del mes)
        return base - total_gastos_mes
    
    def get_gastos_mes_actual(self):
        """Obtiene los gastos del mes actual"""
        now = datetime.now()
        mes_actual = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        return self.user.gasto_set.filter(
            fecha__gte=mes_actual
        )
    
    def get_total_gastos_mes(self):
        """Obtiene el total de gastos del mes actual"""
        return self.get_gastos_mes_actual().aggregate(
            total=Sum('monto')
        )['total'] or Decimal('0')

class Gasto(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    descripcion = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    fecha = models.DateTimeField(auto_now_add=True)
    imagen_comprobante = models.ImageField(upload_to='comprobantes/', blank=True, null=True)
    
    class Meta:
        ordering = ['-fecha']
    
    def __str__(self):
        return f"{self.descripcion} - ${self.monto}"
        
    def save(self, *args, **kwargs):
        # Simplificar la descripción eliminando prefijos no deseados
        import re
        
        # Casos específicos como "oo Golonor Sa" o "og Cafemocasrl017"
        if re.match(r'^[a-zA-Z]{2}\s+', self.descripcion):
            descripcion_simplificada = re.sub(r'^[a-zA-Z]{2}\s+', '', self.descripcion)
        # Otros casos con números o caracteres especiales al inicio
        else:
            descripcion_simplificada = re.sub(r'^[\d\s\-:\.]+\s*', '', self.descripcion)
        
        # Si aún hay contenido después de la simplificación, actualiza la descripción
        if descripcion_simplificada.strip():
            self.descripcion = descripcion_simplificada.strip()
            
        super().save(*args, **kwargs)

class GastoFijo(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    descripcion = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['descripcion']
    
    def __str__(self):
        return f"{self.descripcion} - ${self.monto} (Fijo)"
    
    def aplicar_gasto(self):
        """Crea un gasto regular a partir de este gasto fijo"""
        return Gasto.objects.create(
            usuario=self.usuario,
            descripcion=self.descripcion,
            monto=self.monto
        )
            
class GastoPlanificado(models.Model):
    MESES_CHOICES = [
        (1, 'Enero'),
        (2, 'Febrero'),
        (3, 'Marzo'),
        (4, 'Abril'),
        (5, 'Mayo'),
        (6, 'Junio'),
        (7, 'Julio'),
        (8, 'Agosto'),
        (9, 'Septiembre'),
        (10, 'Octubre'),
        (11, 'Noviembre'),
        (12, 'Diciembre'),
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    descripcion = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    mes = models.IntegerField(choices=MESES_CHOICES)
    anio = models.IntegerField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    completado = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['anio', 'mes', 'descripcion']
        verbose_name = 'Gasto Planificado'
        verbose_name_plural = 'Gastos Planificados'
    
    def __str__(self):
        return f"{self.descripcion} - ${self.monto} ({self.get_mes_display()} {self.anio})"
    
    def aplicar_gasto(self):
        """Crea un gasto regular a partir de este gasto planificado y lo marca como completado"""
        gasto = Gasto.objects.create(
            usuario=self.usuario,
            descripcion=self.descripcion,
            monto=self.monto
        )
        self.completado = True
        self.save()
        return gasto

class Vencimiento(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    descripcion = models.CharField(max_length=200, help_text="Descripción del vencimiento (ej: Pago de tarjeta, Renovación de seguro)")
    fecha_vencimiento = models.DateField(help_text="Fecha en que vence")
    activo = models.BooleanField(default=True, help_text="Si está activo, se mostrarán las advertencias")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['fecha_vencimiento']
        verbose_name = 'Vencimiento'
        verbose_name_plural = 'Vencimientos'
    
    def __str__(self):
        return f"{self.descripcion} - {self.fecha_vencimiento.strftime('%d/%m/%Y')}"
    
    @property
    def dias_restantes(self):
        """Calcula los días restantes hasta el vencimiento"""
        from datetime import date
        hoy = date.today()
        delta = self.fecha_vencimiento - hoy
        return delta.days
    
    @property
    def esta_proximo(self):
        """Verifica si el vencimiento está dentro de los próximos 3 días"""
        return 0 <= self.dias_restantes <= 3
    
    @property
    def esta_vencido(self):
        """Verifica si ya está vencido"""
        return self.dias_restantes < 0
        
class EstadisticaMensual(models.Model):
    """Modelo para almacenar estadísticas mensuales de gastos"""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    año = models.IntegerField()
    mes = models.IntegerField()  # 1-12
    total_gastos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('usuario', 'año', 'mes')
        ordering = ['-año', '-mes']
        
    def __str__(self):
        nombre_mes = calendar.month_name[self.mes]
        return f"{nombre_mes} {self.año} - ${self.total_gastos}"
        
    @classmethod
    def guardar_estadisticas_y_limpiar(cls, año=None, mes=None):
        """
        Guarda las estadísticas del mes especificado y elimina los gastos de ese mes.
        Si no se especifica año y mes, usa el mes anterior al actual.
        """
        from django.db import transaction
        
        # Si no se especifica año y mes, usar el mes anterior
        if año is None or mes is None:
            fecha_actual = datetime.now()
            # Si estamos en enero, el mes anterior es diciembre del año anterior
            if fecha_actual.month == 1:
                mes = 12
                año = fecha_actual.year - 1
            else:
                mes = fecha_actual.month - 1
                año = fecha_actual.year
        
        # Obtener el primer y último día del mes
        ultimo_dia = calendar.monthrange(año, mes)[1]
        inicio_mes = datetime(año, mes, 1, 0, 0, 0)
        fin_mes = datetime(año, mes, ultimo_dia, 23, 59, 59)
        
        # Procesar cada usuario
        for usuario in User.objects.all():
            with transaction.atomic():
                # Obtener todos los gastos del mes para este usuario
                gastos_mes = Gasto.objects.filter(
                    usuario=usuario,
                    fecha__gte=inicio_mes,
                    fecha__lte=fin_mes
                )
                
                # Calcular el total de gastos
                total = gastos_mes.aggregate(total=Sum('monto'))['total'] or Decimal('0')
                
                # Guardar la estadística mensual
                estadistica, created = cls.objects.update_or_create(
                    usuario=usuario,
                    año=año,
                    mes=mes,
                    defaults={'total_gastos': total}
                )
                
                # Eliminar los gastos del mes
                gastos_mes.delete()
                
        return True



class MetaAhorro(models.Model):
    """Modelo para metas de ahorro del usuario"""
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('completada', 'Completada'),
        ('pausada', 'Pausada'),
        ('cancelada', 'Cancelada'),
    ]
    
    ICONO_CHOICES = [
        ('piggy-bank', '🐷 Alcancía'),
        ('car', '🚗 Auto'),
        ('plane', '✈️ Viaje'),
        ('home', '🏠 Casa'),
        ('graduation-cap', '🎓 Educación'),
        ('ring', '💍 Boda'),
        ('baby', '👶 Bebé'),
        ('laptop', '💻 Tecnología'),
        ('bicycle', '🚲 Bicicleta'),
        ('camera', '📷 Cámara'),
        ('gamepad', '🎮 Videojuegos'),
        ('music', '🎵 Música'),
        ('gift', '🎁 Regalo'),
        ('heart', '❤️ Salud'),
        ('star', '⭐ Sueño'),
    ]
    
    COLOR_CHOICES = [
        ('primary', 'Azul'),
        ('success', 'Verde'),
        ('info', 'Celeste'),
        ('warning', 'Amarillo'),
        ('danger', 'Rojo'),
        ('secondary', 'Gris'),
        ('dark', 'Negro'),
        ('purple', 'Morado'),
        ('pink', 'Rosa'),
        ('orange', 'Naranja'),
    ]
    
    MONEDA_CHOICES = [
        ('ARS', 'Pesos Argentinos (ARS)'),
        ('USD', 'Dólares Estadounidenses (USD)'),
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=200, help_text="Nombre de la meta (ej: Viaje a Europa, Auto nuevo)")
    descripcion = models.TextField(blank=True, help_text="Descripción detallada de la meta")
    monto_objetivo = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(1)], help_text="Monto total a ahorrar")
    monto_ahorrado = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text="Monto ya ahorrado")
    fecha_objetivo = models.DateField(help_text="Fecha límite para alcanzar la meta")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activa')
    icono = models.CharField(max_length=50, choices=ICONO_CHOICES, default='piggy-bank', help_text="Ícono de la meta")
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default='primary', help_text="Color del tema (Bootstrap)")
    moneda = models.CharField(max_length=3, choices=MONEDA_CHOICES, default='ARS', help_text="Moneda del objetivo")
    
    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Meta de Ahorro'
        verbose_name_plural = 'Metas de Ahorro'
    
    def __str__(self):
        return f"{self.nombre} - ${self.monto_objetivo}"
    
    @property
    def porcentaje_completado(self):
        """Calcula el porcentaje de la meta completado"""
        if self.monto_objetivo > 0:
            from decimal import Decimal
            return min((self.monto_ahorrado / self.monto_objetivo) * Decimal('100'), Decimal('100'))
        return 0
    
    @property
    def monto_restante(self):
        """Calcula cuánto falta para completar la meta"""
        return max(self.monto_objetivo - self.monto_ahorrado, 0)
    
    @property
    def dias_restantes(self):
        """Calcula cuántos días quedan para la fecha objetivo"""
        from datetime import date
        if self.fecha_objetivo > date.today():
            return (self.fecha_objetivo - date.today()).days
        return 0
    
    @property
    def ahorro_mensual_recomendado(self):
        """Calcula cuánto se debe ahorrar por mes para alcanzar la meta"""
        if self.dias_restantes <= 0:
            return self.monto_restante
        
        from decimal import Decimal
        meses_restantes = max(Decimal(str(self.dias_restantes)) / Decimal('30.44'), Decimal('1'))  # 30.44 días promedio por mes
        return self.monto_restante / meses_restantes
    
    @property
    def ahorro_semanal_recomendado(self):
        """Calcula cuánto se debe ahorrar por semana para alcanzar la meta"""
        if self.dias_restantes <= 0:
            return self.monto_restante
        
        from decimal import Decimal
        semanas_restantes = max(Decimal(str(self.dias_restantes)) / Decimal('7'), Decimal('1'))
        return self.monto_restante / semanas_restantes
    
    @property
    def esta_completada(self):
        """Verifica si la meta está completada"""
        return self.monto_ahorrado >= self.monto_objetivo
    
    @property
    def esta_vencida(self):
        """Verifica si la meta está vencida"""
        from datetime import date
        return self.fecha_objetivo < date.today() and not self.esta_completada
    
    def agregar_ahorro(self, monto):
        """Agrega un monto al ahorro de la meta"""
        self.monto_ahorrado += monto
        if self.esta_completada and self.estado == 'activa':
            self.estado = 'completada'
        self.save()
    
    def calcular_progreso_tiempo(self):
        """Calcula el progreso basado en el tiempo transcurrido"""
        from datetime import date
        fecha_inicio = self.fecha_creacion.date()
        fecha_actual = date.today()
        
        if self.fecha_objetivo <= fecha_inicio:
            return 100
        
        dias_totales = (self.fecha_objetivo - fecha_inicio).days
        dias_transcurridos = (fecha_actual - fecha_inicio).days
        
        from decimal import Decimal
        return min((Decimal(str(dias_transcurridos)) / Decimal(str(dias_totales))) * Decimal('100'), Decimal('100')) if dias_totales > 0 else Decimal('100')