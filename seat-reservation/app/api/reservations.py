from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database import get_db
from app.schemas.reservation import (
    CancelResponse,
    ReservationCreate,
    ReservationResponse,
)
from app.services.reservation_service import (
    cancel_reservation,
    reserve_seats,
)

router = APIRouter(tags=["reservations"])


@router.post(
    "/shows/{show_id}/reserve",
    response_model=ReservationResponse,
    status_code=201,
)
def create_reservation(
    show_id: UUID,
    payload: ReservationCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation = reserve_seats(
        db=db,
        show_id=show_id,
        user_id=user_id,
        seat_numbers=payload.seats,
        idempotency_key=idempotency_key,
    )

    return {
        "id": reservation.id,
        "show_id": reservation.show_id,
        "user_id": reservation.user_id,
        "amount_paise": reservation.amount_paise,
        "status": reservation.status,
        "seats": payload.seats,
    }


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=CancelResponse,
)
def cancel(
    reservation_id: UUID,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation = cancel_reservation(
        db=db,
        reservation_id=reservation_id,
        user_id=user_id,
    )

    return {
        "id": reservation.id,
        "status": reservation.status,
    }