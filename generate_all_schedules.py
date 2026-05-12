"""
generate_all_schedules.py
=========================
Genera (o regenera) los horarios base para todos los períodos activos.

Uso:
    python manage.py shell < generate_all_schedules.py

    O desde la shell interactiva:
    >>> exec(open('generate_all_schedules.py').read())

Opciones configurables:
    FORCE_REGENERATE = True  → borra y regenera aunque ya existan horarios
    FORCE_REGENERATE = False → salta períodos que ya tienen horario válido
"""

import time
import os
import django

# ── Configuración ────────────────────────────────────────────────────────────
FORCE_REGENERATE = True   # Cambiar a False para saltar períodos ya generados

# ── Bootstrap Django si se ejecuta como script standalone ────────────────────
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.general.settings')
    django.setup()

from apps.data_management.models import (
    Period, Schedule, TimeSlot, AssignedEvent, DocentEvent
)
from apps.scheduler_management.schedule_service import (
    _base_schedule_has_timeslots,
    _generate_base_for_period,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def delete_schedules_for_period(period):
    """Elimina todos los schedules (y su cascada) de un período."""
    for s in Schedule.objects.filter(period=period):
        for ts in TimeSlot.objects.filter(schedule=s):
            for ae in AssignedEvent.objects.filter(time_slot=ts):
                if ae.docent_event:
                    ae.docent_event.delete()
                ae.delete()
            ts.delete()
        s.delete()


def print_separator(char='─', width=60):
    print(char * width)


# ── Main ─────────────────────────────────────────────────────────────────────

periods = Period.objects.filter(is_active=True).order_by('career', 'number')
total   = periods.count()

print()
print_separator('═')
print(f"  GENERACIÓN DE HORARIOS — {total} períodos activos")
print(f"  Modo: {'FORZAR REGENERACIÓN' if FORCE_REGENERATE else 'INCREMENTAL (saltar existentes)'}")
print_separator('═')

results = {
    'generados':  [],
    'saltados':   [],
    'errores':    [],
}

for i, period in enumerate(periods, 1):
    label = str(period)
    print(f"\n[{i}/{total}] {label}")

    already_exists = _base_schedule_has_timeslots(period)

    if already_exists and not FORCE_REGENERATE:
        count = AssignedEvent.objects.filter(
            time_slot__schedule__period=period,
            time_slot__schedule__is_base=True,
        ).count()
        print(f"  ⏭  Ya existe ({count} eventos). Saltando.")
        results['saltados'].append(label)
        continue

    if already_exists and FORCE_REGENERATE:
        print("  🗑  Eliminando horario existente...")
        delete_schedules_for_period(period)

    print("  ⚙  Generando...")
    t0 = time.time()
    try:
        _generate_base_for_period(period)
        elapsed = time.time() - t0

        ae_count = AssignedEvent.objects.filter(
            time_slot__schedule__period=period,
            time_slot__schedule__is_base=True,
        ).count()
        score = Schedule.objects.filter(
            period=period, is_base=True
        ).first().score if Schedule.objects.filter(period=period, is_base=True).exists() else '?'

        print(f"  ✅ OK — {ae_count} eventos | score={score} | {elapsed:.1f}s")
        results['generados'].append((label, ae_count, score, elapsed))

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ❌ ERROR tras {elapsed:.1f}s: {e}")
        results['errores'].append((label, str(e)))

# ── Resumen ──────────────────────────────────────────────────────────────────
print()
print_separator('═')
print("  RESUMEN")
print_separator('═')
print(f"  ✅ Generados:  {len(results['generados'])}")
print(f"  ⏭  Saltados:   {len(results['saltados'])}")
print(f"  ❌ Errores:    {len(results['errores'])}")

if results['generados']:
    print()
    print("  Detalle de generados:")
    for label, ae_count, score, elapsed in results['generados']:
        print(f"    • {label}")
        print(f"      eventos={ae_count} | score={score} | tiempo={elapsed:.1f}s")

if results['errores']:
    print()
    print("  Detalle de errores:")
    for label, err in results['errores']:
        print(f"    • {label}: {err}")

print_separator('═')
print()