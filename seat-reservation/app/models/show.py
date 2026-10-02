import uuid

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Show(Base):
    __tablename__ = "shows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    price_paise: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    per_user_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4,
    )

    total_seats: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    seats = relationship(
        "ShowSeat",
        back_populates="show",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "price_paise >= 0",
            name="ck_shows_price_non_negative",
        ),
        CheckConstraint(
            "per_user_limit > 0",
            name="ck_shows_per_user_limit_positive",
        ),
        CheckConstraint(
            "total_seats > 0",
            name="ck_shows_total_seats_positive",
        ),
    )