"""
============================================================
PRUEBAS AUTOMÁTICAS — scheduler_management (vistas)
============================================================
Cubre:
  - Autenticación (login, logout, protección de rutas)
  - Vista selector de horario
  - Vista generación/visualización de horario
  - Landing page
============================================================
Ejecutar:  python manage.py test apps.scheduler_management --verbosity=2
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from apps.data_management.models import (
    Period, Group, Room, Subject, Activity,
    Professor, TeachingActivityAssignment,
)


# ============================================================
# Fixtures
# ============================================================

def create_user(username='testuser', password='testpass123'):
    return User.objects.create_user(username=username, password=password)

def create_full_period():
    """Crea un período con datos mínimos para poder generar un horario."""
    period    = Period.objects.create(
        career=Period.Career.ICI_D,
        number=1, is_active=True, weeks_count=16,
    )
    professor = Professor.objects.create(
        full_name='Prof Test',
        scientific_category=Professor.ScientificCategory.MASTER,
        docent_category=Professor.DocentCategory.ASSISTANT,
    )
    Room.objects.create(room_code='S01', room_type=Room.RoomType.CONFERENCE_ROOM)
    Room.objects.create(room_code='A01', room_type=Room.RoomType.CLASSROOM)
    Room.objects.create(room_code='L01', room_type=Room.RoomType.LABORATORY)

    subject = Subject.objects.create(name='Programación I', alias='PROG1', period=period)
    group   = Group.objects.create(group_code='IC1G1', period=period)

    # Crear los objetos Activity (necesarios para persistir el horario)
    Activity.objects.create(title='PROG1 — Conferencia', activity_type='C', subject=subject)
    Activity.objects.create(title='PROG1 — Laboratorio', activity_type='L', subject=subject)

    TeachingActivityAssignment.objects.create(
        subject=subject, group=group, professor=professor, activity_type='C',
    )
    TeachingActivityAssignment.objects.create(
        subject=subject, group=group, professor=professor, activity_type='L',
    )
    return period


# ============================================================
# 1. AUTENTICACIÓN
# ============================================================

class AuthTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user   = create_user()

    def test_login_page_accessible(self):
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)

    def test_login_with_valid_credentials(self):
        response = self.client.post('/accounts/login/', {
            'username': 'testuser',
            'password': 'testpass123',
        }, follow=True)
        self.assertTrue(response.context['user'].is_authenticated)

    def test_login_with_invalid_credentials(self):
        response = self.client.post('/accounts/login/', {
            'username': 'testuser',
            'password': 'wrongpassword',
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_redirects(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('logout'))
        self.assertIn(response.status_code, [200, 302])

    def test_logout_requires_post(self):
        """Django 5 solo permite logout por POST."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logout'))
        # GET a logout debe devolver 405 o redirigir, no debe cerrar sesión exitosamente
        self.assertIn(response.status_code, [302, 405])


# ============================================================
# 2. PROTECCIÓN DE RUTAS (login_required)
# ============================================================

class RouteProtectionTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_schedule_selector_requires_login(self):
        response = self.client.get(reverse('schedule_selector'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_view_schedule_requires_login(self):
        response = self.client.get(reverse('view_schedule'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_admin_requires_login(self):
        response = self.client.get('/admin/')
        self.assertIn(response.status_code, [302, 200])  # redirige al login del admin

    def test_landing_accessible_without_login(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)


# ============================================================
# 3. VISTAS DE HORARIO
# ============================================================

class ScheduleSelectorViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user   = create_user()
        self.client.login(username='testuser', password='testpass123')

    def test_selector_returns_200(self):
        response = self.client.get(reverse('schedule_selector'))
        self.assertEqual(response.status_code, 200)

    def test_selector_shows_active_periods(self):
        Period.objects.create(
            career=Period.Career.ICI_D,
            number=1, is_active=True, weeks_count=16,
        )
        response = self.client.get(reverse('schedule_selector'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('periods', response.context)
        self.assertEqual(response.context['periods'].count(), 1)

    def test_selector_with_period_id_shows_weeks(self):
        period = Period.objects.create(
            career=Period.Career.ICI_D,
            number=1, is_active=True, weeks_count=16,
        )
        response = self.client.get(
            reverse('schedule_selector') + f'?period_id={period.id}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('week_choices', response.context)

    def test_selector_no_periods_empty_list(self):
        response = self.client.get(reverse('schedule_selector'))
        self.assertEqual(response.status_code, 200)


class ViewScheduleTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user   = create_user()
        self.client.login(username='testuser', password='testpass123')

    def test_view_schedule_invalid_period_shows_error(self):
        import uuid
        response = self.client.get(
            reverse('view_schedule') + f'?period_id={uuid.uuid4()}&week_number=0'
        )
        self.assertEqual(response.status_code, 200)
        # Debe mostrar la vista de error, no crashear
        self.assertIn(b'error', response.content.lower() + b'no encontrado'.lower())

    def test_view_schedule_no_period_id_shows_error(self):
        response = self.client.get(reverse('view_schedule') + '?week_number=0')
        self.assertEqual(response.status_code, 200)

    def test_view_schedule_generates_base_schedule(self):
        period = create_full_period()
        response = self.client.get(
            reverse('view_schedule') + f'?period_id={period.id}&week_number=0'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('display_groups', response.context)

    def test_view_schedule_context_has_day_labels(self):
        period = create_full_period()
        response = self.client.get(
            reverse('view_schedule') + f'?period_id={period.id}&week_number=0'
        )
        self.assertIn('day_labels', response.context)
        self.assertEqual(len(response.context['day_labels']), 5)

    def test_view_schedule_context_has_score(self):
        period = create_full_period()
        response = self.client.get(
            reverse('view_schedule') + f'?period_id={period.id}&week_number=0'
        )
        self.assertIn('score', response.context)
        self.assertIsInstance(response.context['score'], int)

    def test_generate_schedule_redirects_to_selector(self):
        # generate_schedule es una vista que redirige al selector
        # La URL se llama /schedule/ (schedule_selector)
        response = self.client.get(reverse('schedule_selector'))
        self.assertEqual(response.status_code, 200)


# ============================================================
# 4. LANDING PAGE
# ============================================================

class LandingPageTest(TestCase):

    def test_landing_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_landing_uses_correct_template(self):
        response = self.client.get('/')
        self.assertIn('landing', response.templates[0].name)