from apps.data_management.models import Schedule, TimeSlot, AssignedEvent

for s in Schedule.objects.all():
    for ts in TimeSlot.objects.filter(schedule=s):
        for ae in AssignedEvent.objects.filter(time_slot=ts):
            if ae.docent_event:
                ae.docent_event.delete()
            ae.delete()
        ts.delete()
    s.delete()

print("Schedules restantes:", Schedule.objects.count())
print("TimeSlots restantes:", TimeSlot.objects.count())
print("Borrado completado.")