## 1. File structure — Django vs FastAPI

### Django version — for future

```text
seat-reservation/
│
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env
├── .gitignore
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── reservations/
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── urls.py
│   ├── services.py
│   └── tests.py
│
├── scripts/
│   └── burst.py
│
├── README.md
└── WRITEUP.md
```

Django gives us a lot automatically:

```text
Django
 ├── ORM
 ├── migrations
 ├── admin
 ├── authentication
 └── DRF
```

---

### FastAPI version — **our project**

```text
seat-reservation/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── models/
│   │   ├── show.py
│   │   ├── seat.py
│   │   └── reservation.py
│   │
│   ├── schemas/
│   │   ├── show.py
│   │   └── reservation.py
│   │
│   ├── api/
│   │   ├── shows.py
│   │   ├── reservations.py
│   │   └── health.py
│   │
│   ├── services/
│   │   └── reservation_service.py
│   │
│   ├── middleware/
│   │   └── request_id.py
│   │
│   └── metrics.py
│
├── tests/
│   ├── test_shows.py
│   ├── test_reservations.py
│   ├── test_idempotency.py
│   ├── test_concurrency.py
│   └── test_auth.py
│
├── scripts/
│   └── burst.py
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── WRITEUP.md
```

### The important flow

```text
HTTP Request
     ↓
api/
     ↓
schemas/
     ↓
services/
     ↓
models/
     ↓
PostgreSQL
```

And **all the difficult reservation correctness logic lives in:**

```text
app/services/reservation_service.py
```

That's the file you'll be able to discuss deeply in the interview.

---

# 2. `README.md` — our execution checklist

We'll keep the actual project README concise. This is the checklist we'll follow from zero → GitHub → deployment.


# Seat Reservation at Scale

FastAPI + PostgreSQL backend for concurrent seat reservation with transaction safety, idempotency, per-user limits, observability, and load testing.

## Implementation Checklist

### Phase 1 — Project Setup

- [ ] Create GitHub repository
- [ ] Initialize FastAPI project
- [ ] Create project structure
- [ ] Add `requirements.txt`
- [ ] Add `.env` / `.env.example`
- [ ] Add `.gitignore`
- [ ] Create Dockerfile
- [ ] Create docker-compose with FastAPI + PostgreSQL
- [ ] Run application locally

### Phase 2 — Database

- [ ] Create `shows` table
- [ ] Create `show_seats` table
- [ ] Create `reservations` table
- [ ] Create `reservation_seats` table
- [ ] Add required foreign keys
- [ ] Add unique constraints
- [ ] Add indexes
- [ ] Add database initialization/migrations

### Phase 3 — Show API

- [ ] `POST /shows`
- [ ] Create show
- [ ] Create all seats as `available`
- [ ] Validate duplicate seat numbers
- [ ] Return created show

### Phase 4 — Authentication

- [ ] Add simple token-based authentication
- [ ] Derive `user_id` from token
- [ ] Never trust `user_id` from request body
- [ ] Add authentication tests

### Phase 5 — Reservation

- [ ] `POST /shows/{id}/reserve`
- [ ] Validate requested seats
- [ ] Implement idempotency key
- [ ] Store request hash
- [ ] Implement per-user seat limit
- [ ] Implement all-or-nothing multi-seat reservation
- [ ] Lock seats using PostgreSQL row locking
- [ ] Lock seats in deterministic order
- [ ] Create reservation atomically
- [ ] Return `201` on success
- [ ] Return `409` for domain conflicts
- [ ] Ensure no reservation path returns 5xx for normal contention

### Phase 6 — Cancellation

- [ ] `POST /reservations/{id}/cancel`
- [ ] Verify reservation owner
- [ ] Lock reservation/seats
- [ ] Cancel reservation atomically
- [ ] Return seats to `available`
- [ ] Prevent invalid/double cancellation
- [ ] Test re-booking after cancellation

### Phase 7 — Show State

- [ ] `GET /shows/{id}`
- [ ] Return every seat
- [ ] Return available/held/confirmed status
- [ ] Return seat counts
- [ ] Verify:

```text
available + held + confirmed = total seats
```

### Phase 8 — Correctness Tests

- [ ] Same seat requested concurrently
- [ ] Verify exactly one successful reservation
- [ ] Verify all other requests receive `409`
- [ ] Same idempotency key retried concurrently
- [ ] Same key with different seats
- [ ] Per-user limit under concurrency
- [ ] Multiple-seat reservation under concurrency
- [ ] Cancellation under concurrency
- [ ] User spoofing test
- [ ] Verify zero unexpected 5xx

### Phase 9 — Observability

- [ ] Add `/health/live`
- [ ] Add `/health/ready`
- [ ] Readiness checks PostgreSQL
- [ ] Add Prometheus `/metrics`
- [ ] Add confirmed reservation counter
- [ ] Add declined reservation counter by reason
- [ ] Add available seats gauge
- [ ] Add request/reservation latency metric
- [ ] Add structured JSON logs
- [ ] Add request/correlation ID

### Phase 10 — Burst Test

- [ ] Create `scripts/burst.py`
- [ ] Add hot-seat concurrency test
- [ ] Add random-seat concurrency test
- [ ] Add idempotency retry test
- [ ] Add per-user limit test
- [ ] Print `201 / 409 / 5xx` distribution
- [ ] Print final reconciliation
- [ ] Verify:

```text
available + held + confirmed = total
```

### Phase 11 — Deployment

- [ ] Build Docker image locally
- [ ] Run clean Docker setup
- [ ] Deploy PostgreSQL
- [ ] Deploy FastAPI service
- [ ] Configure environment variables
- [ ] Verify cold start
- [ ] Verify `/health/live`
- [ ] Verify `/health/ready`
- [ ] Verify `/docs`
- [ ] Verify `/metrics`
- [ ] Test live reservation API

### Phase 12 — Attack the Live Service

- [ ] Run burst script against live URL
- [ ] Test hot-seat storm
- [ ] Test same-user concurrency
- [ ] Test idempotency retries
- [ ] Check logs
- [ ] Check metrics
- [ ] Verify zero unexpected 5xx
- [ ] Verify reconciliation invariant

### Phase 13 — Documentation

- [ ] Update README
- [ ] Add API examples
- [ ] Add local setup instructions
- [ ] Add burst-test command
- [ ] Add live URL
- [ ] Create `WRITEUP.md`
- [ ] Document atomic decision
- [ ] Document idempotency
- [ ] Document concurrency strategy
- [ ] Document cancellation model
- [ ] Document consistency vs availability
- [ ] Document observability
- [ ] Document AI usage

### Phase 14 — Final Git

- [ ] Review `.env` / secrets
- [ ] Confirm clean checkout works
- [ ] Run full test suite
- [ ] Run final burst test
- [ ] Review Git history
- [ ] Push final code
- [ ] Verify GitHub repository
- [ ] Verify live deployment
- [ ] Verify README
- [ ] Prepare submission

## Final Architecture

```text
Client
   │
   ▼
FastAPI
   │
   ├── Authentication
   ├── Validation
   ├── Reservation Service
   ├── Metrics
   └── Structured Logging
          │
          ▼
      PostgreSQL
          │
          ├── Shows
          ├── Seats
          └── Reservations
```

## Core Correctness Mechanism

```text
PostgreSQL Transaction
        │
        ▼
SELECT ... FOR UPDATE
        │
        ▼
Lock requested seats
        │
        ▼
Check idempotency
        │
        ▼
Check user limit
        │
        ▼
Check availability
        │
        ▼
Create reservation
        │
        ▼
Confirm seats
        │
        ▼
COMMIT
```

## Local Commands

```bash
docker compose up --build
```

Run tests:

```bash
pytest
```

Run burst test:

```bash
python scripts/burst.py <BASE_URL>
```

API documentation:

```text
GET /docs
```

Metrics:

```text
GET /metrics
```

Health:

```text
GET /health/live
GET /health/ready
```

### Our working rule

We'll **not jump around**.

We'll execute this checklist sequentially:

**Setup → DB → Show → Auth → Reservation → Cancellation → State → Tests → Metrics/Logs → Burst → Docker → Deploy → Attack live → Docs → Submit.**

And after each meaningful phase, make a Git commit so the Paytm reviewer can see the project evolving naturally.