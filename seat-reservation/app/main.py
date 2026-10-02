from fastapi import FastAPI

app = FastAPI(
    title="Seat Reservation Service",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "service": "seat-reservation",
        "status": "running",
    }


@app.get("/health/live")
def liveness():
    return {"status": "alive"}