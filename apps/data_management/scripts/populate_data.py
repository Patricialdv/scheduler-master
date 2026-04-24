"""
populate_data.py — Seed script for the scheduler system.

Creates:
    - 15 professors
    - 10 rooms (3 salons, 4 classrooms, 3 labs)
    - 8 periods (ICI_D semesters 1-8), only even periods active
    - 4 groups per period
    - 7 subjects per period
    - Realistic TeachingActivityAssignments:
        * Conference (C)      → 1 per subject, SHARED across all groups
                                (same professor, merges into one slot)
        * Practical Class (CP)→ 1 per subject per group (split: G1+G2 / G3+G4)
        * Laboratory (L)      → only for PROG1, MATD, BD (3 of 7 subjects)
                                1 per subject per group
      Total turns per group ≈ 7(C) + 7(CP) + 3(L) = 17 → fits in 30 cells
    - AcademicDays (16 weeks × 5 days) for period 2
    - 3 NonDocentEvents
    - 14 Constraints (all types)
"""

import random
from datetime import date, timedelta

PROFESSORS_DATA = [
    ('Ana Garcia Lopez',          'Master',   'Titular'),
    ('Carlos Rodriguez Perez',    'Doctor',   'Titular'),
    ('Maria Fernandez Diaz',      'Master',   'Assistant'),
    ('Jose Martinez Sanchez',     'Licensed', 'Assistant'),
    ('Laura Gonzalez Torres',     'Doctor',   'Associate'),
    ('Pedro Hernandez Ruiz',      'Master',   'Instructor'),
    ('Carmen Lopez Jimenez',      'Engineer', 'Instructor'),
    ('Antonio Martin Moreno',     'Doctor',   'Titular'),
    ('Isabel Sanchez Castro',     'Master',   'Assistant'),
    ('Francisco Diaz Romero',     'Licensed', 'Associate'),
    ('Elena Jimenez Navarro',     'Doctor',   'Titular'),
    ('Miguel Angel Ruiz Blanco',  'Master',   'Assistant'),
    ('Sofia Castro Vargas',       'Licensed', 'Instructor'),
    ('Roberto Moreno Iglesias',   'Doctor',   'Associate'),
    ('Patricia Vega Serrano',     'Master',   'Titular'),
]

ROOMS_DATA = [
    ('S01', 'Conference Room'),
    ('S02', 'Conference Room'),
    ('S03', 'Conference Room'),
    ('A01', 'Classroom'),
    ('A02', 'Classroom'),
    ('A03', 'Classroom'),
    ('A04', 'Classroom'),
    ('L01', 'Laboratory'),
    ('L02', 'Laboratory'),
    ('L03', 'Laboratory'),
]

SUBJECTS_DATA = [
    ('Programacion I',               'PROG1'),
    ('Programacion II',              'PROG2'),
    ('Matematica Discreta',          'MATD'),
    ('Algebra Lineal',               'ALG'),
    ('Arquitectura de Computadoras', 'ARQC'),
    ('Bases de Datos',               'BD'),
    ('Sistemas Operativos',          'SOP'),
]

# Only these subjects have laboratory sessions
LAB_SUBJECTS = {'PROG1', 'MATD', 'BD'}

NUM_PERIODS       = 8
GROUPS_PER_PERIOD = 4
WEEKS_PER_PERIOD  = 16


def generate_test_data():
    from apps.data_management.models import (
        Period, Professor, Room, Subject, Group,
        Activity, TeachingActivityAssignment,
        AssignedEvent, DocentEvent, NonDocentEvent,
        TimeSlot, Schedule, AcademicDay,
        Constraint, ConstraintSchedule,
    )

    print('\n--- Generando Datos de Prueba ---\n')

    for model in [
        AssignedEvent, DocentEvent, NonDocentEvent,
        TeachingActivityAssignment, TimeSlot, Schedule, AcademicDay,
        Activity, Subject, ConstraintSchedule, Constraint,
        Group, Room, Professor, Period,
    ]:
        model.objects.all().delete()
    print('Datos anteriores eliminados.')

    professors = []
    for name, sci, doc in PROFESSORS_DATA:
        professors.append(Professor.objects.create(
            full_name=name, scientific_category=sci, docent_category=doc
        ))
    print(f'{len(professors)} profesores creados.')

    rooms = []
    room_objects = {}
    for code, rtype in ROOMS_DATA:
        r = Room.objects.create(room_code=code, room_type=rtype)
        rooms.append(r)
        room_objects[code] = r
    print(f'{len(rooms)} locales creados.')

    all_periods = []
    all_groups  = {}
    period_start = date(2024, 2, 5)

    for p_num in range(1, NUM_PERIODS + 1):
        period = Period.objects.create(
            number=p_num,
            career=Period.Career.ICI_D,
            weeks_count=WEEKS_PER_PERIOD,
            is_active=(p_num % 2 == 0),
            start_date=period_start,
        )
        all_periods.append(period)

        groups = []
        for g in range(1, GROUPS_PER_PERIOD + 1):
            groups.append(Group.objects.create(
                group_code=f'IC{p_num}G{g}',
                period=period,
            ))
        all_groups[period.id] = groups

        subjects = []
        for name, alias in SUBJECTS_DATA:
            s = Subject.objects.create(
                name=name, alias=f'{alias}P{p_num}', period=period
            )
            # Create Activity records for all types (needed by the system)
            for act_type, act_label in Activity.ActivityType.choices:
                Activity.objects.create(
                    title=f'{act_label} de {alias}P{p_num}',
                    activity_type=act_type,
                    subject=s,
                )
            subjects.append(s)

        _create_assignments(subjects, groups, professors)
        period_start += timedelta(weeks=24)

    total_assignments = TeachingActivityAssignment.objects.count()
    print(f'{NUM_PERIODS} periodos (pares activos), '
          f'{NUM_PERIODS * GROUPS_PER_PERIOD} grupos, '
          f'{NUM_PERIODS * len(SUBJECTS_DATA)} asignaturas.')
    print(f'Actividades: {Activity.objects.count()}')
    print(f'Asignaciones (TAA): {total_assignments}')

    # Estimate turns per group for an active period
    n_conf = len(SUBJECTS_DATA)           # 7  — one conference per subject (shared)
    n_cp   = len(SUBJECTS_DATA)           # 7  — one CP per subject per group
    n_lab  = len(LAB_SUBJECTS)            # 3  — lab only for lab subjects
    print(f'\nTurnos estimados por grupo por período activo:')
    print(f'  Conferencias (C) : {n_conf}')
    print(f'  Clases Prácticas (CP): {n_cp}')
    print(f'  Laboratorios (L) : {n_lab}')
    print(f'  TOTAL            : {n_conf + n_cp + n_lab} (capacidad de la matriz: 30)\n')

    second_period = all_periods[1]
    academic_days = _create_academic_days(second_period)
    print(f'Dias academicos: {len(academic_days)} (periodo 2)')

    second_groups     = all_groups[second_period.id]
    second_activities = list(Activity.objects.filter(subject__period=second_period))
    conf_activities   = [a for a in second_activities if a.activity_type == 'Conference']

    for group in second_groups:
        schedule = Schedule.objects.create(
            period=second_period,
            group=group,
            is_base=True,
            score=random.randint(0, 5000),
        )
        week1_days = [d for d in academic_days if d.academic_week_number == 1]
        slots_used = set()
        placed = 0
        for day in week1_days:
            for slot_idx in range(1, 4):
                if placed >= 6:
                    break
                key = (day.id, slot_idx)
                if key in slots_used:
                    continue
                slots_used.add(key)
                ts = TimeSlot.objects.create(
                    schedule=schedule, academic_day=day, slot_index=slot_idx,
                )
                if conf_activities:
                    activity = random.choice(conf_activities)
                    room = random.choice([r for r in rooms if r.room_type == 'Conference Room'])
                    prof_assignment = TeachingActivityAssignment.objects.filter(
                        subject=activity.subject, group=group, activity_type='Conference',
                    ).first()
                    de = DocentEvent.objects.create(
                        professor=prof_assignment.professor if prof_assignment else random.choice(professors),
                        activity=activity, room=room,
                    )
                    AssignedEvent.objects.create(time_slot=ts, docent_event=de)
                    placed += 1

    print(f'Horarios base de muestra: {Schedule.objects.count()}')
    print(f'TimeSlots de muestra: {TimeSlot.objects.count()}')

    non_docent_data = [
        ('Reunion de Claustro',              second_groups[:2], professors[:3],  room_objects.get('S01')),
        ('Taller de Orientacion Profesional', second_groups[2:], professors[3:6], room_objects.get('S02')),
        ('Conferencia de Bienvenida',         second_groups,     professors[:5],  room_objects.get('S03')),
    ]
    for title, groups_list, profs_list, room in non_docent_data:
        nde = NonDocentEvent.objects.create(title=title, room=room)
        nde.affected_groups.set(groups_list)
        nde.professors.set(profs_list)
    print(f'NonDocentEvents: {NonDocentEvent.objects.count()}')

    second_subjects = list(Subject.objects.filter(period=second_period))
    lab_room_1 = room_objects.get('L01')
    lab_room_2 = room_objects.get('L02')
    _create_constraints(professors, second_groups, second_subjects, lab_room_1, lab_room_2)
    print(f'Restricciones: {Constraint.objects.count()}')
    print('\n--- Datos de Prueba Generados Correctamente ---\n')


def _create_academic_days(period):
    from apps.data_management.models import AcademicDay
    days = []
    current = period.start_date
    # Skip to Monday
    while current.weekday() != 0:
        current += timedelta(days=1)
    for week_num in range(1, period.weeks_count + 1):
        for day_offset in range(5):
            d = current + timedelta(days=day_offset)
            is_active = not (week_num == 3 and day_offset == 2)
            reason    = 'Día festivo de prueba' if not is_active else None
            ad = AcademicDay.objects.create(
                period=period, date=d, is_active=is_active,
                academic_week_number=week_num, cancellation_reason=reason,
            )
            days.append(ad)
        current += timedelta(weeks=1)
    return days


def _create_assignments(subjects, groups, professors):
    """
    Realistic assignment strategy:

    Conference (C):
        - One professor per subject teaches ALL groups.
        - The GA will merge these into a single shared slot (same prof + subject).
        - Result: 7 C-turns total per period (not 7×4=28).

    Practical Class (CP):
        - Groups are split in half: G1+G2 share one professor, G3+G4 another.
        - Result: 7 CP-turns per group.

    Laboratory (L):
        - Only for LAB_SUBJECTS (PROG1, MATD, BD).
        - Same split as CP.
        - Result: 3 L-turns per group.

    Total per group: 7 + 7 + 3 = 17 turns → fits comfortably in 30 cells.
    """
    from apps.data_management.models import TeachingActivityAssignment

    half = len(groups) // 2

    for subject in subjects:
        alias_base = subject.alias.rstrip('P12345678')  # strip period suffix

        # --- Conference: one professor for all groups ---
        conf_prof = random.choice(professors)
        for group in groups:
            try:
                TeachingActivityAssignment.objects.create(
                    subject=subject,
                    group=group,
                    professor=conf_prof,
                    activity_type='Conference',
                )
            except Exception:
                pass  # unique_together violation — skip

        # --- Practical Class: split by half ---
        others   = [p for p in professors if p != conf_prof]
        cp_profs = random.sample(others, k=min(2, len(others)))
        for i, group in enumerate(groups):
            prof = cp_profs[0] if i < half else cp_profs[-1]
            try:
                TeachingActivityAssignment.objects.create(
                    subject=subject,
                    group=group,
                    professor=prof,
                    activity_type='Practical Class',
                )
            except Exception:
                pass

        # --- Laboratory: only for lab subjects ---
        if alias_base in LAB_SUBJECTS:
            lab_cands = [p for p in others if p not in cp_profs]
            lab_profs = random.sample(lab_cands, k=min(2, len(lab_cands))) if lab_cands else cp_profs
            for i, group in enumerate(groups):
                prof = lab_profs[0] if i < half else lab_profs[-1]
                try:
                    TeachingActivityAssignment.objects.create(
                        subject=subject,
                        group=group,
                        professor=prof,
                        activity_type='Laboratory',
                    )
                except Exception:
                    pass


def _create_constraints(professors, groups, subjects, lab_room_1, lab_room_2):
    from apps.data_management.models import Constraint, ConstraintSchedule

    # C1. Prof 0: no disponible viernes T5-T6 (prioridad 4)
    c1 = Constraint.objects.create(
        name=f'{professors[0].full_name} no disponible viernes T5-T6',
        priority=4, constraint_type='UNAVAILABILITY',
        target_type='PROFESSOR', professor=professors[0], is_active=True,
    )
    ConstraintSchedule.objects.create(
        constraint=c1, pattern_type='ALWAYS', days_of_week=[5], slots=[5, 6],
    )

    # C2. Prof 1: no disponible lunes y miercoles T1-T2 (prioridad 4)
    c2 = Constraint.objects.create(
        name=f'{professors[1].full_name} no disponible lunes/miercoles T1-T2',
        priority=4, constraint_type='UNAVAILABILITY',
        target_type='PROFESSOR', professor=professors[1], is_active=True,
    )
    ConstraintSchedule.objects.create(
        constraint=c2, pattern_type='ALWAYS', days_of_week=[1, 3], slots=[1, 2],
    )

    # C3. Prof 2: no disponible jueves (prioridad 3)
    c3 = Constraint.objects.create(
        name=f'{professors[2].full_name} no disponible jueves',
        priority=3, constraint_type='UNAVAILABILITY',
        target_type='PROFESSOR', professor=professors[2], is_active=True,
    )
    ConstraintSchedule.objects.create(
        constraint=c3, pattern_type='ALWAYS',
        days_of_week=[4], slots=[1, 2, 3, 4, 5, 6],
    )

    # C4. Prof 3: no disponible martes T4-T6 (prioridad 3)
    c4 = Constraint.objects.create(
        name=f'{professors[3].full_name} no disponible martes T4-T6',
        priority=3, constraint_type='UNAVAILABILITY',
        target_type='PROFESSOR', professor=professors[3], is_active=True,
    )
    ConstraintSchedule.objects.create(
        constraint=c4, pattern_type='ALWAYS', days_of_week=[2], slots=[4, 5, 6],
    )

    # C5. Prof 4: no disponible miercoles y viernes T1 (prioridad 4)
    c5 = Constraint.objects.create(
        name=f'{professors[4].full_name} no disponible miercoles/viernes T1',
        priority=4, constraint_type='UNAVAILABILITY',
        target_type='PROFESSOR', professor=professors[4], is_active=True,
    )
    ConstraintSchedule.objects.create(
        constraint=c5, pattern_type='ALWAYS', days_of_week=[3, 5], slots=[1],
    )

    if len(subjects) >= 4:
        # C6. Subj 0: siempre por la tarde (prioridad 4)
        c6 = Constraint.objects.create(
            name=f'{subjects[0].alias} siempre por la tarde',
            priority=4, constraint_type='TIME_SLOT_PREFERENCE',
            target_type='SUBJECT', subject=subjects[0], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c6, pattern_type='ALWAYS',
            days_of_week=[], slots=[], time_of_day='AFTERNOON',
        )

        # C7. Subj 1: siempre por la manana (prioridad 4)
        c7 = Constraint.objects.create(
            name=f'{subjects[1].alias} siempre por la manana',
            priority=4, constraint_type='TIME_SLOT_PREFERENCE',
            target_type='SUBJECT', subject=subjects[1], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c7, pattern_type='ALWAYS',
            days_of_week=[], slots=[], time_of_day='MORNING',
        )

        # C8. Subj 2: preferiblemente por la tarde (prioridad 3)
        c8 = Constraint.objects.create(
            name=f'{subjects[2].alias} preferiblemente por la tarde',
            priority=3, constraint_type='TIME_SLOT_PREFERENCE',
            target_type='SUBJECT', subject=subjects[2], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c8, pattern_type='ALWAYS',
            days_of_week=[], slots=[], time_of_day='AFTERNOON',
        )

        # C9. Subj 3: preferiblemente por la manana (prioridad 3)
        c9 = Constraint.objects.create(
            name=f'{subjects[3].alias} preferiblemente por la manana',
            priority=3, constraint_type='TIME_SLOT_PREFERENCE',
            target_type='SUBJECT', subject=subjects[3], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c9, pattern_type='ALWAYS',
            days_of_week=[], slots=[], time_of_day='MORNING',
        )

    if len(groups) >= 3:
        # C10. Grupo 0: sin clases lunes T1 (prioridad 3)
        c10 = Constraint.objects.create(
            name=f'{groups[0].group_code} sin clases lunes T1',
            priority=3, constraint_type='UNAVAILABILITY',
            target_type='GROUP', group=groups[0], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c10, pattern_type='ALWAYS', days_of_week=[1], slots=[1],
        )

        # C11. Grupo 1: sin clases viernes T5-T6 (prioridad 4)
        c11 = Constraint.objects.create(
            name=f'{groups[1].group_code} sin clases viernes T5-T6',
            priority=4, constraint_type='UNAVAILABILITY',
            target_type='GROUP', group=groups[1], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c11, pattern_type='ALWAYS', days_of_week=[5], slots=[5, 6],
        )

        # C12. Grupo 2: sin clases miercoles T1-T2 (prioridad 3)
        c12 = Constraint.objects.create(
            name=f'{groups[2].group_code} sin clases miercoles T1-T2',
            priority=3, constraint_type='UNAVAILABILITY',
            target_type='GROUP', group=groups[2], is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c12, pattern_type='ALWAYS', days_of_week=[3], slots=[1, 2],
        )

    if lab_room_1 and len(subjects) >= 1:
        # C13. Subj 0 Laboratorio siempre en L01 (prioridad 5)
        c13 = Constraint.objects.create(
            name=f'{subjects[0].alias} Laboratorio siempre en {lab_room_1.room_code}',
            priority=5, constraint_type='ROOM_ASSIGNMENT',
            target_type='SUBJECT', subject=subjects[0],
            room=lab_room_1, is_active=True, notes='L',
        )
        ConstraintSchedule.objects.create(
            constraint=c13, pattern_type='ALWAYS', days_of_week=[], slots=[],
        )

    if lab_room_2 and len(subjects) >= 2:
        # C14. Subj 1 Laboratorio siempre en L02 (prioridad 5)
        c14 = Constraint.objects.create(
            name=f'{subjects[1].alias} Laboratorio siempre en {lab_room_2.room_code}',
            priority=5, constraint_type='ROOM_ASSIGNMENT',
            target_type='SUBJECT', subject=subjects[1],
            room=lab_room_2, is_active=True, notes='L',
        )
        ConstraintSchedule.objects.create(
            constraint=c14, pattern_type='ALWAYS', days_of_week=[], slots=[],
        )