**FastAPI + PostgreSQL + Docker + Prometheus + Render/Railway**.

### 🎯 Your target architecture

```text
                 ┌──────────────┐
Users ──────────►│   FastAPI    │
                 └──────┬───────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      PostgreSQL     Metrics        Logs
       (source       /metrics      JSON logs
       of truth)
```



---
<!-- Goal -->
# 1. To Build these 5 endpoints

```text
POST   /shows
POST   /shows/{show_id}/reserve
POST   /reservations/{reservation_id}/cancel
GET    /shows/{show_id}
GET    /health/live
GET    /health/ready
GET    /metrics
```

Plus optionally:

```text
GET /docs
```

FastAPI gives us Swagger automatically.

---

# 2. Database design — this is the heart of this assignment

Use roughly:

```text
shows
-----
id
name
price_paise
per_user_limit
total_seats
created_at

show_seats
----------
id
show_id
seat_number
status          -- available / held / confirmed
reserved_by
reservation_id
created_at

reservations
------------
id
show_id
user_id
amount_paise
status
idempotency_key
request_hash
created_at

reservation_seats
------------------
reservation_id
show_seat_id
```

### Critical constraints

```text
UNIQUE(show_id, seat_number)

UNIQUE(show_id, idempotency_key)
```

And your reservation logic must happen inside:

```text
BEGIN TRANSACTION

    lock/check idempotency
    lock requested seats
    check per-user limit
    check seats available
    create reservation
    update seats → confirmed

COMMIT
```

---

# 3. The most important thing: concurrency

This is what can attack.

### ❌ Do NOT do this

```python
seat = get_seat("A12")

if seat.status == "available":
    seat.status = "confirmed"
    seat.save()
```

Two requests can both read:

```text
A12 = available
```

and both sell it.

---

### ✅ I'll do this.

Use PostgreSQL row locking:

```sql
SELECT *
FROM show_seats
WHERE show_id = :show_id
  AND seat_number IN (...)
ORDER BY seat_number
FOR UPDATE;
```

Now:

```text
Request A ──► locks A12
Request B ──► waits

Request A ──► confirms A12
Request A ──► COMMIT

Request B ──► sees A12 confirmed
Request B ──► 409 seat_taken
```

Therefore:

```text
500 requests
     ↓
A12
     ↓
1 × 201
499 × 409
```

That's exactly what they want.

---

# 4. Multi-seat requests

Choose **all-or-nothing**.

For:

```json
{
  "seats": ["A12", "A13"]
}
```

Either:

```text
A12 + A13 → confirmed
```

or:

```text
A12 unavailable
→ entire request → 409
```

This is easier to reason about and test.

### Avoid deadlocks

Always lock seats in deterministic order:

```text
A12
A13
A14
```

not the order supplied by the user.

So:

```python
sorted(request.seats)
```

before locking.

Mention this explicitly in `WRITEUP.md`.

---

# 5. Idempotency — I will absolutely test this

Request:

```http
Idempotency-Key: abc123
```

Store:

```text
show_id
user_id
idempotency_key
request_hash
reservation_id
```

Suppose:

```text
POST A12
key = abc123
```

→ reservation created.

Retry:

```text
POST A12
key = abc123
```

→ return the **same reservation**.

No second reservation.

---

### Same key, different body

First:

```text
abc123 → A12
```

Then:

```text
abc123 → A13
```

Calculate a deterministic request hash.

```text
hash(A12) != hash(A13)
```

Return:

```http
409 Conflict
```

with something like:

```json
{
  "error": "idempotency_key_reused_with_different_request"
}
```

---

# 6. Per-user limit

Do this **inside the same DB transaction**.

Example:

```text
User Shivam
limit = 4

10 concurrent requests
```

Your transaction should lock the user's relevant reservation state / use a database-safe mechanism before checking the count.

Result:

```text
4 confirmed
6 → 409 per_user_limit
```

Never:

```text
request 1 checks → 3
request 2 checks → 3
request 3 checks → 3
...
```

because then concurrency can push the user over 4.

---

# 7. Authentication

Keep it simple.

For example:

```http
Authorization: Bearer user-123
```

In the backend:

```python
current_user = authenticate_token(...)
```

Then:

```python
user_id = current_user.id
```

**Never accept:**

```json
{
    "user_id": "someone-else"
}
```

as authoritative.

If they send:

```json
{
    "user_id": "attacker",
    "seats": ["A12"]
}
```

while token says:

```text
user-123
```

reservation belongs to:

```text
user-123
```

This directly addresses their spoofing test.

---

# 8. Cancellation / release

For a 1-day assignment, choose:

### Explicit cancellation

```text
POST /reservations/{id}/cancel
```

Only owner can cancel.

Inside transaction:

```text
lock reservation
lock seats
verify owner
verify reservation confirmed/held
reservation → cancelled
seat → available
```

This is considerably simpler than implementing expiry workers.

---

# 9. Metrics

Expose:

```text
reservations_confirmed_total

reservations_declined_total{
    reason="seat_taken"
}

reservations_declined_total{
    reason="per_user_limit"
}

reservations_declined_total{
    reason="idempotent_replay"
}

seats_available
```

Also add:

```text
reservation_latency_seconds
reservation_requests_total
reservation_errors_total
```

Your metrics should allow them to see:

```text
confirmed = 10
seat_taken = 990
5xx = 0
```

---

# 10. Structured logging

Every request should have:

```json
{
  "timestamp": "...",
  "level": "INFO",
  "request_id": "uuid",
  "user_id": "user-123",
  "show_id": "show-1",
  "seat": "A12",
  "event": "reservation_confirmed"
}
```

For failures:

```json
{
  "request_id": "...",
  "event": "reservation_declined",
  "reason": "seat_taken"
}
```

This will make your interview discussion much stronger.

---

# 11. Burst script = VERY important

Create:

```text
./burst.sh https://your-live-url
```

or:

```text
python scripts/burst.py https://your-live-url
```

Generate:

```text
500 users → A12
1000 users → random seats
100 users → same user
100 retries → same idempotency key
```

Print:

```text
========== HOT SEAT ==========
Requests:       500
201 confirmed:  1
409 declined:   499
5xx:            0

========== RECONCILIATION ==========
Total seats:     100
Available:        96
Confirmed:         4
Held:              0

SUM = 100 ✓
```

This is something I would **definitely spend time making polished**.

---

# 12. Deployment

Use:

```text
Docker
   ↓
FastAPI
   ↓
PostgreSQL
```

Deploy to Render/Railway/Fly.io.

Environment variables:

```text
DATABASE_URL
APP_ENV
LOG_LEVEL
```

Never commit secrets.

Health:

```text
GET /health/live
```

returns:

```json
{"status":"alive"}
```

Readiness actually checks DB:

```text
GET /health/ready
```

If DB unavailable:

```http
503
```

That's exactly what they requested.

---

# 13. Repository structure

I'd make it look approximately like:

```text
seat-reservation/
│
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── shows.py
│   │   └── reservations.py
│   │
│   ├── models/
│   │   ├── show.py
│   │   ├── seat.py
│   │   └── reservation.py
│   │
│   ├── services/
│   │   └── reservation_service.py
│   │
│   ├── db/
│   │   └── database.py
│   │
│   ├── middleware/
│   │   └── request_id.py
│   │
│   └── metrics.py
│
├── tests/
│   ├── test_shows.py
│   ├── test_reservation.py
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
├── README.md
└── WRITEUP.md
```

---

# 14. Testing strategy

Before deploying, prove these locally.

| Test | Expected |
|---|---|
| Same seat × 500 users | 1×201, 499×409 |
| Different seats | each succeeds |
| Same idempotency key ×100 | 1 reservation |
| Same key + different seats | 409 |
| Same user ×10, limit 4 | max 4 |
| Different users | independent |
| Cancel | seat available again |
| Unauthorized cancel | 403 |
| Spoof user_id | ignored |
| DB unavailable | readiness 503 |
| 20k-ish burst | zero 5xx |

**The concurrency tests are the main event.**

---

# 15. Git history matters

They explicitly said:

> "commit incrementally — we look at how the work was actually done."

So don't do:

```text
initial commit
```

then dump the entire project.

Do something like:

```text
1. init FastAPI service and Docker setup
2. add PostgreSQL schema
3. implement show creation
4. implement reservation transaction
5. add row locking and concurrency protection
6. add idempotency
7. add per-user limit
8. add cancellation
9. add authentication
10. add health endpoints
11. add Prometheus metrics
12. add structured logging
13. add concurrency tests
14. add burst test
15. deploy service
16. harden production configuration
17. update README and writeup
```

That history itself demonstrates engineering discipline.

---

# 16. Your `WRITEUP.md` should answer only these questions

Keep it short.

### Atomic decision

> PostgreSQL transaction + `SELECT ... FOR UPDATE` on requested seat rows, ordered deterministically by seat number.

### Why race-free?

Explain:

```text
Only one transaction can hold the seat row lock.
Other concurrent requests wait.
After the first transaction commits, subsequent transactions observe
the seat as confirmed and return 409.
```

### Idempotency

Explain:

```text
Unique(show_id, idempotency_key)
+
request hash
+
original reservation stored
```

### Multi-seat

```text
All-or-nothing.
Seats locked in sorted order to avoid deadlocks.
```

### Holds

You're choosing:

```text
explicit cancellation
```

### Consistency vs availability

Say that during a DB partition you prefer **correctness/consistency over accepting potentially conflicting reservations**.

Don't try to impress them with distributed systems terminology unnecessarily.

---

---

## Your 1-day execution plan

### Morning — Core

```text
09:00–10:00  Project + Docker + PostgreSQL
10:00–11:00  DB models/schema
11:00–13:00  Reservation transaction
13:00–14:00  Idempotency + user limit
```

### Afternoon — Correctness

```text
14:00–15:00  Cancellation + auth
15:00–16:30  Concurrency tests
16:30–17:30  Burst script
```

### Evening — Production

```text
17:30–18:30  Metrics + structured logs
18:30–19:00  Health/readiness
19:00–20:00  Docker production setup
20:00–21:00  Deploy
```

### Final

```text
21:00–22:00  Attack your own live API
22:00–22:30  README
22:30–23:00  WRITEUP
23:00         Final Git history + submission
```

---
