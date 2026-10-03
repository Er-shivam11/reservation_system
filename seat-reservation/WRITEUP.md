# Seat Reservation at Scale — Technical Write-Up

## 1. Architecture

The service is implemented using:

- FastAPI for the HTTP API
- PostgreSQL as the source of truth
- SQLAlchemy for database access
- Alembic for schema migrations
- Docker for containerization
- Prometheus-compatible metrics for observability
- Railway for deployment

```text
Client
   |
   v
FastAPI
   |
   +-- Authentication
   +-- Validation
   +-- Reservation Service
   +-- Metrics / Logging
   |
   v
PostgreSQL
   |
   +-- shows
   +-- show_seats
   +-- reservations
   +-- reservation_seats
   +-- show_user_counters
```

PostgreSQL is responsible for reservation correctness. The reservation decision is not maintained in application memory.

---

## 2. Atomic Reservation Mechanism

A reservation is performed inside a single PostgreSQL transaction.

The important sequence is:

```text
BEGIN
  |
  +-- Authenticate user
  |
  +-- Initialize / lock user counter
  |
  +-- Lock requested seats
  |
  +-- Check per-user limit
  |
  +-- Check seat availability
  |
  +-- Create reservation
  |
  +-- Mark seats confirmed
  |
  +-- Update user counter
  |
COMMIT
```

Requested seats are locked using PostgreSQL row-level locking with:

```sql
SELECT ...
FROM show_seats
WHERE ...
FOR UPDATE;
```

Because the seat rows are locked before availability is checked, concurrent transactions cannot both successfully reserve the same seat.

The transaction is all-or-nothing for multi-seat reservations. If any requested seat is unavailable or invalid, the reservation is rejected without partially confirming the remaining seats.

---

## 3. Deterministic Locking and Deadlock Avoidance

Multiple-seat requests can potentially request the same seats in different orders.

For example:

```text
Request A: A1, A2
Request B: A2, A1
```

The application normalizes and sorts requested seat numbers before locking them.

Therefore both requests attempt to acquire seat locks in the same deterministic order:

```text
A1 → A2
```

This reduces lock-order inversion and helps prevent deadlocks between competing reservation transactions.

---

## 4. Idempotency

Every reservation requires an `Idempotency-Key`.

The database stores:

- `show_id`
- `user_id`
- `idempotency_key`
- `request_hash`

A unique constraint protects the idempotency identity:

```text
show_id + user_id + idempotency_key
```

The request hash is generated from the normalized seat list.

Therefore:

### Same key + same request

The existing reservation is returned.

### Same key + different request

The request is rejected with:

```text
409 Conflict
```

### Concurrent retries

Concurrent requests using the same idempotency key cannot create multiple reservations.

The database uniqueness constraint and transaction handling ensure that the original reservation is reused.

---

## 5. Per-User Reservation Limit

Each show has a configurable per-user reservation limit.

The default is:

```text
4 seats
```

A `show_user_counters` table maintains the number of confirmed seats held by each user for each show.

The counter row is locked using:

```sql
SELECT ...
FOR UPDATE;
```

The application then evaluates:

```text
current_count + requested_count <= per_user_limit
```

This check happens while the counter is locked, so concurrent requests from the same user cannot bypass the limit through race conditions.

---

## 6. Cancellation Model

The assignment allows either explicit cancellation or time-based holds.

This implementation uses **explicit cancellation**.

A user can cancel their own confirmed reservation using:

```text
POST /reservations/{reservation_id}/cancel
```

Cancellation is transactional.

The operation:

1. Locks the reservation.
2. Locks its associated reservation-seat records.
3. Locks the associated seats.
4. Marks the seats as `available`.
5. Decrements the user's reservation counter.
6. Marks the reservation as `cancelled`.
7. Commits the transaction.

After a successful cancellation, the released seats can be reserved again.

The reservation state is never changed back to confirmed by the cancellation operation, preventing an old cancellation request from resurrecting a previously completed reservation.

---

## 7. Consistency vs Availability

The reservation path prioritizes **correctness and consistency** over accepting every concurrent request.

For a hot seat:

```text
500 concurrent requests
        |
        v
1 successful reservation
        |
        v
499 conflict responses
```

A seat cannot be sold twice simply to improve request success rates.

PostgreSQL acts as the serialization point for conflicting reservations.

The API returns `409 Conflict` for expected business contention rather than returning a server error.

---

## 8. Reconciliation Invariant

The show-state endpoint calculates:

```text
available
held
confirmed
```

The system maintains the invariant:

```text
available + held + confirmed = total seats
```

The burst test verifies this after concurrent activity.

The current implementation uses explicit cancellation rather than timed holds, so normal reservations have:

```text
held = 0
```

---

## 9. Authentication and Identity

Reservation identity is derived from the authorization token.

The request body does not contain a trusted `user_id`.

The authenticated identity is passed into the reservation service from the authentication dependency.

This prevents a client from attempting to reserve seats as another user by supplying a different user ID in the request body.

The authentication mechanism is intentionally simple token-based authentication for the scope of the take-home exercise.

---

## 10. Observability

The service exposes:

```text
GET /health/live
GET /health/ready
GET /metrics
```

### Liveness

Confirms that the application process is running.

### Readiness

Performs a PostgreSQL connectivity check and returns `503` if the database is unavailable.

### Metrics

The application exposes metrics for:

- Confirmed reservations
- Declined reservations by reason
- Available seats
- Reservation latency
- HTTP requests

Structured JSON request logs contain:

- Request ID
- HTTP method
- Path
- Status code
- Request duration

The request ID is also returned through:

```text
X-Request-ID
```

This allows an individual request to be correlated with application logs.

---

## 11. Load Testing

The project includes:

```text
scripts/burst.py
```

The script tests:

- Hot-seat concurrency
- Per-user reservation limits
- Idempotency retries
- Final reconciliation

The local hot-seat test was executed with 500 concurrent users.

Verified result:

```text
201: 1
409: 499
5xx: 0
```

The test also verified:

```text
available + held + confirmed = total seats
```

and completed successfully.

---

## 12. Database Design

The main tables are:

### `shows`

Stores show-level configuration:

- Show name
- Ticket price in paise
- Total seats
- Per-user limit

### `show_seats`

Stores the authoritative state of every seat:

- Show
- Seat number
- Status
- Reserved user

### `reservations`

Stores reservation-level information:

- User
- Show
- Amount
- Status
- Idempotency key
- Request hash

All monetary values are stored as integer **paise**, never floating-point values.

### `reservation_seats`

Maps reservations to individual seats.

### `show_user_counters`

Maintains the number of confirmed seats for each user/show combination.

---

## 13. Deployment

The application is containerized using Docker and deployed on Railway.

The database schema is initialized through Alembic migrations.

The deployed service exposes:

```text
https://reservationsystem-production-41a7.up.railway.app
```

Health and API endpoints are publicly accessible for verification.

---

## 14. Testing Strategy

The test suite covers:

- Show creation
- Seat reservation
- Concurrent hot-seat reservation
- Per-user limits
- Multi-seat all-or-nothing behavior
- Idempotency
- Concurrent idempotency retries
- Cancellation
- Concurrent cancellation
- Authentication identity
- User spoofing attempts
- Reconciliation

The key concurrency acceptance criteria are:

```text
No duplicate confirmed seat
No per-user limit violation
No unexpected 5xx during normal contention
No duplicate idempotent reservation
Reconciliation invariant remains valid
```

---

## 15. AI Usage

AI assistance was used during development for:

- Architecture discussion
- Implementation guidance
- Debugging
- Concurrency test design
- Documentation
- Code review

The implementation was executed, tested, debugged, and validated by the developer.

---

## 16. Future Improvements

For a larger production system, the following could be added:

- Stronger authentication such as OAuth2/JWT
- Admin authorization for show creation
- Time-based seat holds and automatic expiry
- Payment integration with payment idempotency
- Distributed tracing
- Centralized log aggregation
- Redis for non-critical caching
- Kafka/event streaming for downstream analytics
- Kubernetes-based deployment
- Database connection-pool tuning based on measured production load
- Dedicated migration jobs instead of running migrations during application startup