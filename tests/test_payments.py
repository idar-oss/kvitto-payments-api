import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Payment


BASE_PAYMENT = {
    "tariff_id": 2,
    "email": "student@example.com",
    "method": "card",
}


def test_get_tariffs(client):
    response = client.get("/tariffs")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "title": "basic", "price": 990000},
        {"id": 2, "title": "standard", "price": 1990000},
        {"id": 3, "title": "premium", "price": 2990000},
    ]


@pytest.mark.parametrize(
    ("promo_code", "expected_amount", "expected_discount"),
    [
        (None, 1_990_000, 0),
        ("KVITTO10", 1_791_000, 199_000),
        ("kvitto10", 1_791_000, 199_000),
    ],
)
def test_amount_with_and_without_promo(
    client, promo_code, expected_amount, expected_discount
):
    payload = BASE_PAYMENT.copy()
    if promo_code is not None:
        payload["promo_code"] = promo_code

    response = client.post("/payments", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == expected_amount
    assert body["discount"] == expected_discount


@pytest.mark.parametrize("months", [3, 6, 12])
def test_installment_schedule_sums_to_amount(client, months):
    response = client.post(
        "/payments",
        json={
            "tariff_id": 2,
            "email": "student@example.com",
            "method": "installment",
            "installment_months": months,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["schedule"]) == months
    assert sum(body["schedule"]) == body["amount"]

    base, remainder = divmod(body["amount"], months)
    assert body["schedule"] == [
        base + 1 if index < remainder else base for index in range(months)
    ]


def test_idempotency_key_does_not_create_second_payment(
    client, db_session: Session
):
    headers = {"Idempotency-Key": "checkout-123"}

    first = client.post("/payments", json=BASE_PAYMENT, headers=headers)
    second = client.post("/payments", json=BASE_PAYMENT, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert db_session.scalar(select(func.count()).select_from(Payment)) == 1


def test_invalid_status_transition_returns_409_and_keeps_status(client):
    created = client.post("/payments", json=BASE_PAYMENT).json()
    payment_id = created["id"]

    response = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "refunded"},
    )

    assert response.status_code == 409
    assert response.json() == {"error": "invalid_transition"}
    payment = client.get(f"/payments/{payment_id}").json()
    assert payment["status"] == "pending"


def test_nonexistent_payment_returns_404(client):
    response = client.get("/payments/999999")

    assert response.status_code == 404


def test_valid_status_chain_pending_succeeded_refunded(client):
    payment_id = client.post("/payments", json=BASE_PAYMENT).json()["id"]

    succeeded = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "succeeded"},
    )
    refunded = client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "refunded"},
    )

    assert succeeded.status_code == 200
    assert succeeded.json() == {"result": "ok"}
    assert refunded.status_code == 200
    assert client.get(f"/payments/{payment_id}").json()["status"] == "refunded"


def test_unknown_promo_code_returns_422(client):
    response = client.post(
        "/payments",
        json={**BASE_PAYMENT, "promo_code": "NOPE"},
    )

    assert response.status_code == 422


def test_installment_requires_valid_months(client):
    missing = client.post(
        "/payments",
        json={**BASE_PAYMENT, "method": "installment"},
    )
    invalid = client.post(
        "/payments",
        json={
            **BASE_PAYMENT,
            "method": "installment",
            "installment_months": 5,
        },
    )

    assert missing.status_code == 422
    assert invalid.status_code == 422
