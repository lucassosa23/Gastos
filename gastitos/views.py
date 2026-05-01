from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from .forms import RegistroForm, BootstrapAuthenticationForm
from django.contrib import messages
from django.http import JsonResponse
from django.db import models, transaction
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator
from .models import Gasto, PerfilUsuario, GastoFijo, Vencimiento, MetaAhorro, GastoPlanificado
from .forms import GastoForm, PerfilUsuarioForm, SalarioForm, GastoFijoForm, VencimientoForm
from django import forms
from datetime import datetime

class GastoPlanificadoForm(forms.ModelForm):
    class Meta:
        model = GastoPlanificado
        fields = ['descripcion', 'monto', 'mes', 'anio']
        widgets = {
            'descripcion': forms.TextInput(attrs={'class': 'form-control'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'mes': forms.Select(attrs={'class': 'form-control'}),
            'anio': forms.NumberInput(attrs={'class': 'form-control', 'min': datetime.now().year})
        }
from .forms_ahorro import MetaAhorroForm, AgregarAhorroForm, EditarMetaForm
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import logging
from .utils import extraer_datos_imagen, procesar_historial_mercadopago
from .utils_estadisticas import guardar_estadisticas_mensuales, obtener_estadisticas_mensuales
from django.contrib.admin.views.decorators import staff_member_required

logger = logging.getLogger(__name__)

@login_required
def estadisticas_mensuales(request):
    """Vista para mostrar estadísticas mensuales guardadas"""
    estadisticas = obtener_estadisticas_mensuales(request.user)
    return render(request, 'gastitos/estadisticas_mensuales.html', {
        'estadisticas': estadisticas
    })

@staff_member_required
def ejecutar_limpieza_mensual(request):
    """Vista para ejecutar manualmente la limpieza de gastos mensuales"""
    if request.method == 'POST':
        estadisticas = guardar_estadisticas_mensuales()
        messages.success(request, 'Se han guardado las estadísticas y limpiado los gastos del mes anterior.')
        return redirect('estadisticas_mensuales')
    return render(request, 'gastitos/confirmar_limpieza.html')

from .utils_ahorro import (
    obtener_estadisticas_ahorro_usuario,
    calcular_recomendacion_ahorro_inteligente,
    verificar_metas_vencidas,
    generar_consejos_ahorro
)

@login_required
def planificacion_gastos(request):
    """Vista principal para la planificación de gastos del mes siguiente"""
    # Obtener mes y año siguiente
    fecha_actual = datetime.now()
    if fecha_actual.month == 12:
        mes_siguiente = 1
        año_siguiente = fecha_actual.year + 1
    else:
        mes_siguiente = fecha_actual.month + 1
        año_siguiente = fecha_actual.year
    
    # Obtener gastos planificados del usuario para el mes siguiente
    gastos_planificados = GastoPlanificado.objects.filter(
        usuario=request.user,
        mes=mes_siguiente,
        anio=año_siguiente
    ).order_by('descripcion')
    
    # Calcular total planificado
    total_planificado = gastos_planificados.aggregate(
        total=Sum('monto')
    )['total'] or Decimal('0')
    
    # Procesar el saldo personalizado y monto sobrante si se envía en el formulario
    saldo_personalizado = Decimal('0')
    monto_sobrante = Decimal('0')

    if request.method == 'POST':
        # Revertimos para tomar directamente los valores del formulario
        try:
            saldo_personalizado = Decimal(request.POST.get('saldo_personalizado', '0') or '0')
        except (ValueError, InvalidOperation):
            saldo_personalizado = Decimal('0')

        try:
            monto_sobrante = Decimal(request.POST.get('monto_sobrante', '0') or '0')
        except (ValueError, InvalidOperation):
            monto_sobrante = Decimal('0')
        # Permitimos valores negativos si la suma y planificación lo requieren

    else:
        if 'saldo_personalizado' in request.session:
            try:
                saldo_personalizado = Decimal(str(request.session['saldo_personalizado']))
            except (ValueError, InvalidOperation):
                saldo_personalizado = Decimal('0')
        if 'monto_sobrante' in request.session:
            try:
                monto_sobrante = Decimal(str(request.session['monto_sobrante']))
            except (ValueError, InvalidOperation):
                monto_sobrante = Decimal('0')

    # Guardar valores en la sesión
    request.session['saldo_personalizado'] = str(saldo_personalizado)
    request.session['monto_sobrante'] = str(monto_sobrante)

    # Calcular saldo total disponible (saldo + sobrante)
    saldo_total = saldo_personalizado + monto_sobrante

    # Calcular saldo estimado después de gastos planificados
    saldo_estimado = saldo_total - total_planificado
    
    # Obtener gastos fijos para sugerir planificación
    gastos_fijos = GastoFijo.objects.filter(
        usuario=request.user,
        activo=True
    )
    
    context = {
        'gastos_planificados': gastos_planificados,
        'total_planificado': total_planificado,
        'saldo_personalizado': saldo_personalizado,
        'monto_sobrante': monto_sobrante,
        'saldo_estimado': saldo_estimado,
        'gastos_fijos': gastos_fijos,
        'mes_siguiente': mes_siguiente,
        'año_siguiente': año_siguiente,
        'nombre_mes': GastoPlanificado.MESES_CHOICES[mes_siguiente-1][1]
    }
    
    return render(request, 'gastitos/planificacion_gastos.html', context)

@login_required
def agregar_gasto_planificado(request):
    """Vista para agregar un nuevo gasto planificado"""
    if request.method == 'POST':
        form = GastoPlanificadoForm(request.POST)
        if form.is_valid():
            gasto_planificado = form.save(commit=False)
            gasto_planificado.usuario = request.user
            gasto_planificado.save()
            
            messages.success(request, 'Gasto planificado agregado correctamente.')
            return redirect('planificacion_gastos')
    else:
        # Predeterminar mes y año siguiente
        fecha_actual = datetime.now()
        if fecha_actual.month == 12:
            mes_siguiente = 1
            año_siguiente = fecha_actual.year + 1
        else:
            mes_siguiente = fecha_actual.month + 1
            año_siguiente = fecha_actual.year
            
        form = GastoPlanificadoForm(initial={'mes': mes_siguiente, 'anio': año_siguiente})
    
    return render(request, 'gastitos/gasto_planificado_form.html', {'form': form})

@login_required
def editar_gasto_planificado(request, gasto_id):
    """Vista para editar un gasto planificado existente"""
    gasto_planificado = get_object_or_404(GastoPlanificado, id=gasto_id, usuario=request.user)
    
    if request.method == 'POST':
        form = GastoPlanificadoForm(request.POST, instance=gasto_planificado)
        if form.is_valid():
            form.save()
            messages.success(request, 'Gasto planificado actualizado correctamente.')
            return redirect('planificacion_gastos')
    else:
        form = GastoPlanificadoForm(instance=gasto_planificado)
    
    return render(request, 'gastitos/gasto_planificado_form.html', {
        'form': form,
        'gasto_planificado': gasto_planificado
    })

@login_required
def eliminar_gasto_planificado(request, gasto_id):
    """Vista para eliminar un gasto planificado"""
    gasto_planificado = get_object_or_404(GastoPlanificado, id=gasto_id, usuario=request.user)
    
    if request.method == 'POST':
        gasto_planificado.delete()
        messages.success(request, 'Gasto planificado eliminado correctamente.')
        return redirect('planificacion_gastos')
    
    return render(request, 'gastitos/confirmar_eliminar_gasto_planificado.html', {
        'gasto_planificado': gasto_planificado
    })

@login_required
def aplicar_gasto_planificado(request, gasto_id):
    """Vista para aplicar un gasto planificado como gasto real"""
    gasto_planificado = get_object_or_404(GastoPlanificado, id=gasto_id, usuario=request.user)
    
    if request.method == 'POST':
        gasto = gasto_planificado.aplicar_gasto()
        messages.success(request, f'Gasto "{gasto.descripcion}" aplicado correctamente.')
        return redirect('planificacion_gastos')
    
    return render(request, 'gastitos/confirmar_aplicar_gasto_planificado.html', {
        'gasto_planificado': gasto_planificado
    })

@login_required
def agregar_gasto_calendario(request):
    """Vista para agregar gastos desde el calendario."""
    if request.method != 'POST':
        return JsonResponse(
            {'success': False, 'error': 'Método no permitido'},
            status=405,
        )

    # Parseo y validacion de input fuera del lock: si los datos son
    # invalidos no necesitamos tomar el lock del perfil.
    try:
        descripcion = request.POST.get('descripcion')
        monto = Decimal(str(request.POST.get('monto')))
        fecha = datetime.strptime(
            request.POST.get('fecha_seleccionada'), '%Y-%m-%d'
        ).date()
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Datos inválidos'},
            status=400,
        )

    # Lock + check + create en una unica transaccion para evitar que
    # dos requests concurrentes del mismo usuario superen su saldo.
    try:
        with transaction.atomic():
            perfil = (
                PerfilUsuario.objects
                .select_for_update()
                .get(user=request.user)
            )
            if monto > perfil.saldo_disponible:
                return JsonResponse({
                    'success': False,
                    'error': f'Saldo insuficiente. Disponible: ${perfil.saldo_disponible:.2f}',
                })
            gasto = Gasto.objects.create(
                usuario=request.user,
                descripcion=descripcion,
                monto=monto,
                fecha=fecha,
            )
    except PerfilUsuario.DoesNotExist:
        return JsonResponse(
            {'success': False, 'error': 'Perfil de usuario no encontrado'},
            status=404,
        )
    except Exception:
        logger.exception("agregar_gasto_calendario fallo")
        return JsonResponse(
            {'success': False, 'error': 'Error al procesar la solicitud'},
            status=500,
        )

    return JsonResponse({
        'success': True,
        'message': f'Gasto "{descripcion}" agregado correctamente',
        'gasto': {
            'id': gasto.id,
            'descripcion': gasto.descripcion,
            'monto': str(gasto.monto),
            'fecha': gasto.fecha.isoformat(),
        },
    })


@login_required
def modo_ahorro(request):
    """Vista principal del modo ahorro"""
    # Verificar metas vencidas
    verificar_metas_vencidas(request.user)
    
    # Obtener estadísticas y datos (se recalculan automáticamente)
    estadisticas = obtener_estadisticas_ahorro_usuario(request.user)
    consejos = generar_consejos_ahorro(request.user)
    
    # Obtener metas del usuario
    metas_activas = MetaAhorro.objects.filter(usuario=request.user, estado='activa').order_by('fecha_objetivo')
    metas_completadas = MetaAhorro.objects.filter(usuario=request.user, estado='completada').order_by('-fecha_creacion')[:5]
    
    context = {
        'estadisticas': estadisticas,
        'consejos': consejos,
        'metas_activas': metas_activas,
        'metas_completadas': metas_completadas,
        'form_nueva_meta': MetaAhorroForm(),
        'form_agregar_ahorro': AgregarAhorroForm()
    }
    
    return render(request, 'gastitos/modo_ahorro.html', context)


@login_required
def crear_meta_ahorro(request):
    """Vista para crear una nueva meta de ahorro"""
    if request.method == 'POST':
        form = MetaAhorroForm(request.POST)
        if form.is_valid():
            meta = form.save(commit=False)
            meta.usuario = request.user
            meta.save()
            
            messages.success(request, f'Meta "{meta.nombre}" creada exitosamente!')
            return redirect('modo_ahorro')
        else:
            messages.error(request, 'Error al crear la meta. Revisa los datos ingresados.')
    else:
        form = MetaAhorroForm()
    
    return render(request, 'gastitos/crear_meta.html', {'form': form})


@login_required
def detalle_meta(request, meta_id):
    """Vista de detalle de una meta específica"""
    meta = get_object_or_404(MetaAhorro, id=meta_id, usuario=request.user)
    recomendacion = calcular_recomendacion_ahorro_inteligente(meta, request.user)
    
    # Formulario para agregar ahorro
    form_agregar = AgregarAhorroForm()
    
    if request.method == 'POST':
        form_agregar = AgregarAhorroForm(request.POST)
        if form_agregar.is_valid():
            monto = form_agregar.cleaned_data['monto']
            descripcion = form_agregar.cleaned_data.get('descripcion', '')
            
            meta.agregar_ahorro(monto, descripcion)
            
            if meta.esta_completada:
                messages.success(request, f'¡Felicitaciones! Has completado tu meta "{meta.nombre}"!')
            else:
                messages.success(request, f'Ahorro de ${monto:,.0f} agregado exitosamente!')
            
            return redirect('detalle_meta', meta_id=meta.id)
    
    context = {
        'meta': meta,
        'recomendacion': recomendacion,
        'form_agregar': form_agregar
    }
    
    return render(request, 'gastitos/detalle_meta.html', context)


@login_required
def agregar_ahorro_rapido(request, meta_id):
    """Vista para agregar ahorro rápidamente desde el modo ahorro"""
    if request.method == 'POST':
        meta = get_object_or_404(MetaAhorro, id=meta_id, usuario=request.user, estado='activa')
        
        # Validación manual del monto
        try:
            monto = Decimal(request.POST.get('monto', '0'))
            
            if monto <= 0:
                messages.error(request, 'El monto debe ser mayor a 0')
            else:
                meta.agregar_ahorro(monto)
                
                if meta.esta_completada:
                    messages.success(request, f'¡Felicitaciones! Has completado tu meta "{meta.nombre}"!')
                else:
                    symbol = 'US$' if meta.moneda == 'USD' else '$'
                    messages.success(request, f'Ahorro de {symbol}{monto:,.0f} agregado exitosamente a "{meta.nombre}"!')
        except (ValueError, TypeError):
            messages.error(request, 'Error al agregar el ahorro. Verifica el monto ingresado.')
    
    return redirect('modo_ahorro')


@login_required
def editar_meta(request, meta_id):
    """Vista para editar una meta existente"""
    meta = get_object_or_404(MetaAhorro, id=meta_id, usuario=request.user)
    
    if request.method == 'POST':
        form = EditarMetaForm(request.POST, instance=meta)
        if form.is_valid():
            form.save()
            messages.success(request, f'Meta "{meta.nombre}" actualizada exitosamente!')
            return redirect('detalle_meta', meta_id=meta.id)
    else:
        form = EditarMetaForm(instance=meta)
    
    context = {
        'form': form,
        'meta': meta
    }
    
    return render(request, 'gastitos/editar_meta.html', context)


@login_required
def eliminar_meta(request, meta_id):
    """Vista para eliminar una meta"""
    meta = get_object_or_404(MetaAhorro, id=meta_id, usuario=request.user)
    
    if request.method == 'POST':
        nombre_meta = meta.nombre
        meta.delete()
        messages.success(request, f'Meta "{nombre_meta}" eliminada exitosamente.')
        return redirect('modo_ahorro')
    
    return render(request, 'gastitos/confirmar_eliminar_meta.html', {'meta': meta})


@login_required
def pausar_reactivar_meta(request, meta_id):
    """Vista para pausar o reactivar una meta"""
    meta = get_object_or_404(MetaAhorro, id=meta_id, usuario=request.user)
    
    if request.method == 'POST':
        if meta.estado == 'activa':
            meta.estado = 'pausada'
            messages.info(request, f'Meta "{meta.nombre}" pausada.')
        elif meta.estado == 'pausada':
            meta.estado = 'activa'
            messages.success(request, f'Meta "{meta.nombre}" reactivada.')
        
        meta.save()
        return redirect('detalle_meta', meta_id=meta.id)
    
    return redirect('modo_ahorro')



@login_required
def agregar_vencimiento(request):
    """Vista para agregar vencimientos desde el calendario"""
    if request.method == 'POST':
        try:
            descripcion = request.POST.get('descripcion')
            fecha_vencimiento_str = request.POST.get('fecha_vencimiento')
            activo = request.POST.get('activo') == 'true'
            
            fecha_vencimiento = datetime.strptime(fecha_vencimiento_str, '%Y-%m-%d').date()
            
            # Validar que la fecha no sea en el pasado
            if fecha_vencimiento < datetime.now().date():
                return JsonResponse({
                    'success': False,
                    'error': 'La fecha de vencimiento no puede ser en el pasado'
                })
            
            # Crear el vencimiento
            vencimiento = Vencimiento.objects.create(
                usuario=request.user,
                descripcion=descripcion,
                fecha_vencimiento=fecha_vencimiento,
                activo=activo
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Vencimiento "{descripcion}" agregado correctamente',
                'vencimiento': {
                    'id': vencimiento.id,
                    'descripcion': vencimiento.descripcion,
                    'fecha_vencimiento': vencimiento.fecha_vencimiento.strftime('%Y-%m-%d'),
                    'activo': vencimiento.activo
                }
            })
            
        except ValueError as e:
            return JsonResponse({
                'success': False,
                'error': 'Formato de fecha inválido'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error al crear el vencimiento: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
def index(request):
    if request.user.is_authenticated:
        perfil, created = PerfilUsuario.objects.get_or_create(user=request.user)
        
        if request.method == 'POST':
            # Manejar procesamiento de historial de MercadoPago
            if 'historial_submit' in request.POST:
                if 'historial_imagen' in request.FILES:
                    try:
                        imagen_historial = request.FILES['historial_imagen']
                        gastos_extraidos = procesar_historial_mercadopago(imagen_historial)
                        
                        gastos_agregados = 0
                        gastos_rechazados = 0
                        
                        for gasto_data in gastos_extraidos:
                            # Validar que el gasto no exceda el saldo disponible
                            if gasto_data['monto'] <= perfil.saldo_disponible:
                                try:
                                    gasto = Gasto(
                                        usuario=request.user,
                                        descripcion=gasto_data['descripcion'],
                                        monto=gasto_data['monto']
                                    )
                                    gasto.save()
                                    gastos_agregados += 1
                                except Exception as save_error:
                                    gastos_rechazados += 1
                            else:
                                gastos_rechazados += 1
                        
                        if gastos_agregados > 0:
                            messages.success(request, f'Se agregaron {gastos_agregados} gastos del historial.')
                        if gastos_rechazados > 0:
                            messages.warning(request, f'{gastos_rechazados} gastos fueron rechazados por saldo insuficiente.')
                        
                        # Respuesta JSON para AJAX
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.headers.get('Content-Type', '').startswith('multipart/form-data'):
                            response_data = {
                                'success': True,
                                'gastos_agregados': gastos_agregados,
                                'gastos_rechazados': gastos_rechazados,
                                'mensaje': f'Se procesaron {len(gastos_extraidos)} gastos. {gastos_agregados} agregados, {gastos_rechazados} rechazados por saldo insuficiente.'
                            }
                            return JsonResponse(response_data)
                        
                    except Exception as e:
                        messages.error(request, f'Error procesando historial: {str(e)}')
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.headers.get('Content-Type', '').startswith('multipart/form-data'):
                            return JsonResponse({
                                'success': False,
                                'error': f'Error procesando historial: {str(e)}'
                            })
                else:
                    messages.error(request, 'No se seleccionó ninguna imagen.')
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '') or request.headers.get('Content-Type', '').startswith('multipart/form-data'):
                        return JsonResponse({
                            'success': False,
                            'error': 'No se seleccionó ninguna imagen.'
                        })
                
                return redirect('index')
            
            # Manejar procesamiento de PDF de tarjeta de crédito
            elif 'tarjeta_credito_submit' in request.POST:
                if 'tarjeta_pdf' in request.FILES:
                    try:
                        from .utils import procesar_pdf_tarjeta_credito
                        
                        pdf_file = request.FILES['tarjeta_pdf']
                        resultado = procesar_pdf_tarjeta_credito(pdf_file)
                        
                        if resultado:
                            # Validar que el monto no exceda el saldo disponible
                            if resultado['monto'] <= perfil.saldo_disponible:
                                try:
                                    gasto = Gasto(
                                        usuario=request.user,
                                        descripcion=resultado['descripcion'],
                                        monto=resultado['monto']
                                    )
                                    gasto.save()
                                    
                                    messages.success(request, f'Estado de cuenta procesado. Total agregado: ${resultado["monto"]:.2f}')
                                    
                                    # Respuesta JSON para AJAX
                                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                        return JsonResponse({
                                            'success': True,
                                            'total_agregado': float(resultado['monto']),
                                            'descripcion': resultado['descripcion'],
                                            'mensaje': f'Estado de cuenta procesado exitosamente. Total: ${resultado["monto"]:.2f}'
                                        })
                                    
                                except Exception as save_error:
                                    messages.error(request, f'Error al guardar el gasto: {str(save_error)}')
                                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                        return JsonResponse({
                                            'success': False,
                                            'error': f'Error al guardar el gasto: {str(save_error)}'
                                        })
                            else:
                                messages.error(request, f'Saldo insuficiente. Total del estado de cuenta: ${resultado["monto"]:.2f}, Disponible: ${perfil.saldo_disponible:.2f}')
                                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                    return JsonResponse({
                                        'success': False,
                                        'error': f'Saldo insuficiente. Total: ${resultado["monto"]:.2f}, Disponible: ${perfil.saldo_disponible:.2f}'
                                    })
                        else:
                            messages.error(request, 'No se pudo extraer el total del PDF. Verifica que sea un estado de cuenta válido.')
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({
                                    'success': False,
                                    'error': 'No se pudo extraer el total del PDF. Verifica que sea un estado de cuenta válido.'
                                })
                        
                    except Exception as e:
                        messages.error(request, f'Error procesando PDF: {str(e)}')
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'error': f'Error procesando PDF: {str(e)}'
                            })
                else:
                    messages.error(request, 'No se seleccionó ningún archivo PDF.')
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': 'No se seleccionó ningún archivo PDF.'
                        })
                
                return redirect('index')
            
            # Manejar edición de saldo disponible
            elif 'edit_saldo_submit' in request.POST:
                try:
                    nuevo_saldo = Decimal(str(request.POST.get('nuevo_saldo')))
                    if nuevo_saldo < 0:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'error': 'El saldo no puede ser negativo.'
                            })
                        messages.error(request, 'El saldo no puede ser negativo.')
                        return redirect('index')
                    
                    # Calcular gastos del mes actual
                    now = datetime.now()
                    mes_actual = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    total_gastos_mes = perfil.user.gasto_set.filter(
                        fecha__gte=mes_actual
                    ).aggregate(total=Sum('monto'))['total'] or Decimal('0')
                    
                    # Establecer el saldo_base para que el saldo_disponible sea el deseado
                    # saldo_disponible = saldo_base - gastos_mes, entonces saldo_base = saldo_deseado + gastos_mes
                    perfil.saldo_base = nuevo_saldo + total_gastos_mes
                    perfil.save()
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': 'Saldo actualizado correctamente',
                            'nuevo_saldo': str(nuevo_saldo)
                        })
                    
                    messages.success(request, f'Saldo actualizado a ${nuevo_saldo:.2f}')
                    return redirect('index')
                    
                except (ValueError, TypeError) as e:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': 'Monto inválido. Por favor ingresa un número válido.'
                        })
                    messages.error(request, 'Monto inválido. Por favor ingresa un número válido.')
                    return redirect('index')
            
            # Manejar adición de gasto individual
            elif 'gasto_submit' in request.POST:
                gasto_form = GastoForm(request.POST)
                if gasto_form.is_valid():
                    gasto = gasto_form.save(commit=False)
                    gasto.usuario = request.user
                    
                    # Validar saldo suficiente
                    if gasto.monto > perfil.saldo_disponible:
                        messages.error(request, f'Saldo insuficiente. Disponible: ${perfil.saldo_disponible:.2f}')
                    else:
                        gasto.save()
                        messages.success(request, f'Gasto "{gasto.descripcion}" agregado. Saldo restante: ${perfil.saldo_disponible:.2f}')
                    
                    return redirect('index')
        
        # Inicializar formulario de gastos
        gasto_form = GastoForm()
        
        # Obtener gastos recientes del usuario con paginación
        gastos_list = Gasto.objects.filter(usuario=request.user).order_by('-fecha')
        
        # Implementar paginación - los gastos más recientes aparecen en la página 1
        page_number = request.GET.get('page', 1)
        paginator = Paginator(gastos_list, 10)  # 10 gastos por página
        gastos_recientes = paginator.get_page(page_number)
        
        # Mantener los primeros 5 para mostrar en el dashboard principal
        gastos_dashboard = gastos_list[:5]
        gastos = gastos_list
        
        # Calcular total de gastos del mes actual
        total_mes_actual = perfil.get_total_gastos_mes()
        
        context = {
            'perfil': perfil,
            'gastos': gastos,
            'gastos_recientes': gastos_recientes,
            'gastos_dashboard': gastos_dashboard,
            'gasto_form': gasto_form,
            'saldo': perfil.saldo_disponible,
            'salario_configurado': perfil.salario_mensual > 0,
            'total_gastos': gastos_list.count(),
            'total_mes_actual': total_mes_actual,
        }
    else:
        context = {
            'perfil': None,
            'gastos': [],
            'gastos_recientes': [],
            'gasto_form': None,
            'saldo': 0,
            'salario_configurado': False,
            'total_mes_actual': 0,
        }
    return render(request, 'gastos/index.html', context)

@login_required
def actualizar_salario(request):
    perfil, created = PerfilUsuario.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Manejar actualización de salario
        if 'salario_submit' in request.POST:
            form = SalarioForm(request.POST, instance=perfil)
            if form.is_valid():
                form.save()
                messages.success(request, 'Salario actualizado correctamente')
                return redirect('actualizar_salario')
        
        # Manejar adición de gasto
        elif 'gasto_submit' in request.POST:
            gasto_form = GastoForm(request.POST, request.FILES)
            if gasto_form.is_valid():
                gasto = gasto_form.save(commit=False)
                gasto.usuario = request.user
                
                # Si hay una imagen, extraer datos con OCR
                if gasto.imagen_comprobante:
                    try:
                        datos_ocr = extraer_datos_imagen(gasto.imagen_comprobante)
                        if datos_ocr:
                            # Si no se proporcionó monto, usar el del OCR
                            if not gasto.monto and datos_ocr.get('monto'):
                                gasto.monto = datos_ocr['monto']
                            
                            # Si se extrajo fecha, usar la del OCR
                            if datos_ocr.get('fecha'):
                                gasto.fecha = datos_ocr['fecha']
                            
                            messages.info(request, f'Datos extraídos de la imagen - Monto: ${datos_ocr.get("monto", "N/A")}, Fecha: {datos_ocr.get("fecha", "N/A")}')
                    except Exception as e:
                        messages.warning(request, f'No se pudieron extraer datos de la imagen: {str(e)}')
                
                # Validar saldo suficiente
                if gasto.monto > perfil.saldo_disponible:
                    messages.error(request, f'Saldo insuficiente. Disponible: ${perfil.saldo_disponible:.2f}')
                else:
                    gasto.save()
                    messages.success(request, f'Gasto "{gasto.descripcion}" agregado. Saldo restante: ${perfil.saldo_disponible:.2f}')
                
                return redirect('actualizar_salario')
    
    # Inicializar formularios
    form = SalarioForm(instance=perfil)
    gasto_form = GastoForm()
    
    # Obtener gastos recientes del usuario
    gastos_recientes = Gasto.objects.filter(usuario=request.user).order_by('-fecha')[:5]
    
    context = {
        'form': form,
        'gasto_form': gasto_form,
        'perfil': perfil,
        'gastos_recientes': gastos_recientes,
        'salario_configurado': perfil.salario_mensual > 0,
    }
    
    return render(request, 'gastos/actualizar_salario.html', context)

@login_required
def agregar_gasto(request):
    if request.method == 'POST':
        form = GastoForm(request.POST, request.FILES)
        if form.is_valid():
            gasto = form.save(commit=False)
            gasto.usuario = request.user

            # OCR fuera del lock: la lectura de imagen puede tardar y no
            # debe mantener bloqueada la fila del perfil.
            if gasto.imagen_comprobante:
                try:
                    datos_ocr = extraer_datos_imagen(gasto.imagen_comprobante)
                    if datos_ocr:
                        if not gasto.monto and datos_ocr.get('monto'):
                            gasto.monto = datos_ocr['monto']
                        if datos_ocr.get('fecha'):
                            gasto.fecha = datos_ocr['fecha']
                        messages.info(request, f'Datos extraídos de la imagen - Monto: ${datos_ocr.get("monto", "N/A")}, Fecha: {datos_ocr.get("fecha", "N/A")}')
                except Exception:
                    logger.exception("OCR de imagen fallo en agregar_gasto")
                    messages.warning(request, 'No se pudieron extraer datos de la imagen')

            # Lock + validacion de saldo + save en una unica transaccion.
            # select_for_update() serializa requests concurrentes del mismo
            # usuario para que no puedan consumir saldo en paralelo.
            try:
                with transaction.atomic():
                    perfil = (
                        PerfilUsuario.objects
                        .select_for_update()
                        .get(user=request.user)
                    )
                    if gasto.monto > perfil.saldo_disponible:
                        messages.error(request, f'Saldo insuficiente. Disponible: ${perfil.saldo_disponible:.2f}')
                        return redirect('index')
                    gasto.save()
            except PerfilUsuario.DoesNotExist:
                messages.error(request, 'Perfil de usuario no encontrado')
                return redirect('index')

            messages.success(request, 'Gasto agregado exitosamente')
            return redirect('index')
    else:
        form = GastoForm()

    return render(request, 'gastos/agregar_gasto.html', {'form': form})

@login_required
def eliminar_gasto(request, gasto_id):
    gasto = get_object_or_404(Gasto, id=gasto_id, usuario=request.user)
    if request.method == 'POST':
        gasto.delete()
        messages.success(request, 'Gasto eliminado correctamente')
    return redirect('index')

@login_required
def editar_gasto(request):
    if request.method == 'POST':
        gasto_id = request.POST.get('gasto_id')
        gasto = get_object_or_404(Gasto, id=gasto_id, usuario=request.user)
        
        # Obtener el perfil del usuario
        perfil = get_object_or_404(PerfilUsuario, user=request.user)
        
        # Obtener los nuevos valores
        nueva_descripcion = request.POST.get('descripcion')
        nuevo_monto = request.POST.get('monto')
        try:
            nuevo_monto = float(nuevo_monto)
            
            # Calcular la diferencia de monto
            diferencia_monto = nuevo_monto - float(gasto.monto)
            
            # Verificar si hay saldo suficiente para el incremento
            if diferencia_monto > 0 and diferencia_monto > perfil.saldo_disponible:
                return JsonResponse({
                    'success': False, 
                    'error': f'Saldo insuficiente para el incremento. Disponible: ${perfil.saldo_disponible:.2f}'
                })
            
            # Actualizar el gasto
            gasto.descripcion = nueva_descripcion
            gasto.monto = nuevo_monto
            gasto.save()
            
            return JsonResponse({
                'success': True, 
                'message': 'Gasto actualizado correctamente'
            })
            
        except ValueError:
            return JsonResponse({
                'success': False, 
                'error': 'Monto inválido'
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
def dashboard(request):
    perfil, created = PerfilUsuario.objects.get_or_create(user=request.user)
    

    
    # Verificar metas vencidas y obtener estadísticas de ahorro
    verificar_metas_vencidas(request.user)
    estadisticas_ahorro = obtener_estadisticas_ahorro_usuario(request.user)
    
    # Gastos por mes con detalles
    gastos_por_mes = Gasto.objects.filter(usuario=request.user).annotate(
        mes=TruncMonth('fecha')
    ).values('mes').annotate(
        total=Sum('monto')
    ).order_by('mes')
    
    # Gastos del mes actual
    from datetime import datetime
    mes_actual = datetime.now().replace(day=1)
    gastos_mes_actual = Gasto.objects.filter(
        usuario=request.user,
        fecha__gte=mes_actual
    )
    
    total_mes_actual = gastos_mes_actual.aggregate(Sum('monto'))['monto__sum'] or Decimal('0')
    
    # Saldo restante del mes
    saldo_restante = perfil.salario_mensual - total_mes_actual
    
    # Calcular cuánto puede gastar por fin de semana
    # Calculamos los fines de semana restantes en el mes actual
    hoy = datetime.now().date()
    ultimo_dia_mes = (hoy.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias_restantes = (ultimo_dia_mes - hoy).days
    
    # Contar cuántos fines de semana (pares de días) quedan en el mes
    # Un fin de semana es un par de días (sábado y domingo)
    fines_semana_restantes = 0
    dias_fin_semana = []
    
    for i in range(dias_restantes + 1):
        dia = hoy + timedelta(days=i)
        # 5 = sábado, 6 = domingo en la representación de weekday()
        if dia.weekday() >= 5:
            dias_fin_semana.append(dia.weekday())
    
    # Contar pares completos (sábado y domingo)
    sabados = dias_fin_semana.count(5)
    domingos = dias_fin_semana.count(6)
    fines_semana_restantes = min(sabados, domingos)
    
    # Si hay un sábado o domingo sin pareja, contarlo como medio fin de semana
    if abs(sabados - domingos) > 0:
        fines_semana_restantes += 0.5
    
    # Si no quedan fines de semana, asumimos al menos 1 para evitar división por cero
    if fines_semana_restantes == 0:
        fines_semana_restantes = 1
        
    gasto_por_finde = saldo_restante / Decimal(str(fines_semana_restantes)) if saldo_restante > 0 else 0
    
    # Verificar si se acerca al límite (200,000 pesos restantes)
    advertencia_limite = saldo_restante <= 200000 and saldo_restante > 0
    
    # Obtener vencimientos próximos (dentro de 3 días)
    vencimientos_proximos = Vencimiento.objects.filter(
        usuario=request.user,
        activo=True
    ).filter(
        fecha_vencimiento__gte=datetime.now().date(),
        fecha_vencimiento__lte=datetime.now().date() + timedelta(days=3)
    ).order_by('fecha_vencimiento')
    
    # Preparar datos para gráficos
    meses_labels = []
    totales_data = []
    saldos_data = []
    
    for item in gastos_por_mes:
        meses_labels.append(item['mes'].strftime('%B %Y'))
        totales_data.append(float(item['total'] or 0))
        saldos_data.append(float(perfil.salario_mensual - (item['total'] or Decimal('0'))))
    
    # Preparar datos para el calendario - organizar gastos por mes y día
    todos_los_gastos = Gasto.objects.filter(usuario=request.user).order_by('fecha')
    gastos_calendario = {}
    
    for gasto in todos_los_gastos:
        mes_key = gasto.fecha.strftime('%Y-%m')
        if mes_key not in gastos_calendario:
            gastos_calendario[mes_key] = []
        
        gastos_calendario[mes_key].append({
            'fecha': gasto.fecha.isoformat(),
            'descripcion': gasto.descripcion,
            'monto': str(gasto.monto)
        })
    
    # Crear historial simple para los últimos 6 meses
    historial_simple = []
    meses_nombres = [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ]
    
    # Obtener los últimos 6 meses de datos
    ultimos_6_meses = gastos_por_mes[-6:] if len(gastos_por_mes) >= 6 else gastos_por_mes
    
    total_gastos_periodo = 0
    mes_mayor_gasto = {'mes': '', 'total': 0}
    mes_menor_gasto = {'mes': '', 'total': float('inf')}
    
    for item in ultimos_6_meses:
        total_gastos = float(item['total'] or 0)
        total_gastos_periodo += total_gastos
        saldo_restante_mes = perfil.salario_mensual - Decimal(str(total_gastos))
        porcentaje_usado = (total_gastos / float(perfil.salario_mensual) * 100) if perfil.salario_mensual > 0 else 0
        
        mes_nombre = meses_nombres[item['mes'].month - 1]
        
        # Encontrar mes con mayor y menor gasto
        if total_gastos > mes_mayor_gasto['total']:
            mes_mayor_gasto = {'mes': mes_nombre, 'total': total_gastos}
        if total_gastos < mes_menor_gasto['total'] and total_gastos > 0:
            mes_menor_gasto = {'mes': mes_nombre, 'total': total_gastos}
        
        historial_simple.append({
            'mes_nombre': mes_nombre,
            'total_gastos': total_gastos,
            'saldo_restante': saldo_restante_mes,
            'porcentaje_usado': min(porcentaje_usado, 100)  # Limitar a 100%
        })
    
    # Calcular promedio mensual
    promedio_mensual = total_gastos_periodo / len(ultimos_6_meses) if ultimos_6_meses else 0
    
    # Si no hay datos suficientes, ajustar valores por defecto
    if mes_menor_gasto['total'] == float('inf'):
        mes_menor_gasto = {'mes': 'N/A', 'total': 0}
    
    context = {
        'gastos_mensuales': gastos_por_mes,
        'perfil': perfil,
        'total_mes_actual': total_mes_actual,
        'saldo_restante': saldo_restante,
        'gasto_por_finde': gasto_por_finde,
        'advertencia_limite': advertencia_limite,
        'vencimientos_proximos': vencimientos_proximos,
        'meses_labels': json.dumps(meses_labels),
        'totales_data': json.dumps(totales_data),
        'saldos_data': json.dumps(saldos_data),
        'gastos_recientes': gastos_mes_actual.order_by('-fecha')[:10],
        'gastos_json': gastos_calendario,
        'historial_simple': historial_simple,
        'promedio_mensual': promedio_mensual,
        'mes_mayor_gasto': mes_mayor_gasto['mes'],
        'mes_menor_gasto': mes_menor_gasto['mes'],

        'estadisticas_ahorro': estadisticas_ahorro,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def perfil(request):
    perfil_usuario, created = PerfilUsuario.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = PerfilUsuarioForm(request.POST, request.FILES, instance=perfil_usuario)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil actualizado correctamente')
            return redirect('perfil')
    else:
        form = PerfilUsuarioForm(instance=perfil_usuario)
    
    # Información financiera actualizada automáticamente
    gastos_mes_actual = perfil_usuario.get_gastos_mes_actual()
    total_gastos_mes = perfil_usuario.get_total_gastos_mes()
    
    context = {
        'form': form, 
        'perfil': perfil_usuario,
        'gastos_mes_actual': gastos_mes_actual,
        'total_gastos_mes': total_gastos_mes,
        'saldo_disponible': perfil_usuario.saldo_disponible,
    }
    
    return render(request, 'gastos/perfil.html', context)

def registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'¡Registro exitoso! Bienvenido {username}, ahora puedes iniciar sesión.')
            return redirect('login')
    else:
        form = RegistroForm()
    return render(request, 'registration/registro.html', {'form': form})

class CustomLoginView(LoginView):
    form_class = BootstrapAuthenticationForm
    template_name = 'registration/login.html'
    
    def form_valid(self, form):
        username = form.get_user().username
        messages.success(self.request, f'¡Bienvenido de vuelta, {username}! Has iniciado sesión correctamente.')
        return super().form_valid(form)

@login_required
def gastos_fijos(request):
    """Vista para gestionar gastos fijos"""
    gastos_fijos = GastoFijo.objects.filter(usuario=request.user, activo=True)
    
    if request.method == 'POST':
        if 'crear_gasto_fijo' in request.POST:
            form = GastoFijoForm(request.POST)
            if form.is_valid():
                gasto_fijo = form.save(commit=False)
                gasto_fijo.usuario = request.user
                gasto_fijo.save()
                return JsonResponse({'success': True, 'message': 'Gasto fijo creado'})
            else:
                return JsonResponse({'success': False, 'error': 'Error en el formulario', 'errors': form.errors})
        
        elif 'aplicar_gasto_fijo' in request.POST:
            gasto_fijo_id = request.POST.get('aplicar_gasto_fijo')
            gasto_fijo = get_object_or_404(GastoFijo, id=gasto_fijo_id, usuario=request.user)
            
            # Verificar saldo suficiente
            perfil = PerfilUsuario.objects.get(user=request.user)
            if gasto_fijo.monto > perfil.saldo_disponible:
                return JsonResponse({
                    'success': False, 
                    'error': f'Saldo insuficiente. Disponible: ${perfil.saldo_disponible:.2f}'
                })
            
            # Aplicar el gasto fijo
            gasto = gasto_fijo.aplicar_gasto()
            return JsonResponse({
                'success': True, 
                'message': f'Gasto "{gasto.descripcion}" aplicado correctamente'
            })
        
        elif 'eliminar_gasto_fijo' in request.POST:
            gasto_fijo_id = request.POST.get('eliminar_gasto_fijo')
            gasto_fijo = get_object_or_404(GastoFijo, id=gasto_fijo_id, usuario=request.user)
            gasto_fijo.delete()
            return JsonResponse({'success': True, 'message': 'Gasto fijo eliminado'})
        
        elif 'editar_gasto_fijo_id' in request.POST:
            gasto_fijo_id = request.POST.get('editar_gasto_fijo_id')
            descripcion = request.POST.get('descripcion')
            monto = request.POST.get('monto')
            
            gasto_fijo = get_object_or_404(GastoFijo, id=gasto_fijo_id, usuario=request.user)
            gasto_fijo.descripcion = descripcion
            gasto_fijo.monto = monto
            gasto_fijo.save()
            
            return JsonResponse({'success': True, 'message': 'Gasto fijo actualizado correctamente'})
    
    # Manejar peticiones GET
    if request.GET.get('get_form'):
        form = GastoFijoForm()
        return render(request, 'gastos/gasto_fijo_form.html', {'form': form})
    
    if request.GET.get('get_list'):
        return JsonResponse({
            'gastos_fijos': [{
                'id': gf.id,
                'descripcion': gf.descripcion,
                'monto': float(gf.monto),
            } for gf in gastos_fijos]
        })
    
    # Respuesta por defecto
    form = GastoFijoForm()
    return JsonResponse({
        'gastos_fijos': [{
            'id': gf.id,
            'descripcion': gf.descripcion,
            'monto': float(gf.monto)
        } for gf in gastos_fijos]
    })

