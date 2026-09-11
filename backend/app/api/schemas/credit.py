"""Credit/wallet schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, computed_field

from app.api.schemas.common import ORMModel

# The widest credit figure the ledger can hold. `CreditTransaction.amount` and `CreditWallet`
# balances are Numeric(18,2), so anything at or beyond 10^16 is rejected by the database — as a
# 500, until this bound turned it into a validation error. The cap is also a business guard: an
# unbounded top-up let one request mint more credit than the platform could ever spend.
MAX_CREDIT = Decimal("1000000000000")   # 10^12


# A credit amount as the ledger stores it: two decimal places, half-up, and never a value that
# rounds away to nothing. Declared as a type so the rejection happens during request validation
# (a clean 422) rather than deep in a handler, where it surfaced as a 500.
CreditAmount = Annotated[Decimal, AfterValidator(lambda v: quantized_credit(v))]


def quantized_credit(v: Decimal) -> Decimal:
    """Round to the ledger's two decimal places and refuse what rounds away to nothing.

    A request for 0.001 used to be accepted, stored as 0.00, and reported as a successful
    top-up that moved no money.
    """
    # Half-up, matching pricing.round_credit. Decimal's default is banker's rounding, which
    # would send 1.005 down to 1.00 — money rounds away from zero at the midpoint.
    q = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if q == 0:
        raise ValueError("amount rounds to zero at two decimal places")
    return q


class WalletRead(ORMModel):
    id: str
    owner_type: str
    owner_id: str
    balance: Decimal
    reserved: Decimal
    monthly_grant: Decimal = Decimal("0")   # monthly refill amount; 0 disables refills
    owner_name: str | None = None           # owner name (user, group, or organization), for display

    @computed_field  # available = balance - reserved. Computed here so the wallet screen and the
    # dashboard show the same number.
    @property
    def available(self) -> Decimal:
        return self.balance - self.reserved


class MonthlyGrantBody(BaseModel):
    # Set a child wallet's monthly refill, from the administrator one level up. 0 disables it.
    amount: Decimal = Field(ge=0, le=MAX_CREDIT)


class TopupRequestBody(BaseModel):
    amount: CreditAmount = Field(gt=0, le=MAX_CREDIT)
    note: str | None = None
    wallet_id: str | None = None   # the console sends it in the body; absent means the caller's personal wallet


class AdjustBody(BaseModel):
    amount: CreditAmount = Field(ge=-MAX_CREDIT, le=MAX_CREDIT)   # signed
    reason: str


class TransferBody(BaseModel):
    to_wallet_id: str
    amount: CreditAmount = Field(gt=0, le=MAX_CREDIT)


class AllocateBody(BaseModel):
    # Hierarchical allocation and reclaim: organization to project for an org_admin, project to user
    # for a group_admin. super_admin may do either.
    from_wallet_id: str
    to_wallet_id: str
    amount: CreditAmount = Field(gt=0, le=MAX_CREDIT)
    reason: str | None = None


class BulkAllocateBody(BaseModel):
    # Allocate the same amount from the group's wallet to EVERY member's personal wallet in one
    # idempotent operation — the start-of-term "give the whole class N credits" action.
    group_id: str
    amount: CreditAmount = Field(gt=0, le=MAX_CREDIT)
    reason: str | None = None


class BulkMonthlyGrantBody(BaseModel):
    # Set the same monthly refill on every member wallet of a group. 0 disables it.
    group_id: str
    amount: Decimal = Field(ge=0, le=MAX_CREDIT)


class AllocationRequestCreate(BaseModel):
    amount: CreditAmount = Field(gt=0, le=MAX_CREDIT)
    level: str = Field(default="user", pattern="^(user|group|org)$")
    group_id: str | None = None     # for level=user, the group funding it; for level=project, that group
    org_id: str | None = None         # level=org
    note: str | None = None


class AllocationRejectBody(BaseModel):
    reason: str


class TransactionRead(ORMModel):
    id: str
    type: str                 # topup|hold|consume|refund|settle|adjust
    amount: Decimal
    balance_after: Decimal
    ref: str | None = None
    # Human name for the ref: the session's name for session refs, a short label otherwise -
    # so the ledger reads "which session spent this", not an opaque ULID.
    ref_name: str | None = None
    created_at: datetime | None = None
    # Set when this row is a rollup of several transactions (per-minute consume for one session).
    # entry_count == 1 means a single transaction and the period fields are absent.
    entry_count: int = 1
    period_start: datetime | None = None
    period_end: datetime | None = None
    # The session's billing is closed (its zero-amount settle marker folded into this row).
    settled: bool = False
    # The stream behind this rollup is still accruing: the session is running.
    live: bool = False


class TopupRejectBody(BaseModel):
    reason: str = Field(min_length=1)   # rejection reason; required, persisted, and included in the notification and audit entry


class TopupRequestRead(BaseModel):
    # Mirrors the serialised shape of GET /credits/topup-requests, which is assembled as a dict
    # rather than mapped from the ORM.
    id: str
    wallet_id: str
    amount: str                     # serialised as a string, from Decimal
    status: str
    requester_id: str | None = None
    requester_name: str | None = None
    note: str | None = None            # requester's justification
    wallet_owner_type: str | None = None   # user|group — a member's own top-up vs group funding
    wallet_owner_name: str | None = None
    decided_reason: str | None = None  # approver's note / rejection reason
    decided_by: str | None = None
    created_at: str                 # ISO 8601 string


class TopupRequestListResponse(BaseModel):
    data: list[TopupRequestRead]


class SpendDayRead(BaseModel):
    """One day of spend (consume + storage), for the wallet's usage chart."""
    date: str      # YYYY-MM-DD in the caller's timezone (tz_offset_min)
    amount: float  # credits drained that day, absolute
