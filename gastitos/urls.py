from django.urls import path
from . import views

urlpatterns = [
    path('estadisticas/mensuales/', views.estadisticas_mensuales, name='estadisticas_mensuales'),
    path('admin/limpieza-mensual/', views.ejecutar_limpieza_mensual, name='ejecutar_limpieza_mensual'),
    path('', views.index, name='index'),
    path('actualizar-salario/', views.actualizar_salario, name='actualizar_salario'),
    path('agregar-gasto/', views.agregar_gasto, name='agregar_gasto'),
    path('agregar_gasto_calendario/', views.agregar_gasto_calendario, name='agregar_gasto_calendario'),
    path('agregar_vencimiento/', views.agregar_vencimiento, name='agregar_vencimiento'),

    path('eliminar-gasto/<int:gasto_id>/', views.eliminar_gasto, name='eliminar_gasto'),
    path('editar-gasto/', views.editar_gasto, name='editar_gasto'),
    path('gastos-fijos/', views.gastos_fijos, name='gastos_fijos'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('perfil/', views.perfil, name='perfil'),
    path('registro/', views.registro, name='registro'),
    # URLs del modo ahorro
    path('modo-ahorro/', views.modo_ahorro, name='modo_ahorro'),
    path('crear-meta/', views.crear_meta_ahorro, name='crear_meta_ahorro'),
    path('meta/<int:meta_id>/', views.detalle_meta, name='detalle_meta'),
    path('meta/<int:meta_id>/agregar-ahorro/', views.agregar_ahorro_rapido, name='agregar_ahorro_rapido'),
    path('meta/<int:meta_id>/editar/', views.editar_meta, name='editar_meta'),
    path('meta/<int:meta_id>/eliminar/', views.eliminar_meta, name='eliminar_meta'),
    path('meta/<int:meta_id>/pausar-reactivar/', views.pausar_reactivar_meta, name='pausar_reactivar_meta'),
    
    # URLs para planificación de gastos
    path('planificacion/', views.planificacion_gastos, name='planificacion_gastos'),
    path('planificacion/agregar/', views.agregar_gasto_planificado, name='agregar_gasto_planificado'),
    path('planificacion/editar/<int:gasto_id>/', views.editar_gasto_planificado, name='editar_gasto_planificado'),
    path('planificacion/eliminar/<int:gasto_id>/', views.eliminar_gasto_planificado, name='eliminar_gasto_planificado'),
    path('planificacion/aplicar/<int:gasto_id>/', views.aplicar_gasto_planificado, name='aplicar_gasto_planificado'),
]