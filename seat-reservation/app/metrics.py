from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator


instrumentator = Instrumentator()

RESERVATIONS_CONFIRMED = Counter(
    "reservations_confirmed_total",
    "Total number of confirmed reservations",
)

RESERVATIONS_DECLINED = Counter(
    "reservations_declined_total",
    "Total number of declined/replayed reservation requests",
    ["reason"],
)

AVAILABLE_SEATS = Gauge(
    "seats_available",
    "Currently available seats for a show",
    ["show_id"],
)

RESERVATION_LATENCY = Histogram(
    "reservation_latency_seconds",
    "Reservation operation latency in seconds",
)


def update_available_seats(db, show_id):
    from sqlalchemy import func, select

    from app.models import ShowSeat

    available = db.scalar(
        select(func.count())
        .select_from(ShowSeat)
        .where(
            ShowSeat.show_id == show_id,
            ShowSeat.status == "available",
        )
    )

    AVAILABLE_SEATS.labels(
        show_id=str(show_id)
    ).set(available or 0)