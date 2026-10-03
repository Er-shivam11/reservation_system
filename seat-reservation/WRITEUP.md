# Seat Reservation at Scale

Production-ready seat reservation API built with **FastAPI + PostgreSQL**, designed for concurrent reservations with transaction safety, idempotency, per-user limits, cancellation, observability, and load testing.

## Live Deployment

**Base URL**

https://reservationsystem-production-41a7.up.railway.app

### Live Endpoints

- **API Documentation:**  
  https://reservationsystem-production-41a7.up.railway.app/docs

- **Liveness:**  
  https://reservationsystem-production-41a7.up.railway.app/health/live

- **Readiness:**  
  https://reservationsystem-production-41a7.up.railway.app/health/ready

- **Prometheus Metrics:**  
  https://reservationsystem-production-41a7.up.railway.app/metrics

## Source Code

**GitHub Repository:**  
https://github.com/Er-shivam11/reservation_system

## Live Demo Data

A sample show can be created using `POST /shows` with:

```json
{
  "name": "Paytm Reservation Demo",
  "seats": [
    "A1",
    "A2",
    "A3",
    "A4",
    "A5",
    "B1",
    "B2",
    "B3",
    "B4",
    "B5"
  ],
  "price_paise": 25000
}
```

This creates:

- 1 show in `shows`
- 10 seats in `show_seats`

After making a reservation, the related records can be verified in:

- `reservations`
- `reservation_seats`
- `show_user_counters`

The resulting `show_id` is returned by the API and can be used with:

```text
GET /shows/{show_id}
POST /shows/{show_id}/reserve
POST /reservations/{reservation_id}/cancel
```

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker
- Prometheus metrics
- Railway

## Implemented Features

- Create shows and seats
- Token-based authentication
- Concurrent seat reservation
- PostgreSQL row-level locking
- Deterministic seat locking
- No double-selling
- Per-user reservation limit
- Idempotency keys
- Idempotency request-body validation
- All-or-nothing multi-seat reservation
- Reservation cancellation
- Seat re-booking after cancellation
- Show seat-state API
- Reconciliation invariant
- Liveness and readiness health checks
- Prometheus metrics
- Structured JSON request logs
- Request/correlation IDs
- Concurrent burst testing

## Correctness Under Concurrency

The reservation transaction uses PostgreSQL row locking:

```text
Request
   ↓
Authenticate user
   ↓
Validate request
   ↓
Lock user reservation counter
   ↓
Lock requested seats in deterministic order
   ↓
Check per-user limit
   ↓
Check seat availability
   ↓
Create reservation
   ↓
Confirm seats
   ↓
Commit transaction
```

This ensures that concurrent requests cannot successfully reserve the same seat.

## Idempotency

Each reservation requires an `Idempotency-Key`.

- Same user + same key + same request → original reservation is returned.
- Same user + same key + different request → `409 Conflict`.
- Concurrent retries with the same key produce a single reservation.

## Per-User Limit

The default reservation limit is **4 seats per user**.

The limit is protected using a database counter locked with `SELECT ... FOR UPDATE`, making the check safe under concurrent requests.

## Cancellation

Users can cancel their own confirmed reservations.

Cancellation:

1. Locks the reservation.
2. Locks associated seats.
3. Releases the seats.
4. Decrements the user's reservation counter.
5. Commits atomically.

Released seats can then be reserved again.

## Show State

`GET /shows/{show_id}` returns:

- Every seat
- Seat status
- Available count
- Held count
- Confirmed count
- Total seat count

The reconciliation invariant is:

```text
available + held + confirmed = total seats
```

## Burst Test

Run locally:

```bash
python scripts/burst.py http://localhost:8000
```

Run against the live service:

```bash
python scripts/burst.py https://reservationsystem-production-41a7.up.railway.app
```

The burst test covers:

- 500-user hot-seat storm
- Per-user concurrency limit
- Idempotency retries
- Final seat reconciliation

### Verified Local Result

```text
=== HOT-SEAT STORM ===
201: 1
409: 499
5xx: 0

=== PER-USER LIMIT ===
201: 4
409: 6
5xx: 0

=== IDEMPOTENCY RETRY ===
201/200: 20
409: 0
Unique reservation IDs: 1

=== FINAL RECONCILIATION ===
Total:     100
Available: 94
Held:      0
Confirmed: 6
Calculated total: 100

BURST TEST PASSED
```

## Health Checks

### Liveness

```text
GET /health/live
```

Confirms that the application process is running.

### Readiness

```text
GET /health/ready
```

Checks PostgreSQL connectivity and fails with `503` when the database is unavailable.

## Observability

Prometheus metrics are available at:

```text
GET /metrics
```

Implemented metrics include:

- Confirmed reservations
- Declined reservations by reason
- Available seats
- Reservation latency
- HTTP request metrics

Requests also include structured JSON logging and an `X-Request-ID` correlation ID.

## Deployment

The application is containerized using Docker and deployed on Railway.

Database schema is managed using Alembic migrations.

## Project Structure

```text
seat-reservation/
├── app/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── middleware/
│   ├── config.py
│   ├── database.py
│   ├── metrics.py
│   └── main.py
├── tests/
├── scripts/
│   └── burst.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
└── README.md
```

## Local Setup

```bash
docker compose up --build
```

Run tests:

```bash
pytest
```

API documentation:

```text
http://localhost:8000/docs
```

## AI Usage

AI assistance was used during development for architecture discussion, implementation guidance, debugging, test design, documentation, and review.

All application code was reviewed, executed, tested, and validated by the developer.

## Submission

**Live API:**  
https://reservationsystem-production-41a7.up.railway.app

**GitHub:**  
https://github.com/Er-shivam11/reservation_system

**Swagger:**  
https://reservationsystem-production-41a7.up.railway.app/docs

**Metrics:**  
https://reservationsystem-production-41a7.up.railway.app/metrics