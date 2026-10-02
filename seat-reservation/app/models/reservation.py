import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    show_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shows.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    amount_paise: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="confirmed",
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "show_id",
            "user_id",
            "idempotency_key",
            name="uq_reservation_idempotency",
        ),
        Index(
            "ix_reservations_show_user_status",
            "show_id",
            "user_id",
            "status",
        ),
        CheckConstraint(
            "amount_paise >= 0",
            name="ck_reservations_amount_non_negative",
        ),
        CheckConstraint(
            "status IN ('confirmed', 'cancelled')",
            name="ck_reservations_status",
        ),
    )


class ReservationSeat(Base):
    __tablename__ = "reservation_seats"

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reservations.id", ondelete="CASCADE"),
        primary_key=True,
    )

    seat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("show_seats.id", ondelete="CASCADE"),
        primary_key=True,
    )

    
class ShowUserCounter(Base):
    __tablename__ = "show_user_counters"

    show_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shows.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )

    seat_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    __table_args__ = (
        CheckConstraint(
            "seat_count >= 0",
            name="ck_show_user_counter_non_negative",
        ),
    )