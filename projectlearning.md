Absolutely. I’ll make this as a **revision/learning note**, not just a project checklist — so each topic says **what it is, why we needed it, how we implemented it, and Django equivalent in brackets**.

# Seat Reservation at Scale — Phase-by-Phase Revision Notes

> **Goal:** Build a production-style seat reservation backend where concurrent users cannot double-book seats, retrying requests do not create duplicate reservations, and the system remains consistent under load.

---

# Phase 1 — Project Setup

### FastAPI Application
**What / Why:** FastAPI is our backend framework for creating HTTP APIs (similar to Django + Django REST Framework). We needed a lightweight API layer for shows, reservations, cancellation, and health checks.

**Django relation:** `FastAPI app + APIRouter` ≈ `Django project + urls.py/views.py`.

### Docker
**What / Why:** Docker packages the application with its Python dependencies so it runs consistently on any machine.

**Django relation:** Same concept as containerizing a Django application with Docker.

### Docker Compose
**What / Why:** Compose runs multiple services together — our FastAPI container + PostgreSQL container.

**Django relation:** Same as running a Django container alongside a PostgreSQL container.

### Environment Configuration
**What / Why:** Database credentials and environment-specific values belong in `.env`, not hardcoded in Python.

**Bug/problem resolved:** Running Compose from the wrong directory caused Docker Compose to fail; we learned the Compose file must be executed from the project directory.

---

# Phase 2 — PostgreSQL Schema & Migrations

### SQLAlchemy Models
**What / Why:** SQLAlchemy models represent database tables from Python (similar to Django Models).

**Django relation:** `SQLAlchemy Model` ≈ `django.db.models.Model`.

### `shows`
Stores show information such as name, price, and total seats.

**Why:** A reservation must belong to a specific show.

### `show_seats`
Stores every seat belonging to a show and its current status.

**Why:** We need a database row for each seat so PostgreSQL can lock individual seats during concurrent reservations.

### `reservations`
Stores the actual reservation, user, amount, status, and idempotency information.

**Why:** This is the business record proving which user reserved which show.

### `reservation_seats`
Connects reservations to their seats.

**Why:** One reservation can contain multiple seats.

**Django relation:** Similar to a Many-to-Many relationship / intermediate `through` table.

### `show_user_counters`
Stores how many seats a user currently owns for a show.

**Why:** We need a concurrency-safe way to enforce the maximum 4-seat-per-user rule.

### Constraints
Added unique constraints, foreign keys, and check constraints.

**Why:** Important rules should also be enforced by PostgreSQL, not only Python.

### Indexes
Added indexes for common lookup patterns.

**Why:** They make show/seat/reservation queries faster as the database grows.

### Alembic
Alembic manages database schema migrations.

**Django relation:** `Alembic` ≈ `python manage.py makemigrations` + `python manage.py migrate`.

**Bug resolved:** Alembic initially had `target_metadata=None` and migrations were not detecting our models. We connected `Base.metadata` and imported the models correctly.

---

# Phase 3 — Show Creation

### `POST /shows`
Creates a show and all its seats.

**Why:** The reservation system needs shows and their seat inventory before anyone can reserve.

### Seat Validation
Rejected empty and duplicate seat numbers.

**Why:** Two database rows representing the same logical seat would break reservation correctness.

### Integer `price_paise`
Prices are stored as integer paise rather than floating-point rupees.

**Why:** Money should not use floating-point arithmetic because of precision problems.

### Transaction
The show and its seats are committed together.

**Why:** We don't want a show created successfully while only half of its seats exist.

---

# Phase 4 — Reservation Transaction

## `POST /shows/{id}/reserve`

This is the **core of the entire assignment**.

### Authentication
The user sends an authorization token.

**Why:** We need to know who is making the reservation and must not trust a `user_id` supplied in the request body.

**Django relation:** Similar to `request.user` after Django authentication.

### Token-Derived `user_id`
We derive:

```text
Authorization: Bearer user-123
                ↓
              user_id
              user-123
```

**Why:** Prevents one user from pretending to be another user.

### Idempotency Key
Each reservation request contains:

```text
Idempotency-Key
```

**Why:** Network retries should not accidentally create two reservations for the same operation.

**Django relation:** No direct Django equivalent; this is an API/payment-system reliability pattern.

### Request Hash
We hash the requested seats.

**Why:** If the same idempotency key is reused with different seats, we can detect it and return `409`.

Example:

```text
key = ABC
first request  → A1
second request → A2
                  ↓
                409
```

### PostgreSQL Transaction
The reservation operation happens inside one database transaction.

**Why:** Seat updates, reservation creation, and user-counter updates must succeed or fail together.

**Django relation:** Similar to `transaction.atomic()`.

### Row Locking — `SELECT FOR UPDATE`
We lock requested seat rows before checking availability.

**Why:** This prevents two concurrent transactions from both seeing the same seat as available.

**Django relation:** Similar to Django:

```python
select_for_update()
```

### Deterministic Lock Ordering
Requested seats are sorted before locking.

**Why:** Multiple transactions locking multiple seats in different orders can cause deadlocks.

Example:

```text
Request A → A1 → A2
Request B → A2 → A1   ❌ possible deadlock

Both:
A1 → A2                ✅ deterministic
```

### Per-User Limit
Default limit is 4 seats per user per show.

**Why:** The requirement says one user cannot reserve unlimited seats.

### `ShowUserCounter`
We lock the user's counter row before checking/updating the count.

**Why:** Without the lock, concurrent requests could both see `3 seats` and both reserve another seat, producing `5`.

### All-or-Nothing Multi-seat Reservation
For:

```json
{
  "seats": ["A1", "A2", "A3"]
}
```

either all seats are reserved or none are.

**Why:** We must never leave a partially completed reservation.

### Conflict Handling
Normal business conflicts return `409 Conflict`.

Examples:

```text
Seat already booked
User exceeded limit
Idempotency key reused differently
Seat doesn't exist
```

**Why:** These are expected business conflicts, not server failures.

### Major Reservation Bugs We Prevented

```text
Double booking
     ↓
SELECT FOR UPDATE

Duplicate retry
     ↓
Idempotency key + request hash

User exceeding limit
     ↓
Locked ShowUserCounter

Partial multi-seat booking
     ↓
Single transaction

Deadlock risk
     ↓
Deterministic seat lock order
```

---

# Phase 5 — Cancellation

## `POST /reservations/{id}/cancel`

### Owner Verification
Only the reservation's user can cancel it.

**Why:** Another user must not be able to cancel someone else's reservation.

### Reservation Lock
The reservation is locked before changing its status.

**Why:** Two simultaneous cancellation requests must not both successfully cancel the same reservation.

### Seat Lock
Reservation seats are locked before releasing them.

**Why:** Cancellation can happen concurrently with another reservation trying to acquire those seats.

### Counter Decrement
The user's reserved-seat counter is decreased.

**Why:** After cancellation, the user should be able to reserve those seats again within the limit.

### Cancellation Result

```text
confirmed reservation
        ↓
     cancel
        ↓
reservation = cancelled
seat = available
counter -= seats
```

We tested this successfully.

---

# Phase 6 — Show State

## `GET /shows/{id}`

Returns:

```text
total_seats
available
held
confirmed
seats[]
```

### Why?
The system needs a reliable way to inspect current inventory.

**Django relation:** Similar to a Django REST Framework GET endpoint returning serialized model/queryset data.

### Reconciliation Invariant

```text
available + held + confirmed = total_seats
```

**Why:** This is our fundamental inventory consistency check.

We tested:

```text
4 + 0 + 1 = 5 ✅
```

---

# Phase 7 — Correctness & Concurrency Tests

This phase proves that the implementation works under the conditions the assignment actually cares about.

## Hot Seat — 500 Concurrent Requests

```text
500 users
    ↓
same seat
```

Result:

```text
201 → 1
409 → 499
5xx → 0
```

**Why:** This proves double-booking protection under heavy contention.

### Concurrent Idempotency

20 requests used the same:

```text
user + idempotency key + seats
```

Result:

```text
20 requests
→ same reservation ID
```

**Why:** Retries create one logical reservation rather than 20 reservations.

### Same Key + Different Request

```text
key = ABC
A1 → success
A2 → 409
```

**Why:** An idempotency key represents one specific operation.

### Per-user Concurrency

5 simultaneous reservations from one user:

```text
201 → 4
409 → 1
```

**Why:** Proves the 4-seat limit remains correct under concurrency.

### Multi-seat Concurrency

Two users compete for overlapping seats.

```text
Request A → M1 + M2
Request B → M2 + M3
```

Result:

```text
201 → 1
409 → 1
```

**Why:** Proves atomicity — one request cannot partially steal seats from another.

### Concurrent Cancellation

Two cancellation requests for the same reservation:

```text
200 → 1
409 → 1
```

**Why:** Only one cancellation is allowed.

### User Spoofing

Request attempted:

```json
{
  "seats": ["AUTH1"],
  "user_id": "fake-user"
}
```

with token:

```text
Bearer real-user
```

Result:

```text
reservation.user_id = real-user
```

**Why:** Proves identity comes from authentication, not the request body.

### Reconciliation

Verified:

```text
available + held + confirmed = total_seats
```

**Why:** Confirms inventory never becomes inconsistent.

---

# Phase 8 — Health / Observability

## `/health/live`

Returns:

```json
{
  "status": "alive"
}
```

**Why:** Tells Docker/load balancer that the application process itself is running.

**Django relation:** Similar to a lightweight Django health-check view.

## `/health/ready`

Checks PostgreSQL:

```sql
SELECT 1
```

**Why:** The application may be alive but unable to serve reservations if PostgreSQL is unavailable.

### Readiness Failure

Database unavailable:

```text
503 Service Unavailable
```

**Why:** The service should fail closed instead of pretending it is ready.

## Prometheus Metrics

The application exposes metrics at:

```text
GET /metrics
```

### Reservation Counters

```text
reservations_confirmed_total
reservations_declined_total{reason="..."}
```

The confirmed counter increases after a new reservation commits. Declined
requests are counted by reason, including idempotent replay, idempotency-key
conflict, seat already taken, per-user limit, and other reservation conflicts.

**Why:** Counters help us see reservation volume and explain why requests are
being rejected without treating expected business conflicts as server errors.

### Available-Seat Gauge

```text
seats_available{show_id="..."}
```

The gauge is refreshed after show creation, reservation, and cancellation.
Cancellation therefore increases the available-seat count when it releases
seats.

**Why:** A gauge describes a value that can go both up and down; it is more
appropriate for current inventory than a counter.

### Reservation and HTTP Latency

```text
reservation_latency_seconds
http_request_duration_seconds
```

The reservation histogram records successful reservation-operation latency.
The FastAPI instrumentator records HTTP request latency.

**Why:** Separating business-operation latency from overall HTTP latency helps
distinguish database/reservation work from time spent elsewhere in a request.

### Metric Storage Caveat

These Prometheus metrics are held in the API process's memory. Rebuilding or
restarting the API resets their samples; production monitoring should scrape
and persist them in a Prometheus server.

## Request ID and Structured Request Logs

`RequestIDMiddleware` accepts an incoming `X-Request-ID` or generates a UUID,
stores it on the request, and returns it in the response header.

Each completed request also emits one JSON log record containing the request
ID, method, path, status code, and duration in milliseconds. The application
logger is explicitly configured so these records reach Docker's container
logs.

**Why:** The response ID lets a client report a specific request, while the
same ID in logs lets us find that request across application diagnostics.

## Phase 8 Verification

Verified locally with Docker Compose:

```text
GET /health/live  -> 200 and X-Request-ID returned
GET /health/ready -> ready, database connected
GET /metrics      -> application and HTTP metrics exposed
```

A reservation/replay, idempotency conflict, taken-seat decline,
per-user-limit decline, and cancellation were exercised. The expected metric
series appeared, cancellation refreshed the available-seat gauge, and JSON
request records were visible in the API container logs. Temporary test data
was removed after verification.

---

# Current Position

```text
Phase 1  ✅ Setup
Phase 2  ✅ Database
Phase 3  ✅ Shows
Phase 4  ✅ Reservation
Phase 5  ✅ Cancellation
Phase 6  ✅ Show State
Phase 7  ✅ Correctness Tests
Phase 8  ✅ Health & Observability
```

Then:

```text
Phase 9  → Burst Test
Phase 10 → Deployment
Phase 11 → Attack Live Service
Phase 12 → Documentation
Phase 13 → Final Git / Submission
```

## One-Line Architecture Memory

```text
FastAPI (Django/DRF equivalent API layer)
        ↓
SQLAlchemy (Django ORM equivalent)
        ↓
PostgreSQL (source of truth)
        ↓
Transaction + SELECT FOR UPDATE
        ↓
Correct reservation under concurrency
```


# 1. What are we actually building?

The project is:

> **Seat Reservation at Scale — a concurrent, transactional reservation API.**

At the high level:

```text
Client
  │
  │ HTTP JSON
  ▼
FastAPI
  │
  │ SQLAlchemy
  ▼
PostgreSQL
```

Later we'll add:

```text
FastAPI
 ├── Authentication
 ├── Reservation business logic
 ├── Idempotency
 ├── Metrics
 ├── Structured logging
 └── Health/readiness
          │
          ▼
      PostgreSQL
          │
          ▼
   Optional analytics
      (Snowflake)
```

The most important architectural decision is:

> **PostgreSQL is the source of truth for seat availability and concurrency.**

Snowflake is **not** involved in the actual booking transaction.

---

# 2. Why FastAPI?

FastAPI is a Python web framework designed for building APIs.

For example:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello"}
```

When someone sends:

```http
GET /
```

FastAPI calls:

```python
root()
```

and converts the Python dictionary into JSON.

### Why FastAPI for this project?

Because we need:

- REST/JSON APIs
- request validation
- authentication/dependencies
- good async support
- automatic OpenAPI documentation
- easy testing
- high-performance HTTP handling

FastAPI is built around **Starlette** for web/HTTP functionality and **Pydantic** for data validation/settings.

---

# 3. Why Docker?

Without Docker, you would need to install:

```text
Python
PostgreSQL
PostgreSQL configuration
Python dependencies
```

and make sure everything works on every machine.

Docker packages the application environment.

Think:

```text
Docker image
    =
Application
+
Python
+
Dependencies
+
Runtime configuration
```

Then we can run that image as a **container**.

---

# 4. Image vs Container

This is an important interview question.

### Image

An image is a **template/package**.

Example:

```text
seat-reservation-api image
```

contains:

```text
Python 3.12
FastAPI
SQLAlchemy
Alembic
your application code
```

### Container

A container is a **running instance of an image**.

```text
Image
  ↓
Container
```

So when you saw:

```text
seat_reservation_api
seat_reservation_db
```

those are containers.

---

# 5. What is the Dockerfile?

Our Dockerfile:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Let's understand **every line**.

---

## `FROM`

```dockerfile
FROM python:3.12-slim
```

Means:

> Start my Docker image from an existing Python 3.12 Linux image.

`slim` means a smaller Debian-based Python image with fewer unnecessary packages.

Interview answer:

> "I use Python 3.12-slim as the base image to keep the application image relatively lightweight."

---

# 6. `WORKDIR`

```dockerfile
WORKDIR /app
```

This sets the working directory inside the container.

So:

```text
/app
```

becomes the equivalent of:

```text
F:\...\seat-reservation
```

inside the container.

After this:

```dockerfile
COPY requirements.txt .
```

means:

```text
host requirements.txt
        ↓
container /app/requirements.txt
```

---

# 7. Why copy `requirements.txt` separately?

We have:

```dockerfile
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
```

This ordering is intentional.

Docker builds images in layers.

If you change:

```text
app/main.py
```

but don't change:

```text
requirements.txt
```

Docker can reuse the dependency installation layer.

That's called **Docker layer caching**.

Interview-quality explanation:

> "I copy the dependency file separately so Docker can cache the dependency installation layer and avoid reinstalling packages when only application code changes."

---

# 8. `RUN`

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

This executes a command **while building the image**.

It installs:

```text
fastapi
uvicorn
sqlalchemy
psycopg2
alembic
...
```

into the image.

Important distinction:

```text
RUN
```

happens during **image build**.

---

# 9. `COPY . .`

```dockerfile
COPY . .
```

Copies our project into:

```text
/app
```

inside the image.

---

# 10. `EXPOSE`

```dockerfile
EXPOSE 8000
```

This documents that the application listens on port 8000.

It does **not** itself publish the port to your Windows machine.

The actual publishing happens in Compose:

```yaml
ports:
  - "8000:8000"
```

That's an important distinction.

---

# 11. `CMD`

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

This is the default command executed when the container starts.

### What is:

```text
uvicorn
```

Uvicorn is the **ASGI server** running our FastAPI application.

### What is:

```text
app.main:app
```

Break it down:

```text
app.main
   │
   └── Python module: app/main.py

:
│
└── object inside module

app
│
└── FastAPI application object
```

So:

```text
app.main:app
```

means:

> Load the `app` object from `app/main.py`.

---

# 12. What is ASGI?

This is a useful interview concept.

Traditional Python web applications historically used **WSGI**.

Modern async-capable Python applications commonly use **ASGI**.

FastAPI is an ASGI framework.

Uvicorn is an ASGI server.

Therefore:

```text
HTTP Request
     ↓
Uvicorn
     ↓
FastAPI
     ↓
Your endpoint
```

---

# 13. Why `0.0.0.0`?

We have:

```text
--host 0.0.0.0
```

Inside Docker, if the application only listens on:

```text
127.0.0.1
```

it may only be reachable from inside the container.

`0.0.0.0` means:

> Listen on all network interfaces available inside the container.

That's why Docker can forward:

```text
localhost:8000
       ↓
container:8000
```

---

# 14. Why Docker Compose?

We have **two containers**:

```text
FastAPI
PostgreSQL
```

We could manually run each container.

But Compose lets us define the whole local environment in one YAML file.

```yaml
services:
  api:
    ...

  db:
    ...
```

So:

```bash
docker compose up
```

starts the application stack.

Think of Compose as:

> **A declarative configuration for running multiple related containers together.**

---

# 15. Our development Compose

You have:

```yaml
services:
  api:
    build: .
    container_name: seat_reservation_api
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - .:/app
```

Let's break it down.

---

## `services`

```yaml
services:
```

Defines the containers that make up our application.

We have:

```text
api
db
```

---

# 16. `build`

```yaml
build: .
```

Means:

> Build the API image using the Dockerfile in the current directory.

---

# 17. `ports`

```yaml
ports:
  - "8000:8000"
```

Format:

```text
HOST:CONTAINER
```

Therefore:

```text
Windows localhost:8000
        ↓
Docker container:8000
```

You can access:

```text
http://localhost:8000
```

---

# 18. `env_file`

```yaml
env_file:
  - .env
```

Loads environment variables into the container.

Your `.env` contains:

```env
APP_NAME=Seat Reservation Service
APP_ENV=development
DATABASE_URL=postgresql://postgres:postgres@db:5432/seat_reservation
```

---

# 19. Why does DATABASE_URL use `db` instead of localhost?

This is **very important Docker networking knowledge**.

Inside the API container:

```text
localhost
```

means:

> the API container itself.

It does **not** mean your PostgreSQL container.

Compose creates a network where services can communicate using their service names.

We named PostgreSQL:

```yaml
db:
```

Therefore:

```text
postgresql://postgres:postgres@db:5432/seat_reservation
                                      ↑
                                  DB service
```

The network looks like:

```text
API container
     │
     │ db:5432
     ▼
PostgreSQL container
```

Whereas from your Windows machine:

```text
localhost:5432
```

works because we publish PostgreSQL's port.

---

# 20. Why `volumes: - .:/app`?

This is our **development bind mount**.

```yaml
volumes:
  - .:/app
```

Means:

```text
Windows project
       │
       ▼
container /app
```

The same files are visible in the container.

Therefore if you modify:

```text
app/models/show.py
```

on Windows:

```text
Windows file changes
       ↓
container /app changes
       ↓
Uvicorn sees change
```

---

# 21. What is `--reload`?

Development Compose overrides Dockerfile's default command:

```yaml
command:
  [
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--reload"
  ]
```

`--reload` tells Uvicorn:

> Watch application files and restart the server when they change.

Therefore:

```text
Edit Python
   ↓
Bind mount exposes change
   ↓
Uvicorn detects change
   ↓
Application reloads
```

This is why we **don't rebuild Docker every time we edit Python**.

---

# 22. Why don't we use `--reload` in production?

Because production should use a stable application image.

Development:

```text
change code
↓
automatic reload
```

Production:

```text
build image
↓
test image
↓
deploy image
```

We don't want production constantly watching source files.

---

# 23. Why did we run this?

```powershell
docker compose down
```

This stops/removes the Compose containers and network for that Compose project.

We ran it because we changed our Docker development configuration.

Then:

```powershell
docker compose up --build -d
```

Breakdown:

### `up`

Start the services.

### `--build`

Rebuild the image before starting.

### `-d`

Detached mode.

Meaning:

> Run containers in the background and return control to the terminal.

We **do not need to run this every time**.

Only when something requiring an image rebuild changes, such as:

```text
Dockerfile
requirements.txt
some image-level configuration
```

Normal Python changes are handled by:

```text
bind mount + --reload
```

---

# 24. Why did we run the model import command?

We ran:

```powershell
docker compose exec api python -c "from app.models import Show, ShowSeat, Reservation, ReservationSeat, ShowUserCounter; print('ALL MODELS IMPORTED')"
```

This is a very useful debugging technique.

Break it down:

### `docker compose exec`

Execute a command inside an **already running Compose service**.

```text
docker compose exec api
```

means:

> Run something inside the API container.

### `python -c`

Tell Python:

> Execute this Python code directly from the command line.

Then:

```python
from app.models import ...
```

tests whether the models can actually be imported.

We got:

```text
ALL MODELS IMPORTED
```

Therefore:

```text
Docker
   ↓
Python
   ↓
app package
   ↓
models
   ↓
SQLAlchemy models
```

are all accessible.

---

# 25. Now PostgreSQL

Why PostgreSQL?

Because reservation correctness requires **strong transactional guarantees**.

We need things like:

```text
BEGIN TRANSACTION

lock seats

check availability

check user limit

create reservation

mark seats confirmed

COMMIT
```

PostgreSQL is excellent for this.

---

# 26. What is SQLAlchemy?

SQLAlchemy is our Python database toolkit/ORM.

Instead of writing everything manually like:

```sql
SELECT * FROM shows WHERE id = ...;
```

we can represent database tables as Python classes:

```python
class Show(Base):
    __tablename__ = "shows"
```

Then SQLAlchemy maps:

```text
Python object
      ↕
Database row
```

This is called **ORM — Object Relational Mapping**.

---

# 27. What is `Base`?

In:

```python
Base = declarative_base()
```

`Base` is the parent registry used by our SQLAlchemy models.

For example:

```python
class Show(Base):
```

means SQLAlchemy knows:

> This class represents a database table.

Then:

```python
Base.metadata
```

contains information about all registered tables.

That's going to become extremely important for Alembic.

---

# 28. Why Alembic?

This is the next major concept.

Imagine we create:

```python
class Show(Base):
```

That Python class **doesn't automatically create the PostgreSQL table**.

We need a controlled way to translate:

```text
SQLAlchemy model changes
        ↓
Database schema changes
```

That's Alembic.

Think of Alembic as:

> **Git for database schema changes.**

For example:

```text
Migration 001
Create shows

Migration 002
Create show_seats

Migration 003
Add per_user_limit

Migration 004
Add idempotency_key
```

Each migration records a schema change.

---

# 29. Why not simply `Base.metadata.create_all()`?

For a toy application you might see:

```python
Base.metadata.create_all(engine)
```

But that's not ideal for a serious project.

Why?

Because production databases evolve.

Imagine:

```text
Version 1:
shows(name)

Version 2:
shows(name, price)

Version 3:
shows(name, price, per_user_limit)
```

You need to know exactly **what changed and when**.

Alembic provides:

```text
migration history
upgrade
downgrade
autogenerate
version tracking
```

That's much more appropriate for this assignment.

---

# 30. What did this command do?

We ran:

```powershell
docker compose exec api alembic init alembic
```

Meaning:

```text
docker compose exec
        ↓
inside API container

alembic
        ↓
run Alembic CLI

init
        ↓
initialize a migration environment

alembic
        ↓
create migration directory named alembic
```

It generated:

```text
alembic/
├── README
├── env.py
├── script.py.mako
└── versions/
```

and:

```text
alembic.ini
```

---

# 31. What is `alembic.ini`?

It's Alembic's configuration file.

It contains configuration such as:

```text
migration script location
logging
database URL configuration
```

In our project, we're deliberately getting the database URL from our application settings:

```python
settings.database_url
```

rather than maintaining another copy of the database credentials.

---

# 32. What is `env.py`?

This is one of the most important Alembic files.

`env.py` is the **runtime configuration/entry point for migrations**.

Our modified version imports:

```python
from app.database import Base
```

and:

```python
from app.models import (
    Show,
    ShowSeat,
    Reservation,
    ReservationSeat,
    ShowUserCounter,
)
```

Then:

```python
target_metadata = Base.metadata
```

This tells Alembic:

> "Here is the SQLAlchemy metadata representing my application's database schema."

---

# 33. Why import every model?

Because Alembic needs those model classes registered in:

```python
Base.metadata
```

If we don't import a model, it may not be registered when Alembic examines the metadata.

So we explicitly import:

```text
Show
ShowSeat
Reservation
ReservationSeat
ShowUserCounter
```

Then:

```text
Base.metadata
       ↓
all five tables
       ↓
Alembic
```

---

# 34. What is `autogenerate`?

Our next command will be:

```powershell
docker compose exec api alembic revision --autogenerate -m "create reservation schema"
```

This does **not yet apply anything to PostgreSQL**.

It compares:

```text
SQLAlchemy models
        VS
current database schema
```

and generates a migration script describing the differences.

For example:

```text
Model says:
shows table exists

Database says:
shows doesn't exist

        ↓

Alembic generates:
CREATE TABLE shows ...
```

---

# 35. `revision` vs `upgrade`

This is a common interview question.

### `revision`

Creates a migration file.

```bash
alembic revision
```

Think:

> "Create the instructions for changing the database."

### `upgrade`

Actually applies those instructions.

```bash
alembic upgrade head
```

Think:

> "Execute the migration against the database."

Therefore:

```text
Models
  ↓
revision --autogenerate
  ↓
migration file
  ↓
upgrade head
  ↓
PostgreSQL schema
```

---

# 36. What is `head`?

Alembic maintains migration versions.

Suppose:

```text
001
 ↓
002
 ↓
003
```

`head` means:

> The latest migration in the migration chain.

So:

```bash
alembic upgrade head
```

means:

> Apply all required migrations until the database reaches the latest version.

---

# 37. Our database architecture

We currently have these logical tables:

```text
shows
  │
  ├── show_seats
  │
  ├── reservations
  │       │
  │       └── reservation_seats
  │
  └── show_user_counters
```

### `shows`

One row per event/show.

Example:

```text
Movie Night
100 seats
₹500
limit 4
```

### `show_seats`

One row per physical seat for that show.

```text
A1 available
A2 available
A3 available
...
```

### `reservations`

One reservation/order.

```text
user
show
amount
status
idempotency key
request hash
```

### `reservation_seats`

Links reservations to seats.

This supports:

```text
Reservation 123
   ├── A1
   ├── A2
   └── A3
```

### `show_user_counters`

This is our concurrency-safe per-user limit mechanism.

Instead of doing an unsafe:

```sql
COUNT(reservations)
```

during concurrent requests, we maintain a counter row that can be locked transactionally.

---

# 38. The big concurrency picture

This is ultimately what Paytm Money is testing.

Suppose 500 users request:

```text
Seat A1
```

at nearly the same time.

We don't want:

```text
Request 1 → A1 available
Request 2 → A1 available
Request 3 → A1 available
...
```

and multiple confirmations.

Our eventual transaction will use PostgreSQL row locking:

```sql
SELECT ...
FROM show_seats
WHERE ...
FOR UPDATE;
```

Conceptually:

```text
500 requests
     │
     ▼
PostgreSQL
     │
     ▼
Lock A1 row
     │
     ├── Request #1 gets lock
     │       ↓
     │    confirms A1
     │       ↓
     │    COMMIT
     │
     └── other requests wait
             ↓
          see A1 confirmed
             ↓
           409
```

That is the heart of the assignment.

---

# 39. Where we are right now

Our journey is:

```text
PHASE 1
Project setup
       ↓
FastAPI
       ↓
Docker
       ↓
PostgreSQL
       ↓
Development reload
       ↓
Model definitions
       ↓
Model import verified
       ↓
Alembic initialized
       ↓
NOW
Configure Alembic
       ↓
Generate migration
       ↓
Inspect migration
       ↓
Apply migration
       ↓
Verify PostgreSQL schema
       ↓
PHASE 3
POST /shows
```

So we are **not yet at reservation logic**.

That's intentional.

---

# 40. Interview cheat sheet

If an interviewer asks:

**Why FastAPI?**

> "FastAPI is a Python ASGI framework with Pydantic-based validation, dependency injection, automatic OpenAPI documentation, and good async support. I used it to expose the reservation HTTP API."

**Why Uvicorn?**

> "Uvicorn is the ASGI server that runs the FastAPI application."

**Why Docker?**

> "To make the application runtime reproducible and isolate the API and PostgreSQL environments."

**Why Docker Compose?**

> "To declaratively run the API and PostgreSQL services together with networking, environment variables, volumes, healthchecks, and dependencies."

**Why PostgreSQL?**

> "The reservation workflow requires ACID transactions and row-level locking for concurrency correctness."

**Why SQLAlchemy?**

> "It provides Python-side database modeling and database access through an ORM/Core abstraction."

**Why Alembic?**

> "Alembic provides version-controlled, incremental database schema migrations and integrates with SQLAlchemy metadata."

**What is Alembic autogenerate?**

> "It compares SQLAlchemy metadata with the current database schema and generates a candidate migration. I still inspect the generated migration before applying it."

**What is `--reload`?**

> "A development-only Uvicorn feature that watches source files and restarts the application when they change."

**Why doesn't production use `--reload`?**

> "Production should run an immutable, tested image rather than watching source files for changes."

**Why `db` in `DATABASE_URL`?**

> "Because Docker Compose provides service-name DNS, so the API container reaches PostgreSQL using the `db` service name rather than localhost."

**Why `0.0.0.0`?**

> "The server listens on all interfaces inside the container so Docker's port mapping can reach it."

---

## Our immediate next step

You already configured `alembic/env.py`.

Now run **only**:

```powershell
docker compose exec api alembic revision --autogenerate -m "create reservation schema"
```

Then we'll **inspect what Alembic generated before touching the database**.

That distinction — **generate migration first, review it, then apply it** — is exactly the kind of thing you should understand rather than blindly executing commands.