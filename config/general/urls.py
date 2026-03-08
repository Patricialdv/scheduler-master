from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from apps.scheduler_management.views import (
    generate_schedule, schedule_selector, view_schedule, landing_page
)

urlpatterns = [
    path('', landing_page, name='landing_page'),
    path('admin/', admin.site.urls),
    path('accounts/login/',
        auth_views.LoginView.as_view(template_name='admin/login.html'),
        name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('schedule/', schedule_selector, name='schedule_selector'),
    path('schedule/view/', view_schedule, name='view_schedule'),
]

# Admin site branding
from django.contrib import admin
admin.site.site_header = 'SGGAH'
admin.site.site_title = 'SGGAH'
admin.site.index_title = 'Panel de Administración'


# Translate auth app name
from django.apps import apps as django_apps
try:
    auth_app = django_apps.get_app_config('auth')
    auth_app.verbose_name = 'Autenticación y Autorización'
except Exception:
    pass