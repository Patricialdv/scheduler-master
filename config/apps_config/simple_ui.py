# SimpleUI Configuration
SIMPLEUI_LOGO = ''
SIMPLEUI_TITLE = 'UCI Scheduler'

SIMPLEUI_HOME_INFO = False
SIMPLEUI_ANALYSIS = False
SIMPLEUI_DEFAULT_THEME = 'admin.lte.css'

SIMPLEUI_HOME_QUICK = True
SIMPLEUI_HOME_ACTION = True

# Custom menu
SIMPLEUI_CONFIG = {
    'system_keep': False,
    'menu_display': [
        'Períodos y Calendario',
        'Datos Académicos',
        'Restricciones',
        'Horarios Generados',
        'Autenticación',
    ],
    'dynamic': True,
    'menus': [
        {
            'name': 'Períodos y Calendario',
            'icon': 'fas fa-calendar-alt',
            'models': [
                {'name': 'Períodos',      'icon': 'fas fa-graduation-cap', 'url': 'data_management/period/'},
                {'name': 'Días Académicos','icon': 'fas fa-calendar-day',  'url': 'data_management/academicday/'},
                {'name': 'Grupos',         'icon': 'fas fa-users',          'url': 'data_management/group/'},
            ]
        },
        {
            'name': 'Datos Académicos',
            'icon': 'fas fa-book',
            'models': [
                {'name': 'Profesores',     'icon': 'fas fa-chalkboard-teacher', 'url': 'data_management/professor/'},
                {'name': 'Locales',        'icon': 'fas fa-door-open',          'url': 'data_management/room/'},
                {'name': 'Asignaturas',    'icon': 'fas fa-book-open',          'url': 'data_management/subject/'},
                {'name': 'Actividades',    'icon': 'fas fa-tasks',              'url': 'data_management/activity/'},
                {'name': 'Asignaciones',   'icon': 'fas fa-user-tie',           'url': 'data_management/teachingactivityassignment/'},
            ]
        },
        {
            'name': 'Restricciones',
            'icon': 'fas fa-ban',
            'models': [
                {'name': 'Restricciones',         'icon': 'fas fa-exclamation-triangle', 'url': 'data_management/constraint/'},
                {'name': 'Patrones temporales',   'icon': 'fas fa-clock',                'url': 'data_management/constraintschedule/'},
            ]
        },
        {
            'name': 'Horarios Generados',
            'icon': 'fas fa-table',
            'models': [
                {'name': 'Horarios',       'icon': 'fas fa-calendar-week', 'url': 'data_management/schedule/'},
                {'name': 'Eventos Docentes','icon': 'fas fa-chalkboard',   'url': 'data_management/docentevent/'},
            ]
        },
        {
            'name': 'Autenticación',
            'icon': 'fas fa-shield-alt',
            'models': [
                {'name': 'Usuarios', 'icon': 'fas fa-user', 'url': 'auth/user/'},
                {'name': 'Grupos',   'icon': 'fas fa-users','url': 'auth/group/'},
            ]
        },
        {
            'name': '📅 Ver Horarios',
            'icon': 'fas fa-external-link-alt',
            'url': '/schedule/',
            'models': []
        },
    ]
}

# Hide SimpleUI's own header bar and inject our navbar via custom CSS/JS
SIMPLEUI_EXTRA_FIELDS = {}

# Custom CSS injected into every admin page
SIMPLEUI_CSS = '/static/admin/uci_admin.css'
SIMPLEUI_JS = '/static/admin/uci_admin.js'