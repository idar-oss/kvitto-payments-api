from .schemas import PaymentStatus


PROMO_PERCENT = 10


def calculate_discount(price: int, promo_code: str | None) -> int:
    if promo_code is None:
        return 0
    return price * PROMO_PERCENT // 100


def build_installment_schedule(amount: int, months: int) -> list[int]:
    base, remainder = divmod(amount, months)
    return [base + 1 if index < remainder else base for index in range(months)]


def can_change_status(current: str, new: PaymentStatus) -> bool:
    allowed = {
        PaymentStatus.pending: {PaymentStatus.succeeded, PaymentStatus.failed},
        PaymentStatus.succeeded: {PaymentStatus.refunded},
        PaymentStatus.failed: set(),
        PaymentStatus.refunded: set(),
    }
    return new in allowed[PaymentStatus(current)]
