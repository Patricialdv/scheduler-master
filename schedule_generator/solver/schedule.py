import random
import copy
from typing import List, Dict, Optional, Tuple
from .dto.turn import Turn
from .dto.room import Room
from .interfaces.constraint_interface import ConstraintInterface

DAYS = 5
TIME_SLOTS_PER_DAY = 6

# Penalties
PENALTY_HARD             = 1_000_000
PENALTY_MISSING_TURN     = 500
PENALTY_WRONG_ROOM_TYPE  = 50_000   # ← Was 200, now HARD-like: never acceptable
PENALTY_LUNCH_MISSING    = 10_000

# Activity → required room type
ACTIVITY_ROOM_TYPE: Dict[str, str] = {
    'C':  'S',   # Conference  → Salon
    'CP': 'A',   # Practical   → Classroom
    'L':  'L',   # Laboratory  → Laboratory
}


class Schedule:
    """
    One chromosome in the GA.
    The matrix is DAYS x TIME_SLOTS_PER_DAY.
    """

    def __init__(
        self,
        rooms: List[Room],
        constraints: List[ConstraintInterface],
        unscheduled_load: List[Turn],
        base_matrix: Optional[List[List[Turn]]] = None,
    ) -> None:
        self.rooms = rooms
        self.constraints = constraints
        self.unscheduled_load = copy.deepcopy(unscheduled_load)
        self.score: int = 0

        if base_matrix is not None:
            self.matrix = copy.deepcopy(base_matrix)
        else:
            self.matrix = [[Turn() for _ in range(TIME_SLOTS_PER_DAY)] for _ in range(DAYS)]

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize_randomly(self) -> None:
        """Randomly place all turns from unscheduled_load into the matrix."""
        turns_to_place = copy.deepcopy(self.unscheduled_load)
        random.shuffle(turns_to_place)
        unplaced: List[Turn] = []

        for turn in turns_to_place:
            placed = self._try_place_turn(turn)
            if not placed:
                unplaced.append(turn)

        self.unscheduled_load = unplaced

    def _try_place_turn(self, turn: Turn) -> bool:
        """
        Try to place a turn in a valid slot.
        Room type match is REQUIRED — only falls back to wrong type if
        absolutely no correct-type room is available in the whole schedule.
        """
        required_room_type = ACTIVITY_ROOM_TYPE.get(turn.activity_type)

        # Check if a fixed room is required by a ROOM_ASSIGNMENT constraint
        fixed_room = self._get_fixed_room(turn)

        # --- For conferences: try merging first ---
        if turn.activity_type == 'C':
            for d in range(DAYS):
                for t in range(TIME_SLOTS_PER_DAY):
                    existing = self.matrix[d][t]
                    if existing.can_merge_with(turn):
                        existing.merge(turn)
                        return True

        # --- Find an empty slot ---
        available_slots = [
            (d, t)
            for d in range(DAYS)
            for t in range(TIME_SLOTS_PER_DAY)
            if self.matrix[d][t].is_empty_slot()
        ]
        random.shuffle(available_slots)

        if fixed_room:
            # Only try the fixed room
            candidate_rooms = [fixed_room]
        else:
            preferred_rooms = [r for r in self.rooms if r.room_type_code == required_room_type]
            fallback_rooms  = [r for r in self.rooms if r.room_type_code != required_room_type]
            candidate_rooms = preferred_rooms if preferred_rooms else fallback_rooms
        random.shuffle(candidate_rooms)

        for d, t in available_slots:
            if self._has_hard_conflict(d, t, turn):
                continue
            if self._violates_constraints(d, t, turn):
                continue
            for room in candidate_rooms:
                if self._room_is_free(d, t, room):
                    placed_turn = copy.deepcopy(turn)
                    placed_turn.room = room
                    self.matrix[d][t] = placed_turn
                    return True

        # Second pass: relax constraint check (place anyway to avoid unscheduled turns)
        for d, t in available_slots:
            if self._has_hard_conflict(d, t, turn):
                continue
            for room in candidate_rooms:
                if self._room_is_free(d, t, room):
                    placed_turn = copy.deepcopy(turn)
                    placed_turn.room = room
                    self.matrix[d][t] = placed_turn
                    return True

        return False

    def _get_fixed_room(self, turn: Turn) -> Optional[Room]:
        """
        If a ROOM_ASSIGNMENT constraint targets this turn's subject+activity_type,
        return the required Room DTO, else None.
        """
        for c in self.constraints:
            if getattr(c, 'constraint_type', None) != 'ROOM_ASSIGNMENT':
                continue
            rule = getattr(c, 'rule_data', {})
            if rule.get('subject_alias') == turn.subject_alias \
               and rule.get('activity_type') == turn.activity_type:
                # Find the room DTO by id
                room_id = rule.get('room_id')
                for r in self.rooms:
                    if str(r.id) == str(room_id):
                        return r
        return None

    # ------------------------------------------------------------------
    # Conflict detection helpers
    # ------------------------------------------------------------------

    def _violates_constraints(self, d: int, t: int, turn: Turn) -> bool:
        """
        Returns True if placing this turn at (d, t) would violate any
        UNAVAILABILITY or TIME_SLOT_PREFERENCE constraint with priority >= 3.
        Used during initialization to prefer constraint-safe slots.
        """
        for c in self.constraints:
            ctype = getattr(c, 'constraint_type', None)
            if ctype not in ('UNAVAILABILITY', 'TIME_SLOT_PREFERENCE'):
                continue
            if getattr(c, 'priority', 0) < 3:
                continue
            if c.evaluate(turn, d, t) > 0:
                return True
        return False

    def _has_hard_conflict(self, d: int, t: int, turn: Turn) -> bool:
        existing = self.matrix[d][t]
        if existing.is_empty_slot():
            return False

        if turn.professor_id and existing.professor_id == turn.professor_id:
            if not existing.can_merge_with(turn):
                return True

        for gc in turn.group_codes:
            if gc in existing.group_codes:
                return True

        return False

    def _room_is_free(self, d: int, t: int, room: Room) -> bool:
        existing = self.matrix[d][t]
        if existing.is_empty_slot():
            return True
        if existing.room and existing.room.id == room.id:
            if existing.activity_type == 'C' and len(existing.group_codes) < 2:
                return True
            return False
        return True

    # ------------------------------------------------------------------
    # Score calculation
    # ------------------------------------------------------------------

    def calculate_score(self) -> None:
        self.score = 0

        # 1. Unplaced turns
        self.score += len(self.unscheduled_load) * PENALTY_MISSING_TURN

        # 2. Placed turns
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = self.matrix[d][t]
                if turn.is_empty_slot():
                    continue
                self.score += self._penalty_wrong_room_type(turn)
                for constraint in self.constraints:
                    self.score += constraint.evaluate(turn, d, t)

        # 3. Lunch break
        self.score += self._penalty_lunch_break()

    def _penalty_wrong_room_type(self, turn: Turn) -> int:
        required = ACTIVITY_ROOM_TYPE.get(turn.activity_type)
        if turn.room and required and turn.room.room_type_code != required:
            return PENALTY_WRONG_ROOM_TYPE
        return 0

    def _penalty_lunch_break(self) -> int:
        penalty = 0
        all_groups = set()
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = self.matrix[d][t]
                if not turn.is_empty_slot():
                    all_groups.update(turn.group_codes)

        for group in all_groups:
            for d in range(DAYS):
                slot3_free = self.matrix[d][2].is_empty_slot() or group not in self.matrix[d][2].group_codes
                slot4_free = self.matrix[d][3].is_empty_slot() or group not in self.matrix[d][3].group_codes
                if not slot3_free and not slot4_free:
                    penalty += PENALTY_LUNCH_MISSING

        return penalty

    # ------------------------------------------------------------------
    # GA operators
    # ------------------------------------------------------------------

    def fusion(self, partner_matrix: List[List[Turn]]) -> None:
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                if random.random() < 0.5:
                    self.matrix[d][t] = copy.deepcopy(partner_matrix[d][t])

    def mutate(self) -> None:
        occupied = [
            (d, t)
            for d in range(DAYS)
            for t in range(TIME_SLOTS_PER_DAY)
            if not self.matrix[d][t].is_empty_slot()
        ]
        if len(occupied) >= 2:
            (d1, t1), (d2, t2) = random.sample(occupied, 2)
            self.matrix[d1][t1], self.matrix[d2][t2] = self.matrix[d2][t2], self.matrix[d1][t1]

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_score(self) -> int:
        return self.score

    def get_matrix(self) -> List[List[Turn]]:
        return self.matrix

    def is_perfect(self) -> bool:
        return self.score == 0

    def split_by_group(self) -> Dict[str, List[List[Optional[Turn]]]]:
        result: Dict[str, List[List[Optional[Turn]]]] = {}
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = self.matrix[d][t]
                if turn.is_empty_slot():
                    continue
                for gc in turn.group_codes:
                    if gc not in result:
                        result[gc] = [[None] * TIME_SLOTS_PER_DAY for _ in range(DAYS)]
                    result[gc][d][t] = turn
        return result