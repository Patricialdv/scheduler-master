"""
============================================================
PRUEBAS AUTOMÁTICAS — data_management
============================================================
Cubre:
  - Modelos (creación, validaciones, __str__)
  - Restricciones ORM (Constraint + ConstraintSchedule)
  - DTOs (Turn, Room)
  - Motor GA (Schedule, penalty, conflictos)
  - ScheduleCreator (GA completo)
  - Constraints del solver (Unavailability, TimeSlotPreference, RoomAssignment)
  - Mappers ORM → DTO (main.py)
============================================================
Ejecutar:  python manage.py test apps.data_management --verbosity=2
"""

import uuid
from django.test import TestCase
from apps.data_management.models import (
    Period, Group, Room, Subject, Activity,
    Professor, TeachingActivityAssignment,
    Constraint, ConstraintSchedule,
)
from schedule_generator.solver.dto.room import Room as RoomDTO
from schedule_generator.solver.dto.turn import Turn as TurnDTO
from schedule_generator.solver.schedule import Schedule as ScheduleGA, PENALTY_WRONG_ROOM_TYPE
from schedule_generator.solver.schedule_creator import ScheduleCreator
from schedule_generator.solver.constraints.unavailability import UnavailabilityConstraint
from schedule_generator.solver.constraints.time_slot_preference import TimeSlotPreferenceConstraint
from schedule_generator.solver.constraints.room_assignment import RoomAssignmentConstraint


# ============================================================
# Fixtures compartidas
# ============================================================

def make_period():
    return Period.objects.create(
        career=Period.Career.ICI_D,
        number=1, is_active=True, weeks_count=16,
    )

def make_professor():
    return Professor.objects.create(
        full_name='Test Professor',
        scientific_category=Professor.ScientificCategory.MASTER,
        docent_category=Professor.DocentCategory.ASSISTANT,
    )

def make_rooms():
    salon = Room.objects.create(room_code='S01', room_type=Room.RoomType.CONFERENCE_ROOM)
    aula  = Room.objects.create(room_code='A01', room_type=Room.RoomType.CLASSROOM)
    lab   = Room.objects.create(room_code='L01', room_type=Room.RoomType.LABORATORY)
    return salon, aula, lab

def make_subject_and_group(period):
    subject = Subject.objects.create(name='Programación I', alias='PROG1', period=period)
    group   = Group.objects.create(group_code='IC1G1', period=period)
    return subject, group

def make_rooms_dto():
    return [
        RoomDTO(id=uuid.uuid4(), room_type_code='S', number='S01'),
        RoomDTO(id=uuid.uuid4(), room_type_code='A', number='A01'),
        RoomDTO(id=uuid.uuid4(), room_type_code='L', number='L01'),
    ]

def make_turns_dto():
    pid = uuid.uuid4()
    return [
        TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',  professor_id=pid),
        TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='CP', professor_id=pid),
        TurnDTO(subject_alias='MAT1',  group_codes=['G1'], activity_type='C',  professor_id=pid),
        TurnDTO(subject_alias='MAT1',  group_codes=['G2'], activity_type='C',  professor_id=pid),
    ]


# ============================================================
# Mocks para constraints (sin BD)
# ============================================================

class MockProfessor:
    def __init__(self): self.id = uuid.uuid4()

class MockRoom:
    def __init__(self, rid=None): self.id = rid or uuid.uuid4()

class MockGroup:
    def __init__(self): self.id = uuid.uuid4()

class MockSubject:
    def __init__(self, alias='PROG1'):
        self.id = uuid.uuid4(); self.alias = alias; self.name = alias

class MockConstraintORM:
    def __init__(self, target_type, priority=3, professor=None,
                 room=None, group=None, subject=None, notes=''):
        self.target_type = target_type; self.priority = priority
        self.professor = professor; self.room = room
        self.group = group; self.subject = subject; self.notes = notes

class MockScheduleORM:
    def __init__(self, pattern_type='ALWAYS', days=None, slots=None, time_of_day=None):
        self.pattern_type   = pattern_type
        self.days_of_week   = days  or [1,2,3,4,5]
        self.slots          = slots or [1,2,3,4,5,6]
        self.time_of_day    = time_of_day
        self.week_numbers   = []
        self.week_from      = None
        self.week_to        = None
        self.week_parity    = None
        self.specific_dates = None


# ============================================================
# 1. MODELOS
# ============================================================

class PeriodModelTest(TestCase):
    def test_create_period(self):
        p = make_period()
        self.assertIsNotNone(p.id)
        self.assertTrue(p.is_active)

    def test_period_str_contains_number(self):
        p = make_period()
        self.assertIn('1', str(p))

    def test_second_period_different_number(self):
        make_period()
        p2 = Period.objects.create(
            career=Period.Career.ICI_D,
            number=2, is_active=True, weeks_count=16,
        )
        self.assertEqual(p2.number, 2)


class RoomModelTest(TestCase):
    def test_room_types_created_correctly(self):
        salon, aula, lab = make_rooms()
        self.assertEqual(salon.room_type, Room.RoomType.CONFERENCE_ROOM)
        self.assertEqual(aula.room_type,  Room.RoomType.CLASSROOM)
        self.assertEqual(lab.room_type,   Room.RoomType.LABORATORY)

    def test_room_str(self):
        salon, _, _ = make_rooms()
        self.assertIn('S01', str(salon))


class ProfessorModelTest(TestCase):
    def test_create_and_str(self):
        p = make_professor()
        self.assertIn('Test Professor', str(p))


class SubjectGroupModelTest(TestCase):
    def setUp(self):
        self.period = make_period()

    def test_subject_linked_to_period(self):
        s, _ = make_subject_and_group(self.period)
        self.assertEqual(s.period, self.period)

    def test_group_linked_to_period(self):
        _, g = make_subject_and_group(self.period)
        self.assertEqual(g.period, self.period)

    def test_subject_str(self):
        s, _ = make_subject_and_group(self.period)
        self.assertIn('PROG1', str(s))

    def test_group_str(self):
        _, g = make_subject_and_group(self.period)
        self.assertIn('IC1G1', str(g))


class ActivityModelTest(TestCase):
    def setUp(self):
        self.period = make_period()
        self.subject, _ = make_subject_and_group(self.period)

    def test_all_activity_types(self):
        for atype in ('C', 'CP', 'L'):
            a = Activity.objects.create(title=f'Act {atype}', activity_type=atype, subject=self.subject)
            self.assertEqual(a.activity_type, atype)

    def test_activity_str(self):
        a = Activity.objects.create(title='Conf', activity_type='C', subject=self.subject)
        self.assertIn('Conf', str(a))


class TeachingAssignmentModelTest(TestCase):
    def setUp(self):
        self.period    = make_period()
        self.professor = make_professor()
        self.subject, self.group = make_subject_and_group(self.period)

    def test_assignment_with_professor(self):
        ta = TeachingActivityAssignment.objects.create(
            subject=self.subject, group=self.group,
            professor=self.professor, activity_type='L',
        )
        self.assertEqual(ta.professor, self.professor)

    def test_assignment_without_professor_allowed(self):
        ta = TeachingActivityAssignment.objects.create(
            subject=self.subject, group=self.group, activity_type='C',
        )
        self.assertIsNone(ta.professor)


# ============================================================
# 2. RESTRICCIONES ORM
# ============================================================

class ConstraintModelTest(TestCase):
    def setUp(self):
        self.period    = make_period()
        self.professor = make_professor()
        self.subject, self.group = make_subject_and_group(self.period)
        _, _, self.lab = make_rooms()

    def test_unavailability_constraint(self):
        c = Constraint.objects.create(
            name='Prof no viernes', constraint_type='UNAVAILABILITY',
            target_type='PROFESSOR', professor=self.professor, priority=5, is_active=True,
        )
        self.assertEqual(c.constraint_type, 'UNAVAILABILITY')

    def test_time_slot_preference_constraint(self):
        c = Constraint.objects.create(
            name='Solo tarde', constraint_type='TIME_SLOT_PREFERENCE',
            target_type='SUBJECT', subject=self.subject, priority=3, is_active=True,
        )
        self.assertEqual(c.constraint_type, 'TIME_SLOT_PREFERENCE')

    def test_room_assignment_constraint(self):
        c = Constraint.objects.create(
            name='Lab en L01', constraint_type='ROOM_ASSIGNMENT',
            target_type='SUBJECT', subject=self.subject, room=self.lab, priority=5, is_active=True,
        )
        self.assertEqual(c.room, self.lab)

    def test_constraint_schedule_always(self):
        c = Constraint.objects.create(
            name='Grupo sin lunes T1', constraint_type='UNAVAILABILITY',
            target_type='GROUP', group=self.group, priority=4, is_active=True,
        )
        cs = ConstraintSchedule.objects.create(
            constraint=c, pattern_type='ALWAYS', days_of_week=[1], slots=[1],
        )
        self.assertEqual(cs.days_of_week, [1])

    def test_constraint_schedule_week_range(self):
        c = Constraint.objects.create(
            name='Semanas 3-4', constraint_type='UNAVAILABILITY',
            target_type='GROUP', group=self.group, priority=3, is_active=True,
        )
        cs = ConstraintSchedule.objects.create(
            constraint=c, pattern_type='WEEK_RANGE', week_from=3, week_to=4,
        )
        self.assertEqual(cs.week_from, 3)
        self.assertEqual(cs.week_to, 4)

    def test_constraint_str(self):
        c = Constraint.objects.create(
            name='Test str', constraint_type='UNAVAILABILITY',
            target_type='GROUP', group=self.group, priority=1,
        )
        self.assertIn('Test str', str(c))


# ============================================================
# 3. DTOs
# ============================================================

class RoomDTOTest(TestCase):
    def test_creation(self):
        r = RoomDTO(id=uuid.uuid4(), room_type_code='L', number='L01')
        self.assertEqual(r.room_type_code, 'L')

    def test_str(self):
        r = RoomDTO(id=uuid.uuid4(), room_type_code='S', number='S01')
        self.assertIn('S01', str(r))


class TurnDTOTest(TestCase):
    def test_empty_turn(self):
        self.assertTrue(TurnDTO().is_empty_slot())

    def test_populated_turn(self):
        t = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L', professor_id=uuid.uuid4())
        self.assertFalse(t.is_empty_slot())

    def test_conference_merge_same_subject(self):
        pid = uuid.uuid4()
        t1 = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C', professor_id=pid)
        t2 = TurnDTO(subject_alias='MAT1', group_codes=['G2'], activity_type='C', professor_id=pid)
        self.assertTrue(t1.can_merge_with(t2))

    def test_conference_no_merge_different_subject(self):
        pid = uuid.uuid4()
        t1 = TurnDTO(subject_alias='MAT1',  group_codes=['G1'], activity_type='C', professor_id=pid)
        t2 = TurnDTO(subject_alias='PROG1', group_codes=['G2'], activity_type='C', professor_id=pid)
        self.assertFalse(t1.can_merge_with(t2))

    def test_conference_no_merge_when_full(self):
        pid = uuid.uuid4()
        t1 = TurnDTO(subject_alias='MAT1', group_codes=['G1','G2'], activity_type='C', professor_id=pid)
        t2 = TurnDTO(subject_alias='MAT1', group_codes=['G3'],      activity_type='C', professor_id=pid)
        self.assertFalse(t1.can_merge_with(t2))

    def test_merge_adds_group(self):
        pid = uuid.uuid4()
        t1 = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C', professor_id=pid)
        t2 = TurnDTO(subject_alias='MAT1', group_codes=['G2'], activity_type='C', professor_id=pid)
        t1.merge(t2)
        self.assertIn('G2', t1.group_codes)


# ============================================================
# 4. MOTOR GA (Schedule)
# ============================================================

class ScheduleGATest(TestCase):
    def setUp(self):
        self.rooms = make_rooms_dto()
        self.turns = make_turns_dto()

    def test_initialize_places_at_least_one_turn(self):
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=self.turns)
        s.initialize_randomly()
        placed = sum(1 for d in range(5) for t in range(6) if not s.matrix[d][t].is_empty_slot())
        self.assertGreater(placed, 0)

    def test_calculate_score_returns_int(self):
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=self.turns)
        s.initialize_randomly()
        s.calculate_score()
        self.assertIsInstance(s.get_score(), int)

    def test_lab_in_lab_room_no_penalty(self):
        lab  = self.rooms[2]  # 'L'
        turn = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',
                       professor_id=uuid.uuid4(), room=lab)
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        s.matrix[0][0] = turn
        s.calculate_score()
        self.assertEqual(s.get_score(), 0)

    def test_lab_in_salon_has_high_penalty(self):
        salon = self.rooms[0]  # 'S'
        turn  = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',
                        professor_id=uuid.uuid4(), room=salon)
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        s.matrix[0][0] = turn
        s.calculate_score()
        self.assertGreaterEqual(s.get_score(), PENALTY_WRONG_ROOM_TYPE)

    def test_practical_in_classroom_no_penalty(self):
        aula = self.rooms[1]  # 'A'
        turn = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='CP',
                       professor_id=uuid.uuid4(), room=aula)
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        s.matrix[0][0] = turn
        s.calculate_score()
        self.assertEqual(s.get_score(), 0)

    def test_professor_conflict_detected(self):
        pid = uuid.uuid4()
        t1  = TurnDTO(subject_alias='MAT1',  group_codes=['G1'], activity_type='CP', professor_id=pid)
        t2  = TurnDTO(subject_alias='PROG1', group_codes=['G2'], activity_type='CP', professor_id=pid)
        s   = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        s.matrix[0][0] = t1
        self.assertTrue(s._has_hard_conflict(0, 0, t2))

    def test_group_conflict_detected(self):
        t1 = TurnDTO(subject_alias='MAT1',  group_codes=['G1'], activity_type='CP', professor_id=uuid.uuid4())
        t2 = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',  professor_id=uuid.uuid4())
        s  = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        s.matrix[1][2] = t1
        self.assertTrue(s._has_hard_conflict(1, 2, t2))

    def test_no_conflict_different_groups_and_professors(self):
        t1 = TurnDTO(subject_alias='MAT1',  group_codes=['G1'], activity_type='CP', professor_id=uuid.uuid4())
        t2 = TurnDTO(subject_alias='PROG1', group_codes=['G2'], activity_type='L',  professor_id=uuid.uuid4())
        s  = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        s.matrix[0][0] = t1
        self.assertFalse(s._has_hard_conflict(0, 0, t2))

    def test_lunch_break_penalty_when_both_slots_occupied(self):
        pid = uuid.uuid4()
        s   = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=[])
        for d in range(5):
            s.matrix[d][2] = TurnDTO(subject_alias='MAT',  group_codes=['G1'], activity_type='CP',
                                      professor_id=pid, room=self.rooms[1])
            s.matrix[d][3] = TurnDTO(subject_alias='PROG', group_codes=['G1'], activity_type='CP',
                                      professor_id=uuid.uuid4(), room=self.rooms[1])
        s.calculate_score()
        self.assertGreater(s.get_score(), 0)

    def test_split_by_group_returns_dict(self):
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=self.turns)
        s.initialize_randomly()
        groups = s.split_by_group()
        self.assertIsInstance(groups, dict)

    def test_mutation_changes_at_most_two_slots(self):
        import copy
        s = ScheduleGA(rooms=self.rooms, constraints=[], unscheduled_load=self.turns)
        s.initialize_randomly()
        before = copy.deepcopy(s.matrix)
        s.mutate()
        diff = sum(1 for d in range(5) for t in range(6) if str(s.matrix[d][t]) != str(before[d][t]))
        self.assertIn(diff, [0, 2])


# ============================================================
# 5. SCHEDULE CREATOR (GA completo)
# ============================================================

class ScheduleCreatorTest(TestCase):
    def setUp(self):
        self.rooms = make_rooms_dto()
        self.turns = make_turns_dto()

    def test_returns_schedule_object(self):
        c = ScheduleCreator(unscheduled_load=self.turns, rooms=self.rooms, constraints=[])
        self.assertIsNotNone(c.get_best_schedule())

    def test_score_non_negative(self):
        c = ScheduleCreator(unscheduled_load=self.turns, rooms=self.rooms, constraints=[])
        best = c.get_best_schedule()
        best.calculate_score()
        self.assertGreaterEqual(best.get_score(), 0)

    def test_lab_only_rooms_available(self):
        """Con solo locales de laboratorio, los labs no deben tener penalidad de tipo."""
        labs = [RoomDTO(id=uuid.uuid4(), room_type_code='L', number=f'L0{i}') for i in range(4)]
        pid  = uuid.uuid4()
        turns = [TurnDTO(subject_alias='PROG1', group_codes=[f'G{i}'], activity_type='L',
                         professor_id=pid) for i in range(3)]
        c    = ScheduleCreator(unscheduled_load=turns, rooms=labs, constraints=[])
        best = c.get_best_schedule()
        best.calculate_score()
        self.assertEqual(best.get_score(), 0, "Labs en locales de laboratorio → score 0")

    def test_places_turns_in_matrix(self):
        c = ScheduleCreator(unscheduled_load=self.turns, rooms=self.rooms, constraints=[])
        best = c.get_best_schedule()
        placed = sum(1 for d in range(5) for t in range(6) if not best.matrix[d][t].is_empty_slot())
        self.assertGreater(placed, 0)


# ============================================================
# 6. CONSTRAINTS DEL SOLVER
# ============================================================

class UnavailabilityConstraintTest(TestCase):

    def test_professor_blocked_slot_penalizes(self):
        prof = MockProfessor()
        # days=[5]=Viernes→índice 4; slots=[5]=T5→índice 4
        c = UnavailabilityConstraint(
            MockConstraintORM('PROFESSOR', professor=prof),
            [MockScheduleORM(days=[5], slots=[5])],
        )
        turn = TurnDTO(subject_alias='X', group_codes=['G1'], activity_type='CP', professor_id=prof.id)
        self.assertGreater(c.evaluate(turn, day=4, slot=4), 0)

    def test_professor_free_slot_no_penalty(self):
        prof = MockProfessor()
        # Bloquea Viernes T5; evaluamos Lunes T1 → no debe penalizar
        c = UnavailabilityConstraint(
            MockConstraintORM('PROFESSOR', professor=prof),
            [MockScheduleORM(days=[5], slots=[5])],
        )
        turn = TurnDTO(subject_alias='X', group_codes=['G1'], activity_type='CP', professor_id=prof.id)
        self.assertEqual(c.evaluate(turn, day=0, slot=0), 0)

    def test_different_professor_no_penalty(self):
        prof = MockProfessor()
        # MockScheduleORM() bloquea todos los días/turnos, pero es otro profesor
        c = UnavailabilityConstraint(
            MockConstraintORM('PROFESSOR', professor=prof),
            [MockScheduleORM()],
        )
        turn = TurnDTO(subject_alias='X', group_codes=['G1'], activity_type='CP', professor_id=uuid.uuid4())
        self.assertEqual(c.evaluate(turn, day=0, slot=0), 0)

    def test_subject_blocked_penalizes(self):
        subj = MockSubject('PROG1')
        # days=[1] = Lunes → índice 0; slots=[1] = T1 → índice 0
        c = UnavailabilityConstraint(
            MockConstraintORM('SUBJECT', subject=subj),
            [MockScheduleORM(days=[1], slots=[1])],
        )
        turn = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='CP', professor_id=uuid.uuid4())
        self.assertGreater(c.evaluate(turn, day=0, slot=0), 0)

    def test_subject_other_alias_no_penalty(self):
        subj = MockSubject('PROG1')
        c = UnavailabilityConstraint(
            MockConstraintORM('SUBJECT', subject=subj),
            [MockScheduleORM(days=[1], slots=[1])],  # Bloquea Lunes T1
        )
        turn = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C', professor_id=uuid.uuid4())
        self.assertEqual(c.evaluate(turn, day=0, slot=0), 0)

    def test_empty_turn_never_penalizes(self):
        c = UnavailabilityConstraint(
            MockConstraintORM('PROFESSOR', professor=MockProfessor()),
            [MockScheduleORM()],
        )
        self.assertEqual(c.evaluate(TurnDTO(), day=0, slot=0), 0)


class TimeSlotPreferenceConstraintTest(TestCase):

    def test_afternoon_pref_morning_slot_penalizes(self):
        subj = MockSubject('MAT1')
        c = TimeSlotPreferenceConstraint(
            MockConstraintORM('SUBJECT', subject=subj),
            [MockScheduleORM(time_of_day='AFTERNOON')],
        )
        turn = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C', professor_id=uuid.uuid4())
        self.assertGreater(c.evaluate(turn, day=0, slot=0), 0)   # Mañana → penaliza

    def test_afternoon_pref_afternoon_slot_no_penalty(self):
        subj = MockSubject('MAT1')
        c = TimeSlotPreferenceConstraint(
            MockConstraintORM('SUBJECT', subject=subj),
            [MockScheduleORM(time_of_day='AFTERNOON')],
        )
        turn = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C', professor_id=uuid.uuid4())
        self.assertEqual(c.evaluate(turn, day=0, slot=4), 0)     # Tarde → ok

    def test_morning_pref_afternoon_penalizes(self):
        subj = MockSubject('PROG1')
        c = TimeSlotPreferenceConstraint(
            MockConstraintORM('SUBJECT', subject=subj),
            [MockScheduleORM(time_of_day='MORNING')],
        )
        turn = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='CP', professor_id=uuid.uuid4())
        self.assertGreater(c.evaluate(turn, day=0, slot=5), 0)   # Tarde → penaliza

    def test_wrong_subject_no_penalty(self):
        subj = MockSubject('PROG1')
        c = TimeSlotPreferenceConstraint(
            MockConstraintORM('SUBJECT', subject=subj),
            [MockScheduleORM(time_of_day='AFTERNOON')],
        )
        turn = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C', professor_id=uuid.uuid4())
        self.assertEqual(c.evaluate(turn, day=0, slot=0), 0)


class RoomAssignmentConstraintTest(TestCase):

    def _make_constraint(self, alias, room_id, notes=''):
        subj = MockSubject(alias)
        room = MockRoom(room_id)
        return RoomAssignmentConstraint(
            MockConstraintORM('SUBJECT', subject=subj, room=room, notes=notes), []
        )

    def test_correct_room_no_penalty(self):
        rid  = uuid.uuid4()
        c    = self._make_constraint('PROG1', rid)
        room_dto = RoomDTO(id=rid, room_type_code='L', number='L01')
        turn = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',
                       professor_id=uuid.uuid4(), room=room_dto)
        self.assertEqual(c.evaluate(turn, 0, 0), 0)

    def test_wrong_room_penalizes(self):
        rid  = uuid.uuid4()
        c    = self._make_constraint('PROG1', rid)
        turn = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',
                       professor_id=uuid.uuid4(),
                       room=RoomDTO(id=uuid.uuid4(), room_type_code='S', number='S01'))
        self.assertGreater(c.evaluate(turn, 0, 0), 0)

    def test_different_subject_no_penalty(self):
        rid  = uuid.uuid4()
        c    = self._make_constraint('PROG1', rid)
        turn = TurnDTO(subject_alias='MAT1', group_codes=['G1'], activity_type='C',
                       professor_id=uuid.uuid4(),
                       room=RoomDTO(id=uuid.uuid4(), room_type_code='S', number='S01'))
        self.assertEqual(c.evaluate(turn, 0, 0), 0)

    def test_activity_type_filter_L_ignores_C(self):
        rid  = uuid.uuid4()
        c    = self._make_constraint('PROG1', rid, notes='L')
        wrong_room = RoomDTO(id=uuid.uuid4(), room_type_code='S', number='S01')
        # C de la misma asignatura → no penaliza (la restricción es solo para L)
        turn_c = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='C',
                         professor_id=uuid.uuid4(), room=wrong_room)
        self.assertEqual(c.evaluate(turn_c, 0, 0), 0)
        # L → sí penaliza
        turn_l = TurnDTO(subject_alias='PROG1', group_codes=['G1'], activity_type='L',
                         professor_id=uuid.uuid4(), room=wrong_room)
        self.assertGreater(c.evaluate(turn_l, 0, 0), 0)


# ============================================================
# 7. MAPPERS ORM → DTO
# ============================================================

class MappersTest(TestCase):
    def setUp(self):
        self.period    = make_period()
        self.professor = make_professor()
        self.salon, self.aula, self.lab = make_rooms()
        self.subject, self.group = make_subject_and_group(self.period)

    def test_map_rooms_count(self):
        from schedule_generator.main import _map_rooms
        dtos = _map_rooms(self.period)
        self.assertEqual(len(dtos), 3)

    def test_map_rooms_type_codes(self):
        from schedule_generator.main import _map_rooms
        dtos = _map_rooms(self.period)
        codes = {r.number: r.room_type_code for r in dtos}
        self.assertEqual(codes['S01'], 'S')
        self.assertEqual(codes['A01'], 'A')
        self.assertEqual(codes['L01'], 'L')

    def test_map_turns_skips_no_professor(self):
        from schedule_generator.main import _map_turns
        TeachingActivityAssignment.objects.create(
            subject=self.subject, group=self.group, activity_type='C'
        )
        self.assertEqual(len(_map_turns(self.period)), 0)

    def test_map_turns_includes_with_professor(self):
        from schedule_generator.main import _map_turns
        TeachingActivityAssignment.objects.create(
            subject=self.subject, group=self.group,
            professor=self.professor, activity_type='L',
        )
        turns = _map_turns(self.period)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].activity_type, 'L')
        self.assertEqual(turns[0].subject_alias, 'PROG1')

    def test_map_turns_uses_alias(self):
        from schedule_generator.main import _map_turns
        TeachingActivityAssignment.objects.create(
            subject=self.subject, group=self.group,
            professor=self.professor, activity_type='CP',
        )
        turns = _map_turns(self.period)
        self.assertEqual(turns[0].subject_alias, 'PROG1')  # alias, no name