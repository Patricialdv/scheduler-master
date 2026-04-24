"""
train_ga.py — Script de entrenamiento / tuning de hiperparámetros del GA.

Uso:
    python train_ga.py

    No requiere Django ni base de datos. Usa datos sintéticos con
    PRE-MERGE de conferencias, igual que hace main.py en producción.

Requisitos:
    pip install tabulate
"""

import random
import copy
import time
from itertools import product
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# DTOs standalone
# ---------------------------------------------------------------------------

class Room:
    def __init__(self, id, room_type_code, number):
        self.id = id
        self.room_type_code = room_type_code
        self.number = number


class Turn:
    def __init__(self, subject_alias=None, group_codes=None, activity_type=None,
                 professor_id=None, source_assignment_ids=None, room=None):
        if subject_alias is not None:
            self.subject_alias = subject_alias
            self.group_codes = group_codes or []
            self.activity_type = activity_type
            self.professor_id = professor_id
            self.source_assignment_ids = source_assignment_ids or []
            self.room = room
            self.is_empty = False
        else:
            self.subject_alias = None
            self.group_codes = []
            self.activity_type = None
            self.professor_id = None
            self.source_assignment_ids = []
            self.room = None
            self.is_empty = True

    def is_empty_slot(self):
        return self.is_empty


# ---------------------------------------------------------------------------
# Datos sintéticos con pre-merge [A]
# ---------------------------------------------------------------------------

SUBJECTS   = ['PROG1', 'PROG2', 'MATD', 'ALG', 'ARQC', 'BD', 'SOP']
LAB_SUBJS  = {'PROG1', 'MATD', 'BD'}
GROUPS     = ['G1', 'G2', 'G3', 'G4']
PROFESSORS = [f'P{i}' for i in range(15)]

ROOMS = [
    Room('S1', 'S', 'S01'), Room('S2', 'S', 'S02'), Room('S3', 'S', 'S03'),
    Room('A1', 'A', 'A01'), Room('A2', 'A', 'A02'),
    Room('A3', 'A', 'A03'), Room('A4', 'A', 'A04'),
    Room('L1', 'L', 'L01'), Room('L2', 'L', 'L02'), Room('L3', 'L', 'L03'),
]


def make_turns() -> List[Turn]:
    """
    [A] Pre-merge aplicado igual que en main.py:
        - Conferencias: 1 Turn merged por asignatura (todos los grupos juntos)
        - Clases Prácticas: 1 Turn por grupo
        - Laboratorios: 1 Turn por grupo (solo LAB_SUBJS)

    Turnos que entran al GA:
        7 conf  (merged, 4 grupos c/u)  → 7 celdas en la matriz
        28 cp   (7 × 4)                 → 28 celdas (pero con conflictos de prof/grupo)
        12 lab  (3 × 4)                 → 12 celdas
        Total: 47 turnos → realista para la matriz de 30
    """
    conf_profs = {s: random.choice(PROFESSORS) for s in SUBJECTS}
    half = len(GROUPS) // 2
    turns = []

    for subj in SUBJECTS:
        cp_profs  = random.sample([p for p in PROFESSORS if p != conf_profs[subj]], k=2)
        lab_profs = random.sample(
            [p for p in PROFESSORS if p != conf_profs[subj] and p not in cp_profs], k=2
        )

        # Una conferencia merged con todos los grupos
        turns.append(Turn(
            subject_alias=subj,
            group_codes=list(GROUPS),
            activity_type='C',
            professor_id=conf_profs[subj],
            source_assignment_ids=[f'{subj}_C_{g}' for g in GROUPS],
        ))

        for i, grp in enumerate(GROUPS):
            turns.append(Turn(
                subject_alias=subj, group_codes=[grp],
                activity_type='CP',
                professor_id=cp_profs[0] if i < half else cp_profs[1],
                source_assignment_ids=[f'{subj}_CP_{grp}'],
            ))
            if subj in LAB_SUBJS:
                turns.append(Turn(
                    subject_alias=subj, group_codes=[grp],
                    activity_type='L',
                    professor_id=lab_profs[0] if i < half else lab_profs[1],
                    source_assignment_ids=[f'{subj}_L_{grp}'],
                ))

    return turns


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

class FakeConstraint:
    def __init__(self, target_id, blocked_slots):
        self.constraint_type = 'UNAVAILABILITY'
        self.target_type = 'PROFESSOR'
        self.target_id = target_id
        self.blocked_slots = blocked_slots
        self.priority = 3
        self.penalty_base = 5000
        self.rule_data = {}

    def evaluate(self, turn, day, slot):
        if turn.is_empty_slot() or (day, slot) not in self.blocked_slots:
            return 0
        if turn.professor_id != self.target_id:
            return 0
        return self.penalty_base


def make_constraints():
    return [
        FakeConstraint('P0', {(4, 4), (4, 5)}),
        FakeConstraint('P1', {(0, 0), (0, 1), (2, 0), (2, 1)}),
        FakeConstraint('P2', {(3, i) for i in range(6)}),
    ]


# ---------------------------------------------------------------------------
# GA inline
# ---------------------------------------------------------------------------

DAYS = 5
SLOTS = 6
PENALTY_MISSING  = 500
PENALTY_WRONG_RT = 50_000
PENALTY_LUNCH    = 10_000
ACTIVITY_ROOM    = {'C': 'S', 'CP': 'A', 'L': 'L'}


class ScheduleMatrix:
    def __init__(self, rooms, constraints, turns):
        self.rooms = rooms
        self.constraints = constraints
        self.unscheduled = copy.deepcopy(turns)
        self.matrix = [[Turn() for _ in range(SLOTS)] for _ in range(DAYS)]
        self.score = 0

    def place_all(self):
        random.shuffle(self.unscheduled)
        unplaced = []
        for turn in self.unscheduled:
            if not self._place(turn):
                unplaced.append(turn)
        self.unscheduled = unplaced

    def _place(self, turn):
        req = ACTIVITY_ROOM.get(turn.activity_type)
        slots = [(d, t) for d in range(DAYS) for t in range(SLOTS)
                 if self.matrix[d][t].is_empty_slot()]
        random.shuffle(slots)
        preferred  = [r for r in self.rooms if r.room_type_code == req]
        fallback   = [r for r in self.rooms if r.room_type_code != req]
        candidates = preferred if preferred else fallback
        random.shuffle(candidates)
        for d, t in slots:
            if self._conflict(d, t, turn):
                continue
            for room in candidates:
                if self._room_free(d, t, room):
                    pt = copy.deepcopy(turn)
                    pt.room = room
                    self.matrix[d][t] = pt
                    return True
        return False

    def _conflict(self, d, t, turn):
        e = self.matrix[d][t]
        if e.is_empty_slot():
            return False
        if turn.professor_id and e.professor_id == turn.professor_id:
            return True
        for gc in turn.group_codes:
            if gc in e.group_codes:
                return True
        return False

    def _room_free(self, d, t, room):
        e = self.matrix[d][t]
        return e.is_empty_slot() or (e.room is None or e.room.id != room.id)

    def calc_score(self):
        self.score = len(self.unscheduled) * PENALTY_MISSING
        groups = set()
        for d in range(DAYS):
            for t in range(SLOTS):
                turn = self.matrix[d][t]
                if turn.is_empty_slot():
                    continue
                groups.update(turn.group_codes)
                req = ACTIVITY_ROOM.get(turn.activity_type)
                if turn.room and req and turn.room.room_type_code != req:
                    self.score += PENALTY_WRONG_RT
                for c in self.constraints:
                    self.score += c.evaluate(turn, d, t)
        for grp in groups:
            for d in range(DAYS):
                s3 = self.matrix[d][2].is_empty_slot() or grp not in self.matrix[d][2].group_codes
                s4 = self.matrix[d][3].is_empty_slot() or grp not in self.matrix[d][3].group_codes
                if not s3 and not s4:
                    self.score += PENALTY_LUNCH

    def fusion(self, other_matrix):
        for d in range(DAYS):
            for t in range(SLOTS):
                if random.random() < 0.5:
                    self.matrix[d][t] = copy.deepcopy(other_matrix[d][t])

    def mutate(self):
        occupied = [(d, t) for d in range(DAYS) for t in range(SLOTS)
                    if not self.matrix[d][t].is_empty_slot()]
        if len(occupied) >= 2:
            (d1, t1), (d2, t2) = random.sample(occupied, 2)
            self.matrix[d1][t1], self.matrix[d2][t2] = self.matrix[d2][t2], self.matrix[d1][t1]


def run_ga(turns, rooms, constraints, params: Dict[str, Any]) -> Dict[str, Any]:
    pop_size       = params['POPULATION_SIZE']
    elite_size     = params['ELITE_SIZE']
    mutation_count = params['MUTATION_COUNT']
    max_epochs     = params['MAX_EPOCHS']
    time_limit     = params['TIME_LIMIT_SECONDS']
    stagnation     = params['STAGNATION_LIMIT']
    threshold      = params['SCORE_THRESHOLD']

    start = time.time()

    population = []
    for _ in range(pop_size):
        ind = ScheduleMatrix(rooms, constraints, turns)
        ind.place_all()
        ind.calc_score()
        population.append(ind)

    population.sort(key=lambda x: x.score)
    best_score = population[0].score
    no_improve = 0
    epoch = 0

    while True:
        if time.time() - start >= time_limit:
            break

        population.sort(key=lambda x: x.score)
        elite   = population[:elite_size]
        new_pop = copy.deepcopy(elite)

        while len(new_pop) < pop_size:
            p1 = random.choice(elite)
            p2 = random.choice(elite)
            if p1 is p2:
                continue
            child = copy.deepcopy(p1)
            child.fusion(p2.matrix)
            child.calc_score()
            new_pop.append(child)

        new_pop.sort(key=lambda x: x.score)

        for idx in range(elite_size - mutation_count, elite_size):
            candidate = copy.deepcopy(new_pop[idx])
            orig = candidate.score
            candidate.mutate()
            candidate.calc_score()
            if candidate.score < orig:
                new_pop[idx] = candidate

        new_pop.sort(key=lambda x: x.score)
        population = new_pop
        epoch += 1

        current_best = population[0].score
        if current_best == 0:
            break
        if current_best < best_score:
            best_score = current_best
            no_improve = 0
        else:
            no_improve += 1

        if no_improve >= stagnation:
            fresh = [ScheduleMatrix(rooms, constraints, turns) for _ in range(10)]
            for f in fresh:
                f.place_all()
                f.calc_score()
            population[-10:] = fresh
            population.sort(key=lambda x: x.score)
            no_improve = 0

        if epoch >= max_epochs:
            if current_best <= threshold:
                break
            if epoch >= max_epochs * 2:
                break

    return {
        'score':    population[0].score,
        'epochs':   epoch,
        'elapsed':  round(time.time() - start, 2),
        'unplaced': len(population[0].unscheduled),
    }


# ---------------------------------------------------------------------------
# Grid de parámetros
# ---------------------------------------------------------------------------

PARAM_GRID = {
    'POPULATION_SIZE':    [50, 100, 150],
    'ELITE_SIZE':         [10, 20, 30],
    'MUTATION_COUNT':     [3, 5, 8],
    'MAX_EPOCHS':         [200, 300, 500],
    'TIME_LIMIT_SECONDS': [60],
    'STAGNATION_LIMIT':   [30, 50],
    'SCORE_THRESHOLD':    [1000],
}

RUNS_PER_CONFIG = 3


def main():
    print('=' * 70)
    print('  GA Hyperparameter Tuning  [con pre-merge de conferencias]')
    print('=' * 70)

    turns       = make_turns()
    rooms       = ROOMS
    constraints = make_constraints()

    print(f'Turns: {len(turns)} '
          f'(conf={len([t for t in turns if t.activity_type=="C"])}, '
          f'cp={len([t for t in turns if t.activity_type=="CP"])}, '
          f'lab={len([t for t in turns if t.activity_type=="L"])})')
    print(f'Rooms: {len(rooms)} | Constraints: {len(constraints)}')

    keys         = list(PARAM_GRID.keys())
    values       = list(PARAM_GRID.values())
    combinations = list(product(*values))
    total        = len(combinations)
    print(f'Combinaciones: {total} × {RUNS_PER_CONFIG} = {total * RUNS_PER_CONFIG} runs\n')

    results = []

    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        scores, ep_list, t_list = [], [], []

        for _ in range(RUNS_PER_CONFIG):
            r = run_ga(turns, rooms, constraints, params)
            scores.append(r['score'])
            ep_list.append(r['epochs'])
            t_list.append(r['elapsed'])

        avg_score   = sum(scores) / len(scores)
        avg_epochs  = sum(ep_list) / len(ep_list)
        avg_elapsed = sum(t_list) / len(t_list)
        best_run    = min(scores)

        results.append({
            'params': params, 'avg_score': round(avg_score, 1),
            'best_score': best_run, 'avg_epochs': round(avg_epochs, 1),
            'avg_elapsed': round(avg_elapsed, 2),
        })

        print(f'[{i+1}/{total}] pop={params["POPULATION_SIZE"]:3} '
              f'elite={params["ELITE_SIZE"]:2} mut={params["MUTATION_COUNT"]} '
              f'epochs={params["MAX_EPOCHS"]:3} stag={params["STAGNATION_LIMIT"]:2} | '
              f'avg={avg_score:8.1f} best={best_run:6} t={avg_elapsed:.1f}s')

    results.sort(key=lambda r: (r['avg_score'], r['avg_elapsed']))

    print('\n' + '=' * 70)
    print('  TOP 10 CONFIGURACIONES')
    print('=' * 70)

    try:
        from tabulate import tabulate
        table = [[rank,
            r['params']['POPULATION_SIZE'], r['params']['ELITE_SIZE'],
            r['params']['MUTATION_COUNT'],  r['params']['MAX_EPOCHS'],
            r['params']['STAGNATION_LIMIT'], r['avg_score'],
            r['best_score'], r['avg_epochs'], r['avg_elapsed']]
            for rank, r in enumerate(results[:10], 1)]
        print(tabulate(table,
            headers=['#','POP','ELITE','MUT','EPOCHS','STAG',
                     'AVG_SCORE','BEST','AVG_EP','AVG_T(s)'],
            tablefmt='rounded_outline'))
    except ImportError:
        for rank, r in enumerate(results[:10], 1):
            p = r['params']
            print(f"{rank:2}. POP={p['POPULATION_SIZE']:3} ELITE={p['ELITE_SIZE']:2} "
                  f"MUT={p['MUTATION_COUNT']} EPOCHS={p['MAX_EPOCHS']:3} "
                  f"STAG={p['STAGNATION_LIMIT']:2} | "
                  f"avg={r['avg_score']:8.1f} best={r['best_score']:6} "
                  f"ep={r['avg_epochs']:6.1f} t={r['avg_elapsed']:.2f}s")

    best = results[0]
    p    = best['params']
    print('\n' + '=' * 70)
    print('  RECOMENDACIÓN — copia estos valores en schedule_creator.py:')
    print('=' * 70)
    print(f"    POPULATION_SIZE    = {p['POPULATION_SIZE']}")
    print(f"    MAX_EPOCHS         = {p['MAX_EPOCHS']}")
    print(f"    ELITE_SIZE         = {p['ELITE_SIZE']}")
    print(f"    MUTATION_COUNT     = {p['MUTATION_COUNT']}")
    print(f"    SCORE_THRESHOLD    = {p['SCORE_THRESHOLD']}")
    print(f"    STAGNATION_LIMIT   = {p['STAGNATION_LIMIT']}")
    print(f"    TIME_LIMIT_SECONDS = 120")
    print()
    print(f"  Score promedio: {best['avg_score']}")
    print(f"  Mejor score individual: {best['best_score']}")
    print(f"  Tiempo promedio: {best['avg_elapsed']}s")
    print('=' * 70)


if __name__ == '__main__':
    main()