import random
import copy
from typing import List, Dict, Optional, Tuple
from .dto.turn import Turn
from .dto.room import Room
from .interfaces.constraint_interface import ConstraintInterface

DAYS = 5             # Monday to Friday
TIME_SLOTS_PER_DAY = 6

# Penalties
PENALTY_HARD = 1_000_000        # Unfixable violation
PENALTY_MISSING_TURN = 500      # A class that couldn't be placed
PENALTY_WRONG_ROOM_TYPE = 200   # Class in wrong room type
PENALTY_LUNCH_MISSING = 10_000  # Group has no free slot 3 or 4 in a day

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
    Each cell holds a Turn (or an empty Turn).
    Because a conference can hold 2 groups, a single cell may represent
    2 groups simultaneously.
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
        For conferences, first try to merge with an existing conference
        of the same subject/professor before occupying a new slot.
        """
        required_room_type = ACTIVITY_ROOM_TYPE.get(turn.activity_type)

        # --- For conferences: try merging first ---
        if turn.activity_type == 'C':
            for d in range(DAYS):
                for t in range(TIME_SLOTS_PER_DAY):
                    existing = self.matrix[d][t]
                    if existing.can_merge_with(turn):
                        # Check room still fits (same room already assigned)
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

        # Prefer rooms of the correct type
        preferred_rooms = [r for r in self.rooms if r.room_type_code == required_room_type]
        fallback_rooms = [r for r in self.rooms if r.room_type_code != required_room_type]
        candidate_rooms = preferred_rooms if preferred_rooms else fallback_rooms
        random.shuffle(candidate_rooms)

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

    # ------------------------------------------------------------------
    # Conflict detection helpers
    # ------------------------------------------------------------------

    def _has_hard_conflict(self, d: int, t: int, turn: Turn) -> bool:
        """
        Returns True if placing `turn` at (d, t) would cause a hard conflict:
        - Same professor already teaching at (d, t) in a non-mergeable way
        - Same group already has a class at (d, t)
        """
        existing = self.matrix[d][t]
        if existing.is_empty_slot():
            return False

        # Professor conflict (same professor, different subject/type → hard)
        if turn.professor_id and existing.professor_id == turn.professor_id:
            if not existing.can_merge_with(turn):
                return True

        # Group conflict: any group in turn already appears at (d, t)
        for gc in turn.group_codes:
            if gc in existing.group_codes:
                return True

        return False

    def _room_is_free(self, d: int, t: int, room: Room) -> bool:
        """Returns True if the given room is not occupied at (d, t)."""
        for dd in range(DAYS):
            existing = self.matrix[dd][t] if dd == d else None
            if existing and not existing.is_empty_slot():
                if existing.room and existing.room.id == room.id:
                    # Room occupied — unless it's a conference with space
                    if existing.activity_type == 'C' and len(existing.group_codes) < 2:
                        continue  # Still has room for one more group
                    return False
        return True

    # ------------------------------------------------------------------
    # Score calculation
    # ------------------------------------------------------------------

    def calculate_score(self) -> None:
        self.score = 0

        # 1. Penalty for unplaced turns
        self.score += len(self.unscheduled_load) * PENALTY_MISSING_TURN

        # 2. Evaluate placed turns
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = self.matrix[d][t]
                if turn.is_empty_slot():
                    continue
                self.score += self._penalty_wrong_room_type(turn)
                for constraint in self.constraints:
                    self.score += constraint.evaluate(turn, d, t)

        # 3. Lunch break: every group must have slot 3 (index 2) OR slot 4 (index 3) free each day
        self.score += self._penalty_lunch_break()

    def _penalty_wrong_room_type(self, turn: Turn) -> int:
        required = ACTIVITY_ROOM_TYPE.get(turn.activity_type)
        if turn.room and required and turn.room.room_type_code != required:
            return PENALTY_WRONG_ROOM_TYPE
        return 0

    def _penalty_lunch_break(self) -> int:
        """
        For each group, for each day, at least one of slots 3 or 4 (index 2 or 3)
        must be free.
        """
        penalty = 0
        # Collect all group codes present in the schedule
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
        """Uniform crossover: each cell has 50% chance of coming from partner."""
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                if random.random() < 0.5:
                    self.matrix[d][t] = copy.deepcopy(partner_matrix[d][t])

    def mutate(self) -> None:
        """Swap two randomly chosen occupied slots."""
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
        """
        Returns a dict: group_code → 5×6 matrix with only that group's turns.
        Useful for persisting individual group schedules.
        """
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