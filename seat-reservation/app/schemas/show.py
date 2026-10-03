from uuid import UUID

from pydantic import BaseModel, Field


class ShowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    seats: list[str] = Field(min_length=1)
    price_paise: int = Field(ge=0)


class ShowResponse(BaseModel):
    id: UUID
    name: str
    price_paise: int
    total_seats: int

    model_config = {"from_attributes": True}