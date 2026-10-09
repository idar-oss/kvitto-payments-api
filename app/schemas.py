from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator


class PaymentMethod(StrEnum):
    card = "card"
    sbp = "sbp"
    installment = "installment"


class PaymentStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: int


class PaymentCreate(BaseModel):
    tariff_id: int
    email: EmailStr
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def validate_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized != "KVITTO10":
            raise ValueError("unknown promo code")
        return normalized

    @model_validator(mode="after")
    def validate_installment(self) -> "PaymentCreate":
        if self.method == PaymentMethod.installment and self.installment_months is None:
            raise ValueError("installment_months is required for installment")
        if self.method != PaymentMethod.installment and self.installment_months is not None:
            raise ValueError("installment_months is only allowed for installment")
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: PaymentStatus
    tariff_id: int
    amount: int
    discount: int
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None
    email: EmailStr
    created_at: datetime


class BankWebhook(BaseModel):
    payment_id: int
    status: PaymentStatus
