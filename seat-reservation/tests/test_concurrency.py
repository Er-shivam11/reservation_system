import concurrent.futures
import uuid

import requests


BASE_URL = "http://localhost:8000"


def create_test_show():
    response = requests.post(
        f"{BASE_URL}/shows",
        json={
            "name": f"Concurrency Test {uuid.uuid4()}",
            "seats": ["HOT-1"],
            "price_paise": 1000,
        },
    )

    assert response.status_code == 201
    return response.json()["id"]


def reserve_hot_seat(show_id, index):
    headers = {
        "Authorization": f"Bearer user-{index}",
        "Idempotency-Key": f"concurrency-{uuid.uuid4()}",
    }

    response = requests.post(
        f"{BASE_URL}/shows/{show_id}/reserve",
        headers=headers,
        json={
            "seats": ["HOT-1"],
        },
        timeout=10,
    )

    return response.status_code


def test_hot_seat_concurrency():
    show_id = create_test_show()

    concurrency = 500

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:
        futures = [
            executor.submit(
                reserve_hot_seat,
                show_id,
                index,
            )
            for index in range(concurrency)
        ]

        results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    success_count = results.count(201)
    conflict_count = results.count(409)
    server_error_count = sum(
        status >= 500
        for status in results
    )

    print("\nResults:")
    print(f"201 success: {success_count}")
    print(f"409 conflict: {conflict_count}")
    print(f"5xx errors: {server_error_count}")

    assert success_count == 1
    assert conflict_count == 499
    assert server_error_count == 0