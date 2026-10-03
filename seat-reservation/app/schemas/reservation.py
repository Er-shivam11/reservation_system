from uuid import UUID

from pydantic import BaseModel, Field


class ReservationCreate(BaseModel):
    seats: list[str] = Field(min_length=1)


class ReservationResponse(BaseModel):
    id: UUID
    show_id: UUID
    user_id: str
    amount_paise: int
    status: str
    seats: list[str]

class CancelResponse(BaseModel):
    id: UUID
    status: str