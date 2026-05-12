"""
seed_constraints.py
===================
Crea 3 restricciones de cada tipo para probar el sistema:
- 3 x UNAVAILABILITY  (indisponibilidad)
- 3 x ROOM_ASSIGNMENT (sala fija)
- 3 x TIME_SLOT_PREFERENCE (preferencia de franja)

Usa datos reales de la BD (profesores, salas, grupos, asignaturas).

Uso:
    python manage.py shell -c "exec(open('seed_constraints.py', encoding='utf-8').read())"
"""
import os
import django

if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.general.settings')
    django.setup()

from apps.data_management.models import (
    Constraint, ConstraintSchedule,
    Professor, Room, Group, Subject, Period,
    AssignedEvent,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def make(constraint_type, target_type, name, priority, **fk):
    c, created = Constraint.objects.get_or_create(
        name=name,
        defaults=dict(
            constraint_type=constraint_type,
            target_type=target_type,
            priority=priority,
            is_active=True,
            **fk,
        )
    )
    return c, created


def schedule(constraint, pattern_type, **kwargs):
    return ConstraintSchedule.objects.get_or_create(
        constraint=constraint,
        pattern_type=pattern_type,
        defaults=kwargs,
    )


def sep(title=''):
    print(('-' * 50) + (f'  {title}' if title else ''))


# ── Pick real objects from the DB ─────────────────────────────────────────────

professors = list(Professor.objects.all()[:5])
rooms_S    = list(Room.objects.filter(room_type=Room.RoomType.CONFERENCE_ROOM)[:3])
rooms_L    = list(Room.objects.filter(room_type=Room.RoomType.LABORATORY)[:3])
groups     = list(Group.objects.all()[:5])
subjects   = list(Subject.objects.all()[:5])

if not professors:
    print("ERROR: No hay profesores en la BD. Carga datos primero.")
    raise SystemExit(1)
if not rooms_S:
    print("ERROR: No hay salas de tipo Conference Room.")
    raise SystemExit(1)
if not groups:
    print("ERROR: No hay grupos en la BD.")
    raise SystemExit(1)
if not subjects:
    print("ERROR: No hay asignaturas en la BD.")
    raise SystemExit(1)

print()
print('=' * 55)
print('  SEMBRANDO RESTRICCIONES DE PRUEBA')
print('=' * 55)

created_total = 0

# =============================================================================
# 1. UNAVAILABILITY — Indisponibilidad temporal
# =============================================================================
sep('UNAVAILABILITY (3)')

# 1a. Profesor no disponible el lunes en turnos 1-2
prof1 = professors[0]
c, new = make(
    Constraint.ConstraintType.UNAVAILABILITY,
    Constraint.TargetType.PROFESSOR,
    f'[TEST] {prof1} - No disponible lunes T1-T2',
    priority=5,
    professor=prof1,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS,
        days_of_week=[1], slots=[1, 2])
status = 'CREADA' if new else 'ya existe'
print(f"  1a. Prof. '{prof1}' - lunes T1-T2 [{status}]")
if new: created_total += 1

# 1b. Sala de laboratorio no disponible los viernes
lab = rooms_L[0] if rooms_L else rooms_S[0]
c, new = make(
    Constraint.ConstraintType.UNAVAILABILITY,
    Constraint.TargetType.ROOM,
    f'[TEST] Sala {lab.room_code} - No disponible viernes',
    priority=4,
    room=lab,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS,
        days_of_week=[5], slots=[])
status = 'CREADA' if new else 'ya existe'
print(f"  1b. Sala '{lab.room_code}' - viernes [{status}]")
if new: created_total += 1

# 1c. Grupo no disponible miercoles T6 (ej. actividad deportiva)
group1 = groups[0]
c, new = make(
    Constraint.ConstraintType.UNAVAILABILITY,
    Constraint.TargetType.GROUP,
    f'[TEST] {group1} - No disponible miercoles T6',
    priority=4,
    group=group1,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS,
        days_of_week=[3], slots=[6])
status = 'CREADA' if new else 'ya existe'
print(f"  1c. Grupo '{group1}' - miercoles T6 [{status}]")
if new: created_total += 1

# =============================================================================
# 2. ROOM_ASSIGNMENT — Sala fija
# =============================================================================
sep('ROOM_ASSIGNMENT (3)')

# Buscar una asignatura que tenga eventos asignados en la BD
# para que la restriccion de sala sea verificable
assigned_subjects = Subject.objects.filter(
    activities_program__isnull=False
).distinct()[:5]

if not assigned_subjects:
    assigned_subjects = subjects

sala1 = rooms_S[0]
sala2 = rooms_S[1] if len(rooms_S) > 1 else rooms_S[0]
sala3 = rooms_S[2] if len(rooms_S) > 2 else rooms_S[0]

subj1 = assigned_subjects[0]
subj2 = assigned_subjects[1] if len(assigned_subjects) > 1 else subjects[0]
prof2 = professors[1] if len(professors) > 1 else professors[0]

# 2a. Asignatura debe usar sala fija (siempre)
c, new = make(
    Constraint.ConstraintType.ROOM_ASSIGNMENT,
    Constraint.TargetType.SUBJECT,
    f'[TEST] {subj1.alias or subj1.name} - sala fija {sala1.room_code}',
    priority=5,
    subject=subj1,
    room=sala1,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS)
status = 'CREADA' if new else 'ya existe'
print(f"  2a. Asignatura '{subj1.alias or subj1.name}' -> sala '{sala1.room_code}' [{status}]")
if new: created_total += 1

# 2b. Otra asignatura - sala fija semanas 1-4
c, new = make(
    Constraint.ConstraintType.ROOM_ASSIGNMENT,
    Constraint.TargetType.SUBJECT,
    f'[TEST] {subj2.alias or subj2.name} - sala fija {sala2.room_code} sem 1-4',
    priority=4,
    subject=subj2,
    room=sala2,
)
schedule(c, ConstraintSchedule.PatternType.WEEK_RANGE,
        week_from=1, week_to=4)
status = 'CREADA' if new else 'ya existe'
print(f"  2b. Asignatura '{subj2.alias or subj2.name}' -> sala '{sala2.room_code}' sem 1-4 [{status}]")
if new: created_total += 1

# 2c. Profesor - sala fija para sus clases
c, new = make(
    Constraint.ConstraintType.ROOM_ASSIGNMENT,
    Constraint.TargetType.PROFESSOR,
    f'[TEST] {prof2} - sala fija {sala3.room_code}',
    priority=3,
    professor=prof2,
    room=sala3,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS)
status = 'CREADA' if new else 'ya existe'
print(f"  2c. Prof. '{prof2}' -> sala '{sala3.room_code}' [{status}]")
if new: created_total += 1

# =============================================================================
# 3. TIME_SLOT_PREFERENCE — Preferencia de franja
# =============================================================================
sep('TIME_SLOT_PREFERENCE (3)')

prof3 = professors[2] if len(professors) > 2 else professors[0]
prof4 = professors[3] if len(professors) > 3 else professors[0]
group2 = groups[1] if len(groups) > 1 else groups[0]
subj3 = assigned_subjects[2] if len(assigned_subjects) > 2 else subjects[0]

# 3a. Profesor prefiere dar clases por la mañana
c, new = make(
    Constraint.ConstraintType.TIME_SLOT_PREFERENCE,
    Constraint.TargetType.PROFESSOR,
    f'[TEST] {prof3} - prefiere manana',
    priority=2,
    professor=prof3,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS,
        time_of_day=ConstraintSchedule.TimeOfDay.MORNING)
status = 'CREADA' if new else 'ya existe'
print(f"  3a. Prof. '{prof3}' - prefiere manana [{status}]")
if new: created_total += 1

# 3b. Grupo prefiere clases los primeros 3 turnos de lunes y martes
c, new = make(
    Constraint.ConstraintType.TIME_SLOT_PREFERENCE,
    Constraint.TargetType.GROUP,
    f'[TEST] {group2} - prefiere lunes/martes T1-T3',
    priority=2,
    group=group2,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS,
        days_of_week=[1, 2], slots=[1, 2, 3])
status = 'CREADA' if new else 'ya existe'
print(f"  3b. Grupo '{group2}' - lunes/martes T1-T3 [{status}]")
if new: created_total += 1

# 3c. Asignatura prefiere turno 2 o 3 (horario de laboratorio accesible)
c, new = make(
    Constraint.ConstraintType.TIME_SLOT_PREFERENCE,
    Constraint.TargetType.SUBJECT,
    f'[TEST] {subj3.alias or subj3.name} - prefiere T2-T3',
    priority=2,
    subject=subj3,
)
schedule(c, ConstraintSchedule.PatternType.ALWAYS,
        slots=[2, 3])
status = 'CREADA' if new else 'ya existe'
print(f"  3c. Asignatura '{subj3.alias or subj3.name}' - T2-T3 [{status}]")
if new: created_total += 1

# =============================================================================
# Resumen
# =============================================================================
sep()
total_constraints = Constraint.objects.filter(name__startswith='[TEST]').count()
print(f"\n  Restricciones [TEST] en BD : {total_constraints}")
print(f"  Creadas en esta ejecucion  : {created_total}")
print()
print("  Ahora regenera los horarios y corre test_schedules.py:")
print("  1. python manage.py shell -c \"exec(open('delete_schedules.py', encoding='utf-8').read())\"")
print("  2. python manage.py shell -c \"exec(open('generate_all_schedules.py', encoding='utf-8').read())\"")
print("  3. python manage.py shell -c \"exec(open('test_schedules.py', encoding='utf-8').read())\"")
print('=' * 55)
print()