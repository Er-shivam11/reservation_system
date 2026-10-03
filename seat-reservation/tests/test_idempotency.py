import concurrent.futures
import threading
import uuid

import requests


BASE_URL = "http://localhost:8000"


def create_test_show():
    response = requests.post(
        f"{BASE_URL}/shows",
        json={
            "name": f"Idempotency Test {uuid.uuid4()}",
            "seats": ["IDEM-1", "IDEM-2"],
            "price_paise": 1000,
        },
        timeout=10,
    )

    assert response.status_code == 201
    return response.json()["id"]


def reserve(show_id, user_id, seats, idempotency_key):
    return requests.post(
        f"{BASE_URL}/shows/{show_id}/reserve",
        headers={
            "Authorization": f"Bearer {user_id}",
            "Idempotency-Key": idempotency_key,
        },
        json={
            "seats": seats,
        },
        timeout=10,
    )


def test_same_idempotency_key_concurrently():
    show_id = create_test_show()

    user_id = "idem-concurrent-user"
    idempotency_key = f"idem-{uuid.uuid4()}"
    request_barrier = threading.Barrier(20)

    def concurrent_reserve():
        request_barrier.wait(timeout=10)
        return reserve(
            show_id,
            user_id,
            ["IDEM-1"],
            idempotency_key,
        )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=request_barrier.parties
    ) as executor:

        futures = [
            executor.submit(concurrent_reserve)
            for _ in range(request_barrier.parties)
        ]

        results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    status_codes = [response.status_code for response in results]

    print("\nIdempotency Results:")
    print(f"Status codes: {status_codes}")
    print(f"Responses: {[response.text for response in results]}")  

    # First request creates the reservation.
    # Concurrent retries return the same reservation.
    unexpected_responses = [
        (response.status_code, response.text)
        for response in results
        if response.status_code not in (200, 201)
    ]
    assert not unexpected_responses, unexpected_responses

    reservation_ids = {
        response.json()["id"]
        for response in results
    }

    print(f"Unique reservation IDs: {reservation_ids}")

    # Every retry must point to the same reservation.
    assert len(reservation_ids) == 1, reservation_ids


def test_same_idempotency_key_different_request():
    show_id = create_test_show()

    user_id = "idem-different-request-user"
    idempotency_key = f"idem-different-{uuid.uuid4()}"

    first = reserve(
        show_id,
        user_id,
        ["IDEM-1"],
        idempotency_key,
    )

    assert first.status_code == 201

    second = reserve(
        show_id,
        user_id,
        ["IDEM-2"],
        idempotency_key,
    )

    assert second.status_code == 409

    print("\nDifferent request with same key:")
    print(second.json())