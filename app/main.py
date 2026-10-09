from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, get_db, get_engine, get_session_factory
from .models import Payment, Tariff
from .schemas import BankWebhook, PaymentCreate, PaymentMethod, PaymentOut, TariffOut
from .services import build_installment_schedule, calculate_discount, can_change_status


TARIFFS = (
    {"id": 1, "title": "basic", "price": 990_000},
    {"id": 2, "title": "standard", "price": 1_990_000},
    {"id": 3, "title": "premium", "price": 2_990_000},
)


def seed_tariffs() -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        existing_ids = set(db.scalars(select(Tariff.id)).all())
        for data in TARIFFS:
            if data["id"] not in existing_ids:
                db.add(Tariff(**data))
        db.commit()


def init_database() -> None:
    Base.metadata.create_all(bind=get_engine())
    seed_tariffs()


def create_app(initialize_database: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if initialize_database:
            init_database()
        yield

    app = FastAPI(title="Kvitto Payments API", version="1.0.0", lifespan=lifespan)

    @app.get("/tariffs", response_model=list[TariffOut])
    def get_tariffs(db: Session = Depends(get_db)):
        return db.scalars(select(Tariff).order_by(Tariff.id)).all()

    @app.post(
        "/payments",
        response_model=PaymentOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_payment(
        payload: PaymentCreate,
        response: Response,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        db: Session = Depends(get_db),
    ):
        if idempotency_key:
            existing = db.scalar(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            if existing is not None:
                response.status_code = status.HTTP_200_OK
                return existing

        tariff = db.get(Tariff, payload.tariff_id)
        if tariff is None:
            raise HTTPException(status_code=404, detail="tariff_not_found")

        discount = calculate_discount(tariff.price, payload.promo_code)
        amount = tariff.price - discount
        schedule = None
        if payload.method == PaymentMethod.installment:
            assert payload.installment_months is not None
            schedule = build_installment_schedule(amount, payload.installment_months)

        payment = Payment(
            status="pending",
            tariff_id=tariff.id,
            amount=amount,
            discount=discount,
            method=payload.method.value,
            installment_months=payload.installment_months,
            schedule=schedule,
            email=str(payload.email),
            idempotency_key=idempotency_key,
        )
        db.add(payment)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if idempotency_key:
                existing = db.scalar(
                    select(Payment).where(Payment.idempotency_key == idempotency_key)
                )
                if existing is not None:
                    response.status_code = status.HTTP_200_OK
                    return existing
            raise
        db.refresh(payment)
        return payment

    @app.get("/payments/{payment_id}", response_model=PaymentOut)
    def get_payment(payment_id: int, db: Session = Depends(get_db)):
        payment = db.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="payment_not_found")
        return payment

    @app.post("/webhooks/bank")
    def bank_webhook(payload: BankWebhook, db: Session = Depends(get_db)):
        payment = db.get(Payment, payload.payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="payment_not_found")

        if not can_change_status(payment.status, payload.status):
            return JSONResponse(
                status_code=409,
                content={"error": "invalid_transition"},
            )

        payment.status = payload.status.value
        db.commit()
        return {"result": "ok"}

    return app


app = create_app()
