# scheduler_core/dto/room.py
import uuid
from typing import Literal

# Mapeo de RoomType del ORM
RoomTypeCode = Literal['A','S','L', 'P'] # A=Classroom, S=Conference, L=Laboratory, P=Custom

class Room:
    """DTO for the Room model."""
    id: uuid.UUID
    room_type_code: RoomTypeCode
    number: str
    capacity: int

    def __init__(self, id: uuid.UUID, room_type_code: RoomTypeCode, number: str, capacity: int = 30):
        self.id = id
        self.room_type_code = room_type_code
        self.number = number
        self.capacity = capacity

    def __str__(self):
        return f'{self.room_type_code}{self.number}'