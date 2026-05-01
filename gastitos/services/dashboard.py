"""Helpers de calculo para la vista dashboard.

La vista dashboard() en views.py creció a ~180 líneas mezclando
queries, calculos financieros y armado del context. Esto extrae la
logica de negocio a funciones puras (o casi puras: las que tocan DB
reciben el user explicito) para que la vista quede como
controller-thin.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from ..models import Gasto, Vencimiento


MESES_NOMBRES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]


def gastos_mes_actual_qs(user):
    """Queryset de gastos del usuario en el mes calendario actual.

    Usa timezone.now() en lugar de datetime.now() — el modelo guarda
    DateTimeField timezone-aware (USE_TZ=True). Sin la conversion, la
    comparacion fecha__gte fallaba silenciosamente y retornaba 0.
    """
    mes_actual = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return Gasto.objects.filter(usuario=user, fecha__gte=mes_actual)


def total_mes_actual(user):
    """Suma de gastos del mes actual del usuario (Decimal)."""
    return gastos_mes_actual_qs(user).aggregate(
        Sum('monto')
    )['monto__sum'] or Decimal('0')


def calcular_gasto_por_finde(saldo_restante):
    """Cuanto puede gastar el usuario por fin de semana restante en el mes.

    Cuenta sabados y domingos restantes desde hoy hasta fin de mes. Si
    hay un sabado huerfano sin domingo (o viceversa) lo cuenta como 0.5.
    Si no quedan fines de semana, devuelve el saldo entero (1 fin de
    semana ficticio para evitar division por cero).
    """
    hoy = timezone.now().date()
    ultimo_dia_mes = (
        (hoy.replace(day=1) + timedelta(days=32)).replace(day=1)
        - timedelta(days=1)
    )
    dias_restantes = (ultimo_dia_mes - hoy).days

    sabados = 0
    domingos = 0
    for offset in range(dias_restantes + 1):
        dia = hoy + timedelta(days=offset)
        if dia.weekday() == 5:
            sabados += 1
        elif dia.weekday() == 6:
            domingos += 1

    fines_semana = min(sabados, domingos)
    if abs(sabados - domingos) > 0:
        fines_semana += 0.5
    if fines_semana == 0:
        fines_semana = 1

    if saldo_restante <= 0:
        return Decimal('0')
    return saldo_restante / Decimal(str(fines_semana))


def vencimientos_proximos(user, dias=3):
    """Vencimientos activos del usuario en los proximos N dias."""
    hoy = timezone.now().date()
    return Vencimiento.objects.filter(
        usuario=user,
        activo=True,
        fecha_vencimiento__gte=hoy,
        fecha_vencimiento__lte=hoy + timedelta(days=dias),
    ).order_by('fecha_vencimiento')


def datos_grafico_mensual(gastos_por_mes, salario_mensual):
    """Arrays para Chart.js: labels, totales, saldos.

    Convierte Decimal -> float porque Chart.js consume number arrays
    via JSON. La perdida de precision al pintar barras es irrelevante.
    """
    labels = []
    totales = []
    saldos = []
    for item in gastos_por_mes:
        labels.append(item['mes'].strftime('%B %Y'))
        totales.append(float(item['total'] or 0))
        saldos.append(float(salario_mensual - (item['total'] or Decimal('0'))))
    return labels, totales, saldos


def gastos_para_calendario(user):
    """Mapa 'YYYY-MM' -> list de gastos para el calendario interactivo.

    El campo monto se serializa como str(decimal) para preservar
    precision; el cliente lo parsea con parseFloat segun necesite.
    """
    out = {}
    for gasto in Gasto.objects.filter(usuario=user).order_by('fecha'):
        key = gasto.fecha.strftime('%Y-%m')
        out.setdefault(key, []).append({
            'fecha': gasto.fecha.isoformat(),
            'descripcion': gasto.descripcion,
            'monto': str(gasto.monto),
        })
    return out


def resumen_ultimos_meses(gastos_por_mes, salario_mensual, n=6):
    """Resumen de los ultimos N meses para la seccion 'Estadisticas'.

    Devuelve dict con:
    - historial_simple: lista de dicts con mes_nombre, total_gastos,
      saldo_restante y porcentaje_usado.
    - promedio_mensual: Decimal.
    - mes_mayor_gasto / mes_menor_gasto: nombre del mes (string).

    Si ningun mes tuvo gastos > 0, mes_menor devuelve 'N/A'. Decimal
    end-to-end (no convierte a float).
    """
    ultimos = gastos_por_mes[-n:] if len(gastos_por_mes) >= n else gastos_por_mes

    total_periodo = Decimal('0')
    mes_mayor = {'mes': '', 'total': Decimal('0')}
    # None como centinela "no se encontro mes con gasto > 0"; al final
    # se reemplaza por Decimal('0') si se queda asi.
    mes_menor = {'mes': '', 'total': None}
    historial = []

    for item in ultimos:
        total_gastos = item['total'] or Decimal('0')
        total_periodo += total_gastos
        saldo_restante_mes = salario_mensual - total_gastos
        if salario_mensual > 0:
            porcentaje = (total_gastos / salario_mensual) * Decimal('100')
        else:
            porcentaje = Decimal('0')

        mes_nombre = MESES_NOMBRES[item['mes'].month - 1]

        if total_gastos > mes_mayor['total']:
            mes_mayor = {'mes': mes_nombre, 'total': total_gastos}
        if total_gastos > 0 and (
            mes_menor['total'] is None or total_gastos < mes_menor['total']
        ):
            mes_menor = {'mes': mes_nombre, 'total': total_gastos}

        historial.append({
            'mes_nombre': mes_nombre,
            'total_gastos': total_gastos,
            'saldo_restante': saldo_restante_mes,
            'porcentaje_usado': min(porcentaje, Decimal('100')),
        })

    promedio = (
        total_periodo / len(ultimos) if ultimos else Decimal('0')
    )

    if mes_menor['total'] is None:
        mes_menor = {'mes': 'N/A', 'total': Decimal('0')}

    return {
        'historial_simple': historial,
        'promedio_mensual': promedio,
        'mes_mayor_gasto': mes_mayor['mes'],
        'mes_menor_gasto': mes_menor['mes'],
    }
