from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.metrics import update_available_seats
from app.models import Show, ShowSeat
from app.schemas.show import ShowCreate, ShowResponse

router = APIRouter(prefix="/shows", tags=["shows"])


@router.post(
    "",
    response_model=ShowResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_show(
    payload: ShowCreate,
    db: Session = Depends(get_db),
):
    seats = [seat.strip() for seat in payload.seats]

    if any(not seat for seat in seats):
        raise HTTPException(
            status_code=400,
            detail="Seat numbers cannot be empty",
        )

    if len(seats) != len(set(seats)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate seat numbers are not allowed",
        )

    show = Show(
        name=payload.name,
        price_paise=payload.price_paise,
        total_seats=len(seats),
    )

    db.add(show)
    db.flush()

    for seat_number in seats:
        db.add(
            ShowSeat(
                show_id=show.id,
                seat_number=seat_number,
                status="available",
            )
        )

    db.commit()
    update_available_seats(db, show.id)
    db.refresh(show)

    return show