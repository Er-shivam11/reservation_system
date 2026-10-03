from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.reservations import router as reservations_router
from app.api.shows import router as shows_router
from app.api.show_state import router as show_state_router
from app.metrics import instrumentator
from app.middleware.request_id import RequestIDMiddleware


app = FastAPI(
    title="Seat Reservation Service",
    version="1.0.0",
)

app.add_middleware(RequestIDMiddleware)

app.include_router(shows_router)
app.include_router(reservations_router)
app.include_router(show_state_router)
app.include_router(health_router)

instrumentator.instrument(app).expose(
    app,
    endpoint="/metrics",
)


@app.get("/")
def root():
    return {
        "service": "seat-reservation",
        "status": "running",
    }