import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ShowSeat(Base):
    __tablename__ = "show_seats"

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

    seat_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="available",
    )

    reserved_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    show = relationship(
        "Show",
        back_populates="seats",
    )

    __table_args__ = (
        UniqueConstraint(
            "show_id",
            "seat_number",
            name="uq_show_seat",
        ),
        Index(
            "ix_show_seats_show_status",
            "show_id",
            "status",
        ),
        CheckConstraint(
            "status IN ('available', 'held', 'confirmed')",
            name="ck_show_seats_status",
        ),
    )