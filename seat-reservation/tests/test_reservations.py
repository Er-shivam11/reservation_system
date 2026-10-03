import concurrent.futures
import uuid
import requests

BASE_URL = "http://localhost:8000"


def create_show(seats):
    r = requests.post(
        f"{BASE_URL}/shows",
        json={
            "name": f"Test {uuid.uuid4()}",
            "seats": seats,
            "price_paise": 1000,
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


def reserve(show_id, user, seats):
    return requests.post(
        f"{BASE_URL}/shows/{show_id}/reserve",
        headers={
            "Authorization": f"Bearer {user}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"seats": seats},
        timeout=10,
    )


def test_per_user_limit():
    show_id = create_show(
        ["L1", "L2", "L3", "L4", "L5"]
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(
            lambda seat: reserve(show_id, "limit-user", [seat]),
            ["L1", "L2", "L3", "L4", "L5"],
        ))

    codes = [r.status_code for r in results]

    print("\nPer-user:", codes)

    assert codes.count(201) == 4
    assert codes.count(409) == 1
    assert not any(code >= 500 for code in codes)


def test_multi_seat_all_or_nothing():
    show_id = create_show(["M1", "M2", "M3"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda data: reserve(show_id, data[0], data[1]),
            [
                ("user-1", ["M1", "M2"]),
                ("user-2", ["M2", "M3"]),
            ],
        ))

    codes = [r.status_code for r in results]

    print("\nMulti-seat:", codes)

    assert codes.count(201) == 1
    assert codes.count(409) == 1
    assert not any(code >= 500 for code in codes)


def test_cancellation_concurrently():
    show_id = create_show(["C1"])

    r = reserve(show_id, "cancel-user", ["C1"])
    assert r.status_code == 201

    reservation_id = r.json()["id"]

    def cancel():
        return requests.post(
            f"{BASE_URL}/reservations/{reservation_id}/cancel",
            headers={"Authorization": "Bearer cancel-user"},
            timeout=10,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: cancel(), range(2)))

    codes = [r.status_code for r in results]

    print("\nCancellation:", codes)

    assert codes.count(200) == 1
    assert codes.count(409) == 1
    assert not any(code >= 500 for code in codes)


def test_user_cannot_spoof_user_id():
    show_id = create_show(["AUTH1"])

    r = requests.post(
        f"{BASE_URL}/shows/{show_id}/reserve",
        headers={
            "Authorization": "Bearer real-user",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={
            "seats": ["AUTH1"],
            "user_id": "fake-user",
        },
    )

    assert r.status_code == 201
    assert r.json()["user_id"] == "real-user"


def test_reconciliation():
    show_id = create_show(["S1", "S2", "S3", "S4"])

    reserve(show_id, "state-user", ["S1"])

    r = requests.get(
        f"{BASE_URL}/shows/{show_id}",
        timeout=10,
    )

    assert r.status_code == 200

    data = r.json()

    print("\nReconciliation:")
    print(data)

    assert (
        data["available"]
        + data["held"]
        + data["confirmed"]
        == data["total_seats"]
    )