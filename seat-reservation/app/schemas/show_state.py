from uuid import UUID

from pydantic import BaseModel


class SeatState(BaseModel):
    seat_number: str
    status: str


class ShowStateResponse(BaseModel):
    id: UUID
    name: str
    price_paise: int
    total_seats: int
    available: int
    held: int
    confirmed: int
    seats: list[SeatState]