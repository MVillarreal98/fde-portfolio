"""Central configuration: tolerances, expected schemas and rule switches.

Every threshold lives here so finance can tighten or relax rules without
touching the detection logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Columns each source MUST have. Extra columns (settled_at, processor_fee, ...)
# are accepted and ignored: settlements are compared gross, see README limits.
OPS_COLUMNS = [
    "transaction_id",
    "merchant",
    "channel",
    "amount",
    "currency",
    "status",
    "recorded_at",
]

BILLING_COLUMNS = [
    "statement_id",
    "transaction_ref",
    "settlement_amount",
    "currency",
]

# Statuses whose expected NET settlement is zero: the charge was reversed, so it
# should either never settle or settle and be reversed (+X and -X) in the file.
VOID_STATUSES = frozenset({"refunded", "cancelled", "canceled", "void"})

ENGINES = ("pandas", "sql")


def parse_tolerance(value: Decimal | float | int | str) -> Decimal:
    """Validate a money tolerance: finite, >= 0 and a whole number of cents."""
    try:
        tol = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"tolerance must be a number, got {value!r}") from None
    if not tol.is_finite() or tol < 0:
        raise ValueError(f"tolerance must be >= 0, got {value!r}")
    if (tol * 100) != (tol * 100).to_integral_value():
        raise ValueError(f"tolerance must be a whole number of cents, got {value!r}")
    return tol


@dataclass
class Config:
    ops_path: Path
    billing_path: Path
    output_dir: Path = Path("output")

    # An absolute difference <= amount_tolerance (currency units) is noise, not a defect.
    amount_tolerance: Decimal | float | str = Decimal("0.01")

    # Two captures with the same merchant, channel and amount recorded within
    # this many minutes of each other form a duplicate-charge candidate group
    # (only reported when the group has fewer settlements than captures).
    duplicate_window_minutes: int = 10

    engine: str = "pandas"

    def __post_init__(self) -> None:
        self.ops_path = Path(self.ops_path)
        self.billing_path = Path(self.billing_path)
        self.output_dir = Path(self.output_dir)
        self.amount_tolerance = parse_tolerance(self.amount_tolerance)
        if int(self.duplicate_window_minutes) < 0:
            raise ValueError("duplicate_window_minutes must be >= 0")
        self.duplicate_window_minutes = int(self.duplicate_window_minutes)
        if self.engine not in ENGINES:
            raise ValueError(f"engine must be one of {ENGINES}, got {self.engine!r}")

    @property
    def tolerance_cents(self) -> int:
        return int(Decimal(self.amount_tolerance) * 100)
