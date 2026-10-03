import hashlib
import json
from uuid import UUID
import time

from app.metrics import (
    RESERVATIONS_CONFIRMED,
    RESERVATIONS_DECLINED,
    RESERVATION_LATENCY,
    update_available_seats,
)
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Reservation,
    ReservationSeat,
    Show,
    ShowSeat,
    ShowUserCounter,
)


def _find_idempotent_reservation(
    db: Session,
    show_id: UUID,
    user_id: str,
    idempotency_key: str,
    request_hash: str,
) -> Reservation | None:
    existing = db.scalar(
        select(Reservation).where(
            Reservation.show_id == show_id,
            Reservation.user_id == user_id,
            Reservation.idempotency_key == idempotency_key,
        )
    )

    if existing and existing.request_hash != request_hash:
        RESERVATIONS_DECLINED.labels(
            reason="idempotency-conflict"
        ).inc()
        raise HTTPException(
            status_code=409,
            detail="Idempotency key already used with different request",
        )

    return existing


def build_request_hash(seat_numbers: list[str]) -> str:
    normalized_seats = sorted(set(seat_numbers))

    payload = json.dumps(
        {"seats": normalized_seats},
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(payload.encode()).hexdigest()


def reserve_seats(
    db: Session,
    show_id: UUID,
    user_id: str,
    seat_numbers: list[str],
    idempotency_key: str,
) -> Reservation:
    start_time = time.perf_counter()
    seats = sorted(set(seat.strip() for seat in seat_numbers))

    if not seats:
        raise HTTPException(
            status_code=400,
            detail="No seats requested",
        )

    request_hash = build_request_hash(seats)

    try:
        # ---------------------------------------------------------
        # 1. Idempotency check
        # ---------------------------------------------------------
        existing = _find_idempotent_reservation(
            db,
            show_id,
            user_id,
            idempotency_key,
            request_hash,
        )

        if existing:
            RESERVATIONS_DECLINED.labels(
                reason="idempotent-replay"
            ).inc()
            return existing

        # ---------------------------------------------------------
        # 2. Load show
        # ---------------------------------------------------------
        show = db.get(Show, show_id)

        if not show:
            raise HTTPException(
                status_code=404,
                detail="Show not found",
            )

        # ---------------------------------------------------------
        # 3. Create user counter row if needed
        # ---------------------------------------------------------
        stmt = (
            insert(ShowUserCounter)
            .values(
                show_id=show_id,
                user_id=user_id,
                seat_count=0,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    ShowUserCounter.show_id,
                    ShowUserCounter.user_id,
                ]
            )
        )

        db.execute(stmt)

        # ---------------------------------------------------------
        # 4. Lock user counter
        # ---------------------------------------------------------
        counter = db.scalar(
            select(ShowUserCounter)
            .where(
                ShowUserCounter.show_id == show_id,
                ShowUserCounter.user_id == user_id,
            )
            .with_for_update()
        )

        if counter is None:
            raise HTTPException(
                status_code=500,
                detail="Unable to initialize user reservation counter",
            )

        # A concurrent request with the same key may have committed while
        # this request waited for the per-user counter lock.
        existing = _find_idempotent_reservation(
            db,
            show_id,
            user_id,
            idempotency_key,
            request_hash,
        )

        if existing:
            db.rollback()
            RESERVATIONS_DECLINED.labels(
                reason="idempotent-replay"
            ).inc()
            return existing

        # ---------------------------------------------------------
        # 5. Per-user limit
        # ---------------------------------------------------------
        requested_count = len(seats)

        if counter.seat_count + requested_count > show.per_user_limit:
            RESERVATIONS_DECLINED.labels(
                reason="per-user-limit"
            ).inc()
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "per_user_limit",
                    "limit": show.per_user_limit,
                    "current": counter.seat_count,
                    "requested": requested_count,
                },
            )

        # ---------------------------------------------------------
        # 6. Lock seats in deterministic order
        # ---------------------------------------------------------
        show_seats = db.scalars(
            select(ShowSeat)
            .where(
                ShowSeat.show_id == show_id,
                ShowSeat.seat_number.in_(seats),
            )
            .order_by(ShowSeat.seat_number)
            .with_for_update(),
        ).all()

        # ---------------------------------------------------------
        # 7. Validate seat existence
        # ---------------------------------------------------------
        if len(show_seats) != len(seats):
            raise HTTPException(
                status_code=409,
                detail="One or more requested seats do not exist",
            )

        # ---------------------------------------------------------
        # 8. Validate availability
        # ---------------------------------------------------------
        unavailable = [
            seat.seat_number
            for seat in show_seats
            if seat.status != "available"
        ]

        if unavailable:
            RESERVATIONS_DECLINED.labels(
                reason="seat-taken"
            ).inc()
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "seat_unavailable",
                    "seats": unavailable,
                },
            )

        # ---------------------------------------------------------
        # 9. Create reservation
        # ---------------------------------------------------------
        reservation = Reservation(
            show_id=show_id,
            user_id=user_id,
            amount_paise=requested_count * show.price_paise,
            status="confirmed",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )

        db.add(reservation)
        db.flush()

        # ---------------------------------------------------------
        # 10. Confirm seats
        # ---------------------------------------------------------
        for seat in show_seats:
            seat.status = "confirmed"
            seat.reserved_by = user_id

            db.add(
                ReservationSeat(
                    reservation_id=reservation.id,
                    seat_id=seat.id,
                )
            )

        # ---------------------------------------------------------
        # 11. Update counter
        # ---------------------------------------------------------
        counter.seat_count += requested_count

        db.commit()
        RESERVATIONS_CONFIRMED.inc()
        update_available_seats(db, show_id)
        RESERVATION_LATENCY.observe(
            time.perf_counter() - start_time
        )
        db.refresh(reservation)

        return reservation

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        # Concurrent request may have created the same idempotency key.
        existing = db.scalar(
            select(Reservation).where(
                Reservation.show_id == show_id,
                Reservation.user_id == user_id,
                Reservation.idempotency_key == idempotency_key,
            )
        )

        if existing:
            if existing.request_hash != request_hash:
                RESERVATIONS_DECLINED.labels(
                    reason="idempotency-conflict"
                ).inc()

                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key already used with different request",
                )

            RESERVATIONS_DECLINED.labels(
                reason="idempotent-replay"
            ).inc()

            return existing

        RESERVATIONS_DECLINED.labels(
            reason="reservation-conflict"
        ).inc()
        raise HTTPException(
            status_code=409,
            detail="Reservation conflict",
        )
def cancel_reservation(
    db: Session,
    reservation_id: UUID,
    user_id: str,
) -> Reservation:
    reservation = db.scalar(
        select(Reservation)
        .where(Reservation.id == reservation_id)
        .with_for_update()
    )

    if not reservation:
        raise HTTPException(
            status_code=404,
            detail="Reservation not found",
        )

    if reservation.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Not allowed to cancel this reservation",
        )

    if reservation.status == "cancelled":
        raise HTTPException(
            status_code=409,
            detail="Reservation already cancelled",
        )

    # Lock seats belonging to this reservation
    reservation_seats = db.scalars(
        select(ReservationSeat)
        .where(
            ReservationSeat.reservation_id == reservation_id,
        )
        .with_for_update()
    ).all()

    seat_ids = [item.seat_id for item in reservation_seats]

    if seat_ids:
        show_seats = db.scalars(
            select(ShowSeat)
            .where(ShowSeat.id.in_(seat_ids))
            .order_by(ShowSeat.id)
            .with_for_update()
        ).all()
    else:
        show_seats = []

    # Lock user counter
    counter = db.scalar(
        select(ShowUserCounter)
        .where(
            ShowUserCounter.show_id == reservation.show_id,
            ShowUserCounter.user_id == user_id,
        )
        .with_for_update()
    )

    # Release seats
    for seat in show_seats:
        seat.status = "available"
        seat.reserved_by = None

    # Decrease user's seat count
    if counter:
        counter.seat_count = max(
            0,
            counter.seat_count - len(show_seats),
        )

    reservation.status = "cancelled"

    db.commit()
    update_available_seats(db, reservation.show_id)
    db.refresh(reservation)

    return reservation