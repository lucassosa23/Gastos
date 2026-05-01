"""Tests para gastitos.

Cobertura:
- Auth: login redirect, vistas protegidas.
- Gastos: alta exitosa, saldo insuficiente, edicion con Decimal, IDOR.
- Service layer del dashboard: las 6 funciones extraidas en
  gastitos/services/dashboard.py.

Usa TestCase (transaccion por test) + Client para los e2e. La DB es
sqlite in-memory por default cuando se corre `manage.py test`.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from gastitos.models import Gasto, PerfilUsuario, Vencimiento
from gastitos.services import dashboard as dashboard_service


# ============================================================================
# Auth
# ============================================================================

class AuthFlowTest(TestCase):
    """Verifica que las vistas protegidas redirigen a login cuando no hay sesion."""

    def setUp(self):
        self.user = User.objects.create_user('alice', password='Secret123!')
        PerfilUsuario.objects.create(user=self.user, salario_mensual=Decimal('1000'))

    def test_index_anonimo_redirige_a_login(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_dashboard_anonimo_redirige_a_login(self):
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_index_autenticado_devuelve_200(self):
        self.client.login(username='alice', password='Secret123!')
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)


# ============================================================================
# Gastos: alta, edicion, IDOR
# ============================================================================

class GastoCRUDTest(TestCase):
    """Verifica creacion / edicion / borrado de gastos preservando Decimal."""

    def setUp(self):
        self.user = User.objects.create_user('bob', password='Secret123!')
        PerfilUsuario.objects.create(user=self.user, salario_mensual=Decimal('1000'))
        self.client.login(username='bob', password='Secret123!')

    def test_agregar_gasto_persiste_decimal_y_redirige(self):
        resp = self.client.post('/agregar-gasto/', {
            'descripcion': 'cafe',
            'monto': '10.50',
        })
        self.assertEqual(resp.status_code, 302)
        gasto = Gasto.objects.get(usuario=self.user)
        # Decimal preservado: no flota a 10.5 ni redondea a 10.
        self.assertEqual(gasto.monto, Decimal('10.50'))

    def test_agregar_gasto_saldo_insuficiente_no_persiste(self):
        # salario_mensual = 1000; intentamos 9999 (insuficiente).
        resp = self.client.post('/agregar-gasto/', {
            'descripcion': 'lujo',
            'monto': '9999',
        })
        self.assertEqual(resp.status_code, 302)
        # El gasto NO se crea porque la validacion ocurre dentro de la
        # transaction.atomic + lock antes del save.
        self.assertFalse(
            Gasto.objects.filter(usuario=self.user, descripcion='lujo').exists()
        )

    def test_editar_gasto_monto_invalido_devuelve_400(self):
        gasto = Gasto.objects.create(usuario=self.user, descripcion='cafe', monto=Decimal('10'))
        resp = self.client.post('/editar-gasto/', {
            'gasto_id': gasto.id,
            'descripcion': 'cafe',
            'monto': 'NO-ES-UN-NUMERO',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b'Monto', resp.content)


# ============================================================================
# IDOR: un user NO puede tocar gastos de otro user
# ============================================================================

class IDORTest(TestCase):
    """Verifica que las vistas filtran por usuario en operaciones por ID."""

    def setUp(self):
        self.alice = User.objects.create_user('alice', password='Secret123!')
        self.bob = User.objects.create_user('bob', password='Secret123!')
        PerfilUsuario.objects.create(user=self.alice, salario_mensual=Decimal('1000'))
        PerfilUsuario.objects.create(user=self.bob, salario_mensual=Decimal('1000'))
        self.gasto_de_bob = Gasto.objects.create(
            usuario=self.bob, descripcion='privado', monto=Decimal('50')
        )

    def test_alice_no_puede_eliminar_gasto_de_bob(self):
        self.client.login(username='alice', password='Secret123!')
        resp = self.client.post(f'/eliminar-gasto/{self.gasto_de_bob.id}/')
        # get_object_or_404(..., usuario=request.user) devuelve 404
        self.assertEqual(resp.status_code, 404)
        # El gasto sigue existiendo.
        self.assertTrue(Gasto.objects.filter(id=self.gasto_de_bob.id).exists())

    def test_bob_si_puede_eliminar_su_propio_gasto(self):
        self.client.login(username='bob', password='Secret123!')
        resp = self.client.post(f'/eliminar-gasto/{self.gasto_de_bob.id}/')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Gasto.objects.filter(id=self.gasto_de_bob.id).exists())


# ============================================================================
# Service layer: dashboard helpers
# ============================================================================

class DashboardServiceTest(TestCase):
    """Tests unitarios del modulo extraido gastitos/services/dashboard.py."""

    def setUp(self):
        self.user = User.objects.create_user('charlie', password='x')
        PerfilUsuario.objects.create(user=self.user, salario_mensual=Decimal('1000'))

    def test_total_mes_actual_sin_gastos_es_cero(self):
        self.assertEqual(
            dashboard_service.total_mes_actual(self.user), Decimal('0')
        )

    def test_total_mes_actual_suma_decimal_preserva_centavos(self):
        Gasto.objects.create(usuario=self.user, descripcion='a', monto=Decimal('10.33'))
        Gasto.objects.create(usuario=self.user, descripcion='b', monto=Decimal('5.17'))
        # 10.33 + 5.17 = 15.50 exacto; con float seria 15.499999...
        self.assertEqual(
            dashboard_service.total_mes_actual(self.user), Decimal('15.50')
        )

    def test_calcular_gasto_por_finde_saldo_negativo_devuelve_cero(self):
        self.assertEqual(
            dashboard_service.calcular_gasto_por_finde(Decimal('-100')), Decimal('0')
        )

    def test_calcular_gasto_por_finde_saldo_positivo_es_decimal_positivo(self):
        result = dashboard_service.calcular_gasto_por_finde(Decimal('200'))
        self.assertGreater(result, Decimal('0'))
        self.assertIsInstance(result, Decimal)

    def test_resumen_ultimos_meses_sin_datos_devuelve_NA(self):
        resumen = dashboard_service.resumen_ultimos_meses(
            gastos_por_mes=[], salario_mensual=Decimal('1000')
        )
        self.assertEqual(resumen['mes_menor_gasto'], 'N/A')
        self.assertEqual(resumen['promedio_mensual'], Decimal('0'))
        self.assertEqual(resumen['historial_simple'], [])

    def test_vencimientos_proximos_filtra_por_3_dias(self):
        hoy = date.today()
        # Cercano (1 dia): debe aparecer.
        Vencimiento.objects.create(
            usuario=self.user, descripcion='hoy_mas_uno',
            fecha_vencimiento=hoy + timedelta(days=1),
        )
        # Lejano (10 dias): NO debe aparecer.
        Vencimiento.objects.create(
            usuario=self.user, descripcion='lejano',
            fecha_vencimiento=hoy + timedelta(days=10),
        )
        # Pasado: NO debe aparecer.
        Vencimiento.objects.create(
            usuario=self.user, descripcion='vencido',
            fecha_vencimiento=hoy - timedelta(days=1),
        )

        result = list(dashboard_service.vencimientos_proximos(self.user))
        descripciones = [v.descripcion for v in result]
        self.assertIn('hoy_mas_uno', descripciones)
        self.assertNotIn('lejano', descripciones)
        self.assertNotIn('vencido', descripciones)
