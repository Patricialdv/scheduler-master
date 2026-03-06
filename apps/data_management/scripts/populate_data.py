"""
populate_data.py — Seed script for the scheduler system.

Creates:
    - 15 professors
    - 10 rooms (3 salons, 4 classrooms, 3 labs)
    - 8 periods (ICI_D semesters 1-8), all active, start dates spaced 6 months apart
    - 4 groups per period
    - 10 subjects per period with C/CP/L activities
    - Realistic TeachingActivityAssignments
    - Sample constraints of all 4 types:
        * UNAVAILABILITY  → professor unavailable on certain days/slots
        * UNAVAILABILITY  → room unavailable on a specific week
        * UNAVAILABILITY  → group unavailable on specific slots
        * TIME_SLOT_PREFERENCE → subject always in the afternoon
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
    ('Sistemas Operativos',          'SO'),
    ('Redes de Computadoras',        'REDES'),
    ('Inteligencia Artificial',      'IA'),
    ('Ingeniería de Software',       'IS'),
]

NUM_PERIODS = 8
GROUPS_PER_PERIOD = 4


def generate_test_data():
    from apps.data_management.models import (
        Period, Professor, Room, Subject, Group,
        Activity, TeachingActivityAssignment,
        AssignedEvent, DocentEvent, NonDocentEvent,
        TimeSlot, Schedule, AcademicDay,
        Constraint, ConstraintSchedule,
    )

    print('\n--- Generando Datos de Prueba ---\n')

    # Clear everything
    for model in [
        AssignedEvent, DocentEvent, NonDocentEvent,
        TeachingActivityAssignment, TimeSlot, Schedule, AcademicDay,
        Activity, Subject, ConstraintSchedule, Constraint,
        Group, Room, Professor, Period,
    ]:
        model.objects.all().delete()
    print('Datos anteriores eliminados.')

    # Professors
    professors = []
    for name, sci, doc in PROFESSORS_DATA:
        professors.append(Professor.objects.create(
            full_name=name, scientific_category=sci, docent_category=doc
        ))
    print(f'{len(professors)} profesores creados.')

    # Rooms
    rooms = []
    room_objects = {}
    for code, rtype in ROOMS_DATA:
        r = Room.objects.create(room_code=code, room_type=rtype)
        rooms.append(r)
        room_objects[code] = r
    print(f'{len(rooms)} locales creados.')

    # Periods + Groups + Subjects + Activities + Assignments
    all_periods = []
    period_start = date(2024, 2, 5)  # First Monday of Feb 2024

    for p_num in range(1, NUM_PERIODS + 1):
        period = Period.objects.create(
            number=p_num,
            career=Period.Career.ICI_D,
            weeks_count=16,
            is_active=True,
            start_date=period_start,
        )
        all_periods.append(period)
        period_start += timedelta(weeks=24)  # ~6 months between periods

        # Groups
        groups = []
        for g in range(1, GROUPS_PER_PERIOD + 1):
            groups.append(Group.objects.create(
                group_code=f'IC{p_num}G{g}',
                period=period,
            ))

        # Subjects + Activities
        subjects = []
        for name, alias in SUBJECTS_DATA:
            s = Subject.objects.create(name=name, alias=f'{alias}P{p_num}', period=period)
            for act_type, act_label in Activity.ActivityType.choices:
                Activity.objects.create(
                    title=f'{act_label} de {alias}',
                    activity_type=act_type,
                    subject=s,
                )
            subjects.append(s)

        # Assignments
        _create_assignments(subjects, groups, professors)

    print(f'{NUM_PERIODS} períodos creados con {NUM_PERIODS * GROUPS_PER_PERIOD} grupos y {NUM_PERIODS * len(SUBJECTS_DATA)} asignaturas.')
    print(f'Asignaciones: {TeachingActivityAssignment.objects.count()}')

    # Constraints (on the first active period)
    first_period = all_periods[0]
    first_groups = list(Group.objects.filter(period=first_period))
    first_subjects = list(Subject.objects.filter(period=first_period))
    first_room = room_objects.get('L01')

    _create_constraints(professors, first_groups, first_subjects, first_room)

    print(f'Restricciones: {Constraint.objects.count()}')
    print('\nSeed completado. Accede a /schedule/ para generar horarios.\n')


def _create_assignments(subjects, groups, professors):
    from apps.data_management.models import TeachingActivityAssignment
    half = len(groups) // 2

    for subject in subjects:
        conf_prof = random.choice(professors)
        others = [p for p in professors if p != conf_prof]
        cp_profs = random.sample(others, k=min(2, len(others)))
        lab_candidates = [p for p in others if p not in cp_profs]
        lab_profs = random.sample(lab_candidates, k=min(2, len(lab_candidates))) if lab_candidates else cp_profs

        for i, group in enumerate(groups):
            for act_type, cp_p, lab_p in [
                ('Conference',     conf_prof,                              conf_prof),
                ('Practical Class', cp_profs[0] if i < half else cp_profs[-1],
                                   cp_profs[0] if i < half else cp_profs[-1]),
                ('Laboratory',     lab_profs[0] if i < half else lab_profs[-1],
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

    # 1. UNAVAILABILITY — Professor unavailable on Fridays (slots 5 and 6)
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
        constraint=c1,
        pattern_type='ALWAYS',
        days_of_week=[5],       # Friday
        slots=[5, 6],
    )
    print(f'  Restricción 1: {c1.name}')

    # 2. TIME_SLOT_PREFERENCE — Subject always in the afternoon (slots 4-6)
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
            constraint=c2,
            pattern_type='ALWAYS',
            days_of_week=[],    # All days
            slots=[],
            time_of_day='AFTERNOON',
        )
        print(f'  Restricción 2: {c2.name}')

    # 3. UNAVAILABILITY — Lab L01 not available during weeks 3 and 4
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
            constraint=c3,
            pattern_type='WEEK_LIST',
            days_of_week=[],    # All days
            slots=[],           # All slots
            week_numbers=[3, 4],
        )
        print(f'  Restricción 3: {c3.name}')

    # 4. UNAVAILABILITY — Group 1 no classes in slot 1 on Mondays
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
            constraint=c4,
            pattern_type='ALWAYS',
            days_of_week=[1],   # Monday
            slots=[1],
        )
        print(f'  Restricción 4: {c4.name}')