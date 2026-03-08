"""
populate_data.py — Seed script for the scheduler system.

Creates:
    - 15 professors
    - 10 rooms (3 salons, 4 classrooms, 3 labs)
    - 8 periods (ICI_D semesters 1-8)
    - 4 groups per period
    - 10 subjects per period with C/CP/L activities
    - TeachingActivityAssignments realistas
    - AcademicDays (16 semanas × 5 días) para el período 1
    - 1 Schedule base por grupo del período 1
    - TimeSlots, DocentEvents y AssignedEvents de muestra
    - 3 NonDocentEvents (reunión, taller, conferencia)
    - 4 Constraints de todos los tipos
"""

import random
from datetime import date, timedelta

PROFESSORS_DATA = [
    ('Ana García López',          'Master',   'Titular'),
    ('Carlos Rodríguez Pérez',    'Doctor',   'Titular'),
    ('María Fernández Díaz',      'Master',   'Assistant'),
    ('José Martínez Sánchez',     'Licensed', 'Assistant'),
    ('Laura González Torres',     'Doctor',   'Associate'),
    ('Pedro Hernández Ruiz',      'Master',   'Instructor'),
    ('Carmen López Jiménez',      'Engineer', 'Instructor'),
    ('Antonio Martín Moreno',     'Doctor',   'Titular'),
    ('Isabel Sánchez Castro',     'Master',   'Assistant'),
    ('Francisco Díaz Romero',     'Licensed', 'Associate'),
    ('Elena Jiménez Navarro',     'Doctor',   'Titular'),
    ('Miguel Ángel Ruiz Blanco',  'Master',   'Assistant'),
    ('Sofía Castro Vargas',       'Licensed', 'Instructor'),
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
    ('Programación I',               'PROG1'),
    ('Programación II',              'PROG2'),
    ('Matemática Discreta',          'MATD'),
    ('Álgebra Lineal',               'ALG'),
    ('Arquitectura de Computadoras', 'ARQC'),
    ('Bases de Datos',               'BD'),
    ('Sistemas Operativos',          'SOP'),
    ('Redes de Computadoras',        'REDES'),
    ('Inteligencia Artificial',      'IAP'),
    ('Ingeniería de Software',       'ISP'),
]

NUM_PERIODS     = 8
GROUPS_PER_PERIOD = 4
WEEKS_PER_PERIOD  = 16


def _next_weekday(d, weekday):
    """Return the next date that is `weekday` (0=Mon … 4=Fri)."""
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


def generate_test_data():
    from apps.data_management.models import (
        Period, Professor, Room, Subject, Group,
        Activity, TeachingActivityAssignment,
        AssignedEvent, DocentEvent, NonDocentEvent,
        TimeSlot, Schedule, AcademicDay,
        Constraint, ConstraintSchedule,
    )

    print('\n--- Generando Datos de Prueba ---\n')

    # ── Clear everything ──────────────────────────────────────────────────────
    for model in [
        AssignedEvent, DocentEvent, NonDocentEvent,
        TeachingActivityAssignment, TimeSlot, Schedule, AcademicDay,
        Activity, Subject, ConstraintSchedule, Constraint,
        Group, Room, Professor, Period,
    ]:
        model.objects.all().delete()
    print('Datos anteriores eliminados.')

    # ── Professors ────────────────────────────────────────────────────────────
    professors = []
    for name, sci, doc in PROFESSORS_DATA:
        professors.append(Professor.objects.create(
            full_name=name, scientific_category=sci, docent_category=doc
        ))
    print(f'{len(professors)} profesores creados.')

    # ── Rooms ─────────────────────────────────────────────────────────────────
    rooms = []
    room_objects = {}
    for code, rtype in ROOMS_DATA:
        r = Room.objects.create(room_code=code, room_type=rtype)
        rooms.append(r)
        room_objects[code] = r
    print(f'{len(rooms)} locales creados.')

    # ── Periods ───────────────────────────────────────────────────────────────
    all_periods   = []
    all_groups    = {}   # period_id → [groups]
    period_start  = date(2024, 2, 5)

    for p_num in range(1, NUM_PERIODS + 1):
        period = Period.objects.create(
            number=p_num,
            career=Period.Career.ICI_D,
            weeks_count=WEEKS_PER_PERIOD,
            is_active=True,
            start_date=period_start,
        )
        all_periods.append(period)

        # Groups
        groups = []
        for g in range(1, GROUPS_PER_PERIOD + 1):
            groups.append(Group.objects.create(
                group_code=f'IC{p_num}G{g}',
                period=period,
            ))
        all_groups[period.id] = groups

        # Subjects + Activities
        subjects = []
        for name, alias in SUBJECTS_DATA:
            s = Subject.objects.create(
                name=name, alias=f'{alias}P{p_num}', period=period
            )
            for act_type, act_label in Activity.ActivityType.choices:
                Activity.objects.create(
                    title=f'{act_label} de {alias}P{p_num}',
                    activity_type=act_type,
                    subject=s,
                )
            subjects.append(s)

        _create_assignments(subjects, groups, professors)
        period_start += timedelta(weeks=24)

    print(f'{NUM_PERIODS} períodos, {NUM_PERIODS * GROUPS_PER_PERIOD} grupos, '
          f'{NUM_PERIODS * len(SUBJECTS_DATA)} asignaturas.')
    print(f'Actividades: {Activity.objects.count()}')
    print(f'Asignaciones: {TeachingActivityAssignment.objects.count()}')

    # ── AcademicDays for period 1 ─────────────────────────────────────────────
    first_period = all_periods[0]
    academic_days = _create_academic_days(first_period)
    print(f'Días académicos: {len(academic_days)} (período 1)')

    # ── Schedules, TimeSlots, DocentEvents, AssignedEvents ───────────────────
    first_groups  = all_groups[first_period.id]
    first_subjects = list(Subject.objects.filter(period=first_period))
    first_activities = list(Activity.objects.filter(subject__period=first_period))
    conf_activities = [a for a in first_activities if a.activity_type == 'Conference']

    for group in first_groups:
        schedule = Schedule.objects.create(
            period=first_period,
            group=group,
            is_base=True,
            score=random.randint(0, 5000),
        )
        # Place ~6 assigned events per group (Mon-Fri, slots 1-3 of week 1)
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
                    schedule=schedule,
                    academic_day=day,
                    slot_index=slot_idx,
                )
                if conf_activities:
                    activity = random.choice(conf_activities)
                    room = random.choice(
                        [r for r in rooms if r.room_type == 'Conference Room']
                    )
                    prof_assignment = TeachingActivityAssignment.objects.filter(
                        subject=activity.subject,
                        group=group,
                        activity_type='Conference',
                    ).first()
                    de = DocentEvent.objects.create(
                        professor=prof_assignment.professor if prof_assignment else random.choice(professors),
                        activity=activity,
                        room=room,
                    )
                    AssignedEvent.objects.create(time_slot=ts, docent_event=de)
                    placed += 1

    print(f'Horarios base: {Schedule.objects.count()}')
    print(f'TimeSlots: {TimeSlot.objects.count()}')
    print(f'DocentEvents: {DocentEvent.objects.count()}')
    print(f'AssignedEvents (docentes): {AssignedEvent.objects.filter(docent_event__isnull=False).count()}')

    # ── NonDocentEvents ───────────────────────────────────────────────────────
    non_docent_data = [
        (
            'Reunión de Claustro',
            first_groups[:2],
            professors[:3],
            room_objects.get('S01'),
        ),
        (
            'Taller de Orientación Profesional',
            first_groups[2:],
            professors[3:6],
            room_objects.get('S02'),
        ),
        (
            'Conferencia de Bienvenida',
            first_groups,           # todos los grupos
            professors[:5],
            room_objects.get('S03'),
        ),
    ]

    if academic_days:
        # Place each NonDocentEvent on a specific day + slot
        nde_day   = academic_days[4]  # week 1, Thursday
        nde_slots = [4, 5, 6]

        for idx, (title, groups_list, profs_list, room) in enumerate(non_docent_data):
            nde = NonDocentEvent.objects.create(
                title=title,
                room=room,
            )
            nde.affected_groups.set(groups_list)
            nde.professors.set(profs_list)

            # Assign to a schedule of the first group that is affected
            target_group = groups_list[0] if groups_list else first_groups[0]
            schedule = Schedule.objects.filter(
                period=first_period, group=target_group, is_base=True
            ).first()
            if schedule:
                ts = TimeSlot.objects.create(
                    schedule=schedule,
                    academic_day=nde_day,
                    slot_index=nde_slots[idx],
                )
                AssignedEvent.objects.create(time_slot=ts, non_docent_event=nde)

    print(f'NonDocentEvents: {NonDocentEvent.objects.count()}')
    print(f'AssignedEvents (no docentes): {AssignedEvent.objects.filter(non_docent_event__isnull=False).count()}')

    # ── Constraints ───────────────────────────────────────────────────────────
    _create_constraints(
        professors, first_groups, first_subjects,
        room_objects.get('L01')
    )
    print(f'Restricciones: {Constraint.objects.count()}')
    print('\nSeed completado.\n')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_academic_days(period):
    from apps.data_management.models import AcademicDay
    days = []
    current = period.start_date
    # Advance to Monday if needed
    while current.weekday() != 0:
        current += timedelta(days=1)

    for week_num in range(1, period.weeks_count + 1):
        for day_offset in range(5):  # Mon-Fri
            d = current + timedelta(days=day_offset)
            # Cancel 1 random day in week 3 as example
            is_active = not (week_num == 3 and day_offset == 2)
            reason    = 'Día festivo de prueba' if not is_active else None
            ad = AcademicDay.objects.create(
                period=period,
                date=d,
                is_active=is_active,
                academic_week_number=week_num,
                cancellation_reason=reason,
            )
            days.append(ad)
        current += timedelta(weeks=1)
    return days


def _create_assignments(subjects, groups, professors):
    from apps.data_management.models import TeachingActivityAssignment
    half = len(groups) // 2

    for subject in subjects:
        conf_prof   = random.choice(professors)
        others      = [p for p in professors if p != conf_prof]
        cp_profs    = random.sample(others, k=min(2, len(others)))
        lab_cands   = [p for p in others if p not in cp_profs]
        lab_profs   = random.sample(lab_cands, k=min(2, len(lab_cands))) if lab_cands else cp_profs

        for i, group in enumerate(groups):
            for act_type, cp_p, lab_p in [
                ('Conference',      conf_prof,
                                    conf_prof),
                ('Practical Class', cp_profs[0] if i < half else cp_profs[-1],
                                    cp_profs[0] if i < half else cp_profs[-1]),
                ('Laboratory',      lab_profs[0] if i < half else lab_profs[-1],
                                    lab_profs[0] if i < half else lab_profs[-1]),
            ]:
                prof = cp_p if act_type != 'Laboratory' else lab_p
                try:
                    TeachingActivityAssignment.objects.create(
                        subject=subject, group=group,
                        professor=prof, activity_type=act_type,
                    )
                except Exception:
                    pass


def _create_constraints(professors, groups, subjects, lab_room):
    from apps.data_management.models import Constraint, ConstraintSchedule

    # 1. Profesor no disponible viernes T5-T6
    prof = professors[0]
    c1 = Constraint.objects.create(
        name=f'{prof.full_name} no disponible los viernes en T5 y T6',
        priority=4,
        constraint_type='UNAVAILABILITY',
        target_type='PROFESSOR',
        professor=prof,
        is_active=True,
    )
    ConstraintSchedule.objects.create(
        constraint=c1, pattern_type='ALWAYS',
        days_of_week=[5], slots=[5, 6],
    )

    # 2. Asignatura siempre por la tarde
    if subjects:
        subj = subjects[0]
        c2 = Constraint.objects.create(
            name=f'{subj.name} siempre por la tarde',
            priority=3,
            constraint_type='TIME_SLOT_PREFERENCE',
            target_type='SUBJECT',
            subject=subj,
            is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c2, pattern_type='ALWAYS',
            days_of_week=[], slots=[], time_of_day='AFTERNOON',
        )

    # 3. Local L01 no disponible semanas 3 y 4
    if lab_room:
        c3 = Constraint.objects.create(
            name='L01 no disponible en semanas 3 y 4',
            priority=5,
            constraint_type='UNAVAILABILITY',
            target_type='ROOM',
            room=lab_room,
            is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c3, pattern_type='WEEK_LIST',
            days_of_week=[], slots=[], week_numbers=[3, 4],
        )

    # 4. Grupo sin clases lunes T1
    if groups:
        group = groups[0]
        c4 = Constraint.objects.create(
            name=f'{group.group_code} sin clases el lunes en T1',
            priority=2,
            constraint_type='UNAVAILABILITY',
            target_type='GROUP',
            group=group,
            is_active=True,
        )
        ConstraintSchedule.objects.create(
            constraint=c4, pattern_type='ALWAYS',
            days_of_week=[1], slots=[1],
        )