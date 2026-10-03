from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Show, ShowSeat
from app.schemas.show_state import (
    SeatState,
    ShowStateResponse,
)

router = APIRouter(tags=["shows"])


@router.get(
    "/shows/{show_id}",
    response_model=ShowStateResponse,
)
def get_show_state(
    show_id: UUID,
    db: Session = Depends(get_db),
):
    show = db.get(Show, show_id)

    if not show:
        raise HTTPException(
            status_code=404,
            detail="Show not found",
        )

    seats = db.scalars(
        select(ShowSeat)
        .where(ShowSeat.show_id == show_id)
        .order_by(ShowSeat.seat_number)
    ).all()

    available = sum(
        1 for seat in seats if seat.status == "available"
    )

    held = sum(
        1 for seat in seats if seat.status == "held"
    )

    confirmed = sum(
        1 for seat in seats if seat.status == "confirmed"
    )

    return {
        "id": show.id,
        "name": show.name,
        "price_paise": show.price_paise,
        "total_seats": show.total_seats,
        "available": available,
        "held": held,
        "confirmed": confirmed,
        "seats": [
            SeatState(
                seat_number=seat.seat_number,
                status=seat.status,
            )
            for seat in seats
        ],
    }