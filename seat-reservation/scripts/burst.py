import concurrent.futures
import sys
import uuid
from collections import Counter

import requests


CONCURRENCY = 500
TIMEOUT = 30


def create_show(base_url):
    seats = [f"A{i}" for i in range(1, 101)]

    response = requests.post(
        f"{base_url}/shows",
        json={
            "name": f"Burst Test {uuid.uuid4()}",
            "seats": seats,
            "price_paise": 25000,
        },
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.json()["id"]


def reserve(base_url, show_id, user_id, seats, key):
    try:
        response = requests.post(
            f"{base_url}/shows/{show_id}/reserve",
            headers={
                "Authorization": f"Bearer {user_id}",
                "Idempotency-Key": key,
            },
            json={
                "seats": seats,
            },
            timeout=TIMEOUT,
        )

        return {
            "status": response.status_code,
            "body": response.json(),
        }

    except Exception as exc:
        return {
            "status": 599,
            "body": {
                "error": str(exc),
            },
        }


def get_state(base_url, show_id):
    response = requests.get(
        f"{base_url}/shows/{show_id}",
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.json()


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/burst.py <BASE_URL>")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")

    print(f"Target: {base_url}")
    print(f"Concurrency: {CONCURRENCY}")

    show_id = create_show(base_url)

    print(f"Show ID: {show_id}")

    # ---------------------------------------------------------
    # 1. HOT-SEAT STORM
    # ---------------------------------------------------------

    print("\n=== HOT-SEAT STORM ===")

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=CONCURRENCY
    ) as executor:

        futures = [
            executor.submit(
                reserve,
                base_url,
                show_id,
                f"burst-user-{i}",
                ["A1"],
                f"hot-seat-{uuid.uuid4()}",
            )
            for i in range(CONCURRENCY)
        ]

        results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    statuses = Counter(
        result["status"]
        for result in results
    )

    reasons = Counter(
        result["body"].get("detail", {}).get("reason")
        for result in results
        if isinstance(result["body"].get("detail"), dict)
    )

    print(f"201: {statuses[201]}")
    print(f"409: {statuses[409]}")
    print(f"5xx: {sum(status >= 500 for status in statuses)}")
    print(f"Other: {sum(status < 200 or status >= 600 for status in statuses)}")
    print(f"Decline reasons: {dict(reasons)}")

    assert statuses[201] == 1
    assert statuses[409] == CONCURRENCY - 1
    assert sum(
        count
        for status, count in statuses.items()
        if status >= 500
    ) == 0

    # ---------------------------------------------------------
    # 2. PER-USER LIMIT
    # ---------------------------------------------------------

    print("\n=== PER-USER LIMIT ===")

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=10
    ) as executor:

        futures = [
            executor.submit(
                reserve,
                base_url,
                show_id,
                "limit-burst-user",
                [f"A{i}"],
                f"limit-{uuid.uuid4()}",
            )
            for i in range(2, 12)
        ]

        limit_results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    limit_statuses = Counter(
        result["status"]
        for result in limit_results
    )

    print(f"201: {limit_statuses[201]}")
    print(f"409: {limit_statuses[409]}")
    print(
        f"5xx: {sum(status >= 500 for status in limit_statuses)}"
    )

    assert limit_statuses[201] <= 4
    assert sum(
        count
        for status, count in limit_statuses.items()
        if status >= 500
    ) == 0

    # ---------------------------------------------------------
    # 3. IDEMPOTENCY RETRY
    # ---------------------------------------------------------

    print("\n=== IDEMPOTENCY RETRY ===")

    idem_key = f"retry-{uuid.uuid4()}"

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=20
    ) as executor:

        futures = [
            executor.submit(
                reserve,
                base_url,
                show_id,
                "idempotent-user",
                ["A20"],
                idem_key,
            )
            for _ in range(20)
        ]

        idem_results = [
            future.result()
            for future in concurrent.futures.as_completed(futures)
        ]

    idem_statuses = Counter(
        result["status"]
        for result in idem_results
    )

    reservation_ids = {
        result["body"].get("id")
        for result in idem_results
        if result["status"] in (200, 201)
    }

    print(f"201/200: {idem_statuses[201] + idem_statuses[200]}")
    print(f"409: {idem_statuses[409]}")
    print(f"Unique reservation IDs: {reservation_ids}")

    assert len(reservation_ids) == 1
    assert all(
        result["status"] in (200, 201)
        for result in idem_results
    )

    # ---------------------------------------------------------
    # 4. FINAL RECONCILIATION
    # ---------------------------------------------------------

    print("\n=== FINAL RECONCILIATION ===")

    state = get_state(base_url, show_id)

    print(f"Total:     {state['total_seats']}")
    print(f"Available: {state['available']}")
    print(f"Held:      {state['held']}")
    print(f"Confirmed: {state['confirmed']}")

    total = (
        state["available"]
        + state["held"]
        + state["confirmed"]
    )

    print(f"Calculated total: {total}")

    assert total == state["total_seats"]

    print("\n================================")
    print("BURST TEST PASSED")
    print("================================")


if __name__ == "__main__":
    main()