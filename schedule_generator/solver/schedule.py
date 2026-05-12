import random
import copy
from typing import List, Dict, Optional, Tuple
from .dto.turn import Turn
from .dto.room import Room
from .interfaces.constraint_interface import ConstraintInterface

DAYS = 5
TIME_SLOTS_PER_DAY = 6

# Penalties - Jerarquía de restricciones (C1: rebalanceo proporcional)
# Prioridad: HARD > INCOMPATIBLE_ROOM > WRONG_ROOM_TYPE > LUNCH > MISSING
#   - HARD: restricción dura (conflictos directos de profesor/grupo)
#   - INCOMPATIBLE_ROOM: tipo de aula incompatible con tipo de actividad
#   - WRONG_ROOM_TYPE: sala incorrecta → 20× missing turn
#   - LUNCH_MISSING: sin pausa de almuerzo → 10× missing turn
#   - MISSING_TURN: turno no colocado (valor base de referencia)
PENALTY_HARD              = 1_000_000
PENALTY_INCOMPATIBLE_ROOM = 50_000  # Penalización crítica por tipo incompatible
PENALTY_WRONG_ROOM_TYPE   = 10_000
PENALTY_LUNCH_MISSING     = 5_000
PENALTY_MISSING_TURN      = 60_000   # Mayor que prioridad 4 (50K) → el GA prefiere respetar restricciones antes que dejar turnos sin colocar

# Activity → allowed room types (set for strict matching)
#   - C (Conferencia): solo en Salón (S)
#   - CP (Clase Práctica): solo en Aulas (A)
#   - L (Laboratorio): solo en Laboratorio (L)
ACTIVITY_ROOM_TYPES: Dict[str, set] = {
    'C':  {'S'},   # Conference → solo Salón
    'CP': {'A'},   # Practical  → solo Aulas
    'L':  {'L'},   # Laboratory → solo Laboratorio
}

# Penalización por desequilibrio de carga entre días
PENALTY_DAY_IMBALANCE = 300  # por slot de desviación respecto al ideal


class Schedule:
    """
    One chromosome in the GA.
    The matrix is DAYS x TIME_SLOTS_PER_DAY.

    Placement strategy [04]:
        1. Turns with active constraints are placed first, guaranteeing compliance.
        2. Remaining turns (no constraints) fill the available slots.

    Population seeding [05]:
        initialize_from_permutation() places constrained turns in the same guaranteed
        slots as the reference individual, then shuffles only the free turns.
        This lets subsequent individuals vary around a valid constraint-safe base.

    Score cache [10]:
        Each cell's partial score is stored in self._cell_scores[d][t].
        calculate_score() rebuilds the full cache.
        calculate_score_after_swap() recomputes only the two affected cells,
        making post-mutation evaluation O(1) instead of O(DAYS×SLOTS).
    """

    def __init__(
        self,
        rooms: List[Room],
        constraints: List[ConstraintInterface],
        unscheduled_load: List[Turn],
        base_matrix: Optional[List[List[Turn]]] = None,
        matrix: Optional[List[List[Turn]]] = None,  # A1: para crossover sin deepcopy
    ) -> None:
        self.rooms = rooms
        self.constraints = constraints
        self.unscheduled_load = copy.deepcopy(unscheduled_load)
        self.score: int = 0

        # [10] Per-cell score cache
        self._cell_scores: List[List[int]] = [
            [0] * TIME_SLOTS_PER_DAY for _ in range(DAYS)
        ]
        self._last_lunch_penalty: int = 0

        # A1: prioridad: matrix > base_matrix > nueva vacía
        if matrix is not None:
            self.matrix = matrix
        elif base_matrix is not None:
            self.matrix = copy.deepcopy(base_matrix)
        else:
            self.matrix = [[Turn() for _ in range(TIME_SLOTS_PER_DAY)] for _ in range(DAYS)]

    # ------------------------------------------------------------------
    # M2: Cache reset
    # ------------------------------------------------------------------

    def _reset_cache(self) -> None:
        """M2: Limpiar estado de caché antes de evaluar hijos del crossover."""
        self.score = 0
        self._cell_scores = [
            [0] * TIME_SLOTS_PER_DAY for _ in range(DAYS)
        ]
        self._last_lunch_penalty = 0

    # ------------------------------------------------------------------
    # Initialization  [04] [05]
    # ------------------------------------------------------------------

    def _split_turns_by_constraint(self, turns: List[Turn]):
        """
        Split turns into two lists:
            constrained : turns affected by any active UNAVAILABILITY,
                        TIME_SLOT_PREFERENCE, or ROOM_ASSIGNMENT constraint
            free        : turns with no matching constraint
        """
        constrained_turns: List[Turn] = []
        free_turns: List[Turn] = []

        for turn in turns:
            has_constraint = False
            for c in self.constraints:
                ctype = getattr(c, 'constraint_type', None)
                if ctype not in ('UNAVAILABILITY', 'TIME_SLOT_PREFERENCE', 'ROOM_ASSIGNMENT'):
                    continue
                # Quick match: does this constraint target this turn?
                target_type = getattr(c, 'target_type', None)
                if target_type == 'PROFESSOR' and getattr(c, 'target_id', None) == turn.professor_id:
                    has_constraint = True
                    break
                if target_type == 'GROUP':
                    if str(getattr(c, 'target_id', '')) in [str(g) for g in turn.group_codes]:
                        has_constraint = True
                        break
                if target_type == 'SUBJECT':
                    if getattr(c, 'subject_alias', None) == turn.subject_alias:
                        has_constraint = True
                        break
                if ctype == 'ROOM_ASSIGNMENT':
                    rule = getattr(c, 'rule_data', {})
                    if rule.get('subject_alias') == turn.subject_alias:
                        has_constraint = True
                        break

            if has_constraint:
                constrained_turns.append(turn)
            else:
                free_turns.append(turn)

        return constrained_turns, free_turns

    def initialize_randomly(self) -> None:
        """
        [04] Place constrained turns first (guaranteed compliance),
        then place free turns in remaining slots.
        """
        turns_to_place = copy.deepcopy(self.unscheduled_load)
        constrained, free = self._split_turns_by_constraint(turns_to_place)

        random.shuffle(constrained)
        random.shuffle(free)

        unplaced: List[Turn] = []

        # Pass 1: constrained turns — strict placement
        for turn in constrained:
            placed = self._try_place_turn(turn, strict=True)
            if not placed:
                unplaced.append(turn)

        # Pass 2: free turns — relaxed placement
        for turn in free:
            placed = self._try_place_turn(turn, strict=False)
            if not placed:
                unplaced.append(turn)

        self.unscheduled_load = unplaced

    def initialize_from_permutation(self, reference: 'Schedule') -> None:
        """
        [05] Seed this individual from a reference schedule:
            - Constrained turns are placed in the same (d, t) slots as in the
            reference, preserving constraint compliance.
            - Free turns are randomly permuted and placed in remaining slots.
        This ensures population diversity without sacrificing constraint safety.
        """
        # Copy the constrained cells verbatim from the reference
        constrained_turns_ref: List[Tuple[int, int, Turn]] = []
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = reference.matrix[d][t]
                if turn.is_empty_slot():
                    continue
                # A2: llamar una sola vez y reusar el resultado
                constrained, free = self._split_turns_by_constraint([turn])
                if len(free) == 0:
                    # It's constrained → copy position
                    self.matrix[d][t] = copy.deepcopy(turn)
                    constrained_turns_ref.append((d, t, turn))

        # Collect free turns (not placed yet) and shuffle them
        all_turn_subjects = set()
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                if not self.matrix[d][t].is_empty_slot():
                    all_turn_subjects.add(id(self.matrix[d][t]))

        free_turns = copy.deepcopy(self.unscheduled_load)
        _, free_turns = self._split_turns_by_constraint(free_turns)
        random.shuffle(free_turns)

        unplaced: List[Turn] = []
        for turn in free_turns:
            placed = self._try_place_turn(turn, strict=False)
            if not placed:
                unplaced.append(turn)

        self.unscheduled_load = unplaced

    def _try_place_turn(self, turn: Turn, strict: bool = True) -> bool:
        """
        Try to place a turn in a valid slot.

        strict=True  : respects UNAVAILABILITY / TIME_SLOT_PREFERENCE constraints
                    with priority >= 3 (used for constrained turns).
        strict=False : skips soft-constraint check (used for free turns and
                    the relaxed second pass).
        """
        required_room_type = ACTIVITY_ROOM_TYPES.get(turn.activity_type)

        # --- For conferences: try merging first ---
        if turn.activity_type == 'C':
            for d in range(DAYS):
                for t in range(TIME_SLOTS_PER_DAY):
                    existing = self.matrix[d][t]
                    if existing.can_merge_with(turn):
                        existing.merge(turn)
                        return True

        # --- Find available empty slots ---
        available_slots = [
            (d, t)
            for d in range(DAYS)
            for t in range(TIME_SLOTS_PER_DAY)
            if self.matrix[d][t].is_empty_slot()
        ]
        random.shuffle(available_slots)

        # --- Placement attempt ---
        for d, t in available_slots:
            fixed_room = self._get_fixed_room(turn, d, t)
            if fixed_room:
                candidate_rooms = [fixed_room]
            else:
                if required_room_type:
                    preferred_rooms = [r for r in self.rooms if r.room_type_code in required_room_type]
                    fallback_rooms  = [r for r in self.rooms if r.room_type_code not in required_room_type]
                    candidate_rooms = preferred_rooms if preferred_rooms else fallback_rooms
                else:
                    candidate_rooms = list(self.rooms)
                random.shuffle(candidate_rooms)

        # --- Placement attempt ---
        for d, t in available_slots:
            if self._has_hard_conflict(d, t, turn):
                continue
            # Para conferencias: evitar slots donde el mismo profesor
            # ya tiene otra conferencia de la misma materia (mitad del split)
            if turn.activity_type == 'C' and self._professor_has_same_subject_here(d, t, turn):
                continue
            if strict and self._violates_constraints(d, t, turn):
                continue
            for room in candidate_rooms:
                if self._room_is_free(d, t, room) and not self._room_is_unavailable(d, t, room):
                    placed_turn = copy.deepcopy(turn)
                    placed_turn.room = room
                    self.matrix[d][t] = placed_turn
                    return True

        # --- Relaxed second pass (no soft constraints) ---
        if strict:
            for d, t in available_slots:
                if self._has_hard_conflict(d, t, turn):
                    continue
                if turn.activity_type == 'C' and self._professor_has_same_subject_here(d, t, turn):
                    continue
                fixed_room = self._get_fixed_room(turn, d, t)
                if fixed_room:
                    relaxed_rooms = [fixed_room]
                else:
                    relaxed_rooms = candidate_rooms
                for room in relaxed_rooms:
                    if self._room_is_free(d, t, room) and not self._room_is_unavailable(d, t, room):
                        placed_turn = copy.deepcopy(turn)
                        placed_turn.room = room
                        self.matrix[d][t] = placed_turn
                        return True

        return False

    def _professor_has_same_subject_here(self, d: int, t: int, turn: Turn) -> bool:
        """
        Returns True si ya hay en (d,t) una conferencia del mismo profesor
        y misma materia — indica que es la otra mitad del split y NO deben
        coincidir en el mismo slot (el profesor no puede estar en dos salas).
        """
        existing = self.matrix[d][t]
        if existing.is_empty_slot():
            return False
        return (
            existing.activity_type == 'C'
            and existing.subject_alias == turn.subject_alias
            and existing.professor_id == turn.professor_id
        )

    def _get_fixed_room(self, turn: Turn, d: int = -1, t: int = -1) -> Optional[Room]:
        """
        Retorna la sala fija para un turno según la jerarquía de prioridad:

        1. Actividad específica con slot concreto
           (asignatura + tipo + (d,t) coincide en applicable_slots)
        2. Tipo de actividad de la asignatura
           (asignatura + tipo, sin restricción de slot o ALWAYS)
        3. Asignatura completa
           (solo asignatura, aplica a todos los tipos)
        4. Default por tipo de actividad
           (manejado por ACTIVITY_ROOM_TYPES — no se gestiona aquí)

        La restricción del usuario siempre tiene prioridad sobre el default.
        """
        candidates = []  # (specificity, room)

        for c in self.constraints:
            if getattr(c, 'constraint_type', None) != 'ROOM_ASSIGNMENT':
                continue
            rule = getattr(c, 'rule_data', {})

            # Verificar si aplica a este turno
            subject_match = (rule.get('subject_alias') == turn.subject_alias
                             and turn.subject_alias is not None)
            prof_match    = (rule.get('professor_id') is not None
                             and str(rule.get('professor_id')) == str(turn.professor_id))

            if not subject_match and not prof_match:
                continue

            rule_act = rule.get('activity_type')  # None = todos los tipos
            if rule_act is not None and rule_act != turn.activity_type:
                continue

            # Verificar patrón de slot
            applicable = rule.get('applicable_slots', set())
            slot_matches_specific = (d >= 0 and t >= 0 and applicable and (d, t) in applicable)
            slot_is_always        = not applicable  # sin restricción de slot

            if applicable and not slot_matches_specific:
                continue  # Patrón definido pero este slot no está incluido

            # Calcular especificidad (mayor = más prioritario)
            specificity = 0
            if slot_matches_specific:
                specificity += 4  # Nivel 1: slot concreto
            if rule_act is not None:
                specificity += 2  # Nivel 2: tipo de actividad especificado
            if subject_match:
                specificity += 1  # subject > professor en igualdad

            room_id = rule.get('room_id')
            for r in self.rooms:
                if str(r.id) == str(room_id):
                    candidates.append((specificity, r))
                    break

        if not candidates:
            return None

        # Retornar la sala del candidato más específico
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # ------------------------------------------------------------------
    # Conflict detection helpers
    # ------------------------------------------------------------------

    def _violates_constraints(self, d: int, t: int, turn: Turn) -> bool:
        """
        Returns True if placing this turn at (d, t) would violate any
        UNAVAILABILITY or TIME_SLOT_PREFERENCE constraint with priority >= 3.
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

    def _room_is_unavailable(self, d: int, t: int, room: Room) -> bool:
        """Returns True if a ROOM UNAVAILABILITY constraint blocks this room at (d,t)."""
        for c in self.constraints:
            if getattr(c, 'constraint_type', None) != 'UNAVAILABILITY':
                continue
            if getattr(c, 'target_type', None) != 'ROOM':
                continue
            if getattr(c, 'target_id', None) != room.id:
                continue
            if (d, t) in getattr(c, 'blocked_slots', set()):  # t is 0-indexed here
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
    # Score calculation  [10]
    # ------------------------------------------------------------------

    def _score_cell(self, d: int, t: int) -> int:
        """Compute and return the penalty for a single cell (d, t)."""
        turn = self.matrix[d][t]
        if turn.is_empty_slot():
            return 0
        cell_score = self._penalty_wrong_room_type(turn, d, t)
        for constraint in self.constraints:
            cell_score += constraint.evaluate(turn, d, t)
        return cell_score

    def calculate_score(self, abort_threshold: int = None) -> None:
        """
        Full score recalculation. Rebuilds the cell cache.
        C3: early stopping si el score supera abort_threshold.
        """
        self.score = 0

        # 1. Unplaced turns
        self.score += len(self.unscheduled_load) * PENALTY_MISSING_TURN

        # Early stop check after unplaced penalty
        if abort_threshold and self.score > abort_threshold:
            return

        # 2. Placed turns — populate cell cache
        # A3: calcular all_groups una vez para reuse en lunch penalty
        all_groups: set = set()
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                cell_score = self._score_cell(d, t)
                self._cell_scores[d][t] = cell_score
                self.score += cell_score
                # Recolectar grupos mientras iteramos
                turn = self.matrix[d][t]
                if not turn.is_empty_slot():
                    all_groups.update(turn.group_codes)

                # C3: early stopping dentro del bucle
                if abort_threshold and self.score > abort_threshold:
                    return

        # 3. Lunch break (global, not per-cell) - A3: pasar all_groups
        self.score += self._penalty_lunch_break(all_groups)

        # 4. Day imbalance penalty
        self.score += self._penalty_day_imbalance()

    def calculate_score_after_swap(self, d1: int, t1: int, d2: int, t2: int) -> None:
        """
        [10] Efficient score update after a swap mutation.
        Only recomputes the two swapped cells and the lunch-break penalty.
        All other cell scores are read from the cache.
        """
        # Remove old contribution of swapped cells
        self.score -= self._cell_scores[d1][t1]
        self.score -= self._cell_scores[d2][t2]

        # Recompute new scores for those cells
        new_score_1 = self._score_cell(d1, t1)
        new_score_2 = self._score_cell(d2, t2)
        self._cell_scores[d1][t1] = new_score_1
        self._cell_scores[d2][t2] = new_score_2

        self.score += new_score_1 + new_score_2

        # Lunch break must be fully recomputed (it's global)
        # A3: calcular all_groups para reuse
        all_groups: set = set()
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                turn = self.matrix[d][t]
                if not turn.is_empty_slot():
                    all_groups.update(turn.group_codes)

        self.score = (
            self.score
            - self._last_lunch_penalty
            + self._penalty_lunch_break(all_groups)
        )
        # Day imbalance: un swap de dos celdas ocupadas no cambia conteos por día,
        # por lo que la penalización de desequilibrio no varía — no hay que recalcularla.

    def _penalty_wrong_room_type(self, turn: Turn, d: int = -1, t: int = -1) -> int:
        """
        Valida que el tipo de aula sea compatible con el tipo de actividad.
        Penalización crítica (INCOMPATIBLE_ROOM) si el tipo no coincide.
        EXCEPCIÓN: si hay una restricción ROOM_ASSIGNMENT del usuario que
        fuerza esa sala en ese slot, no se penaliza.
        """
        if turn.room is None or turn.activity_type is None:
            return 0

        allowed_types = ACTIVITY_ROOM_TYPES.get(turn.activity_type)
        if allowed_types and turn.room.room_type_code not in allowed_types:
            fixed = self._get_fixed_room(turn, d, t)
            if fixed and fixed.id == turn.room.id:
                return 0  # Sala forzada por el usuario — no penalizar
            return PENALTY_INCOMPATIBLE_ROOM

        return 0

    def _penalty_lunch_break(self, all_groups: set) -> int:
        """A3: all_groups calculado una vez en calculate_score()."""
        penalty = 0
        for group in all_groups:
            for d in range(DAYS):
                slot3_free = self.matrix[d][2].is_empty_slot() or group not in self.matrix[d][2].group_codes
                slot4_free = self.matrix[d][3].is_empty_slot() or group not in self.matrix[d][3].group_codes
                if not slot3_free and not slot4_free:
                    penalty += PENALTY_LUNCH_MISSING

        self._last_lunch_penalty = penalty
        return penalty

    def _penalty_day_imbalance(self) -> int:
        """
        Penaliza la distribución desigual de turnos entre los días de la semana.
        Calcula la desviación de cada día respecto al ideal (total/5) y
        acumula PENALTY_DAY_IMBALANCE por cada slot de diferencia.
        """
        day_counts = [0] * DAYS
        total = 0
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                if not self.matrix[d][t].is_empty_slot():
                    day_counts[d] += 1
                    total += 1

        if total == 0:
            return 0

        ideal = total / DAYS
        penalty = sum(int(abs(count - ideal) * PENALTY_DAY_IMBALANCE)
                      for count in day_counts)
        return penalty

    # ------------------------------------------------------------------
    # GA operators
    # ------------------------------------------------------------------

    def _try_reassign_room(self, d: int, t: int) -> None:
        """
        Tras un crossover, intenta reasignar una sala del tipo correcto al turno (d,t).
        Si el turno ya tiene la sala correcta, no hace nada.
        Si encuentra una sala del tipo correcto libre, la asigna.
        """
        turn = self.matrix[d][t]
        if turn.is_empty_slot() or turn.room is None:
            return
        required = ACTIVITY_ROOM_TYPES.get(turn.activity_type)
        if not required or turn.room.room_type_code in required:
            return  # ya está en la sala correcta

        # Buscar sala correcta libre en este slot
        for room in random.sample(self.rooms, len(self.rooms)):
            if room.room_type_code in required and self._room_is_free(d, t, room):
                turn.room = room
                return

    def fusion(self, partner_matrix: List[List[Turn]]) -> None:
        for d in range(DAYS):
            for t in range(TIME_SLOTS_PER_DAY):
                if random.random() < 0.5:
                    self.matrix[d][t] = copy.deepcopy(partner_matrix[d][t])
                    # Intentar corregir el tipo de sala inmediatamente
                    self._try_reassign_room(d, t)

    def mutate(self) -> None:
        """Swap two randomly chosen occupied cells."""
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