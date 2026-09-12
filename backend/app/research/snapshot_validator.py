"""
snapshot_validator.py  —  Two-tier validation: DATA_VALID and TRADE_ELIGIBLE.

SEPARATION OF CONCERNS
======================
DATA_VALID     — Is this snapshot structurally sound for research storage?
TRADE_ELIGIBLE — Is this market suitable for live paper trading?

A market with a wide spread (0.98) is DATA_VALID=True but TRADE_ELIGIBLE=False.
This allows us to collect rich historical observations without letting bad
execution conditions into the strategy.

HARD REJECTS (data is malformed — never store):
  - source is not "POLYMARKET"
  - price is None or outside [0.0, 1.0]
  - bid or ask is None
  - bid > ask  (inverted book — corrupt data)
  - spread < 0 (impossible)
  - market_id is missing
  - both bid_depth AND ask_depth are 0 AND price is at an extreme (0 or 1)

SOFT FLAGS (data is valid but not trade-worthy):
  - spread > MAX_TRADE_SPREAD
  - total depth < MIN_TRADE_DEPTH
  - liquidity < MIN_TRADE_LIQUIDITY
"""

from __future__ import annotations
from dataclasses import dataclass
from app.db.schemas import MarketTick
from app.config import settings


@dataclass
class SnapshotClassification:
    data_valid: bool
    trade_eligible: bool
    reject_reason: str        # non-empty only when data_valid=False
    ineligibility_reasons: list[str]  # non-empty when trade_eligible=False


def classify_snapshot(tick: MarketTick) -> SnapshotClassification:
    """
    Classifies a tick as DATA_VALID and/or TRADE_ELIGIBLE.

    DATA_VALID=False means the tick is malformed and must not be stored.
    DATA_VALID=True, TRADE_ELIGIBLE=False means store for research but never trade.
    DATA_VALID=True, TRADE_ELIGIBLE=True means full pipeline.
    """
    ineligible_reasons: list[str] = []

    # ── HARD REJECTS ───────────────────────────────────────────────────────────

    if tick.source != "POLYMARKET":
        return SnapshotClassification(
            data_valid=False, trade_eligible=False,
            reject_reason=f"Unexpected source: {tick.source}",
            ineligibility_reasons=[],
        )

    if tick.market_id is None or tick.market_id.strip() == "":
        return SnapshotClassification(
            data_valid=False, trade_eligible=False,
            reject_reason="Missing market_id",
            ineligibility_reasons=[],
        )

    if tick.price is None or not (0.0 <= tick.price <= 1.0):
        return SnapshotClassification(
            data_valid=False, trade_eligible=False,
            reject_reason=f"Invalid price: {tick.price}",
            ineligibility_reasons=[],
        )

    if tick.bid is None or tick.ask is None:
        return SnapshotClassification(
            data_valid=False, trade_eligible=False,
            reject_reason="Missing bid or ask",
            ineligibility_reasons=[],
        )

    if tick.bid > tick.ask:
        return SnapshotClassification(
            data_valid=False, trade_eligible=False,
            reject_reason=f"Inverted book: bid ({tick.bid}) > ask ({tick.ask})",
            ineligibility_reasons=[],
        )

    if tick.spread is not None and tick.spread < 0:
        return SnapshotClassification(
            data_valid=False, trade_eligible=False,
            reject_reason=f"Negative spread: {tick.spread}",
            ineligibility_reasons=[],
        )

    bid_d = tick.bid_depth or 0.0
    ask_d = tick.ask_depth or 0.0

    # ── TRADE ELIGIBILITY CHECKS ───────────────────────────────────────────────

    if bid_d == 0.0 and ask_d == 0.0:
        ineligible_reasons.append("EMPTY_BOOK")

    spread = tick.spread or (tick.ask - tick.bid)

    if spread > settings.max_trade_spread:
        ineligible_reasons.append(
            f"Spread {spread:.4f} > max_trade_spread {settings.max_trade_spread}"
        )

    total_depth = bid_d + ask_d
    if total_depth < settings.min_trade_depth:
        ineligible_reasons.append(
            f"Total depth {total_depth:.1f} < min_trade_depth {settings.min_trade_depth}"
        )

    liq = tick.liquidity or 0.0
    if liq < settings.min_trade_liquidity:
        ineligible_reasons.append(
            f"Liquidity {liq:.1f} < min_trade_liquidity {settings.min_trade_liquidity}"
        )

    trade_eligible = len(ineligible_reasons) == 0

    return SnapshotClassification(
        data_valid=True,
        trade_eligible=trade_eligible,
        reject_reason="",
        ineligibility_reasons=ineligible_reasons,
    )


# ── Backward-compat shim used by existing code and tests ──────────────────────
def validate_snapshot(tick: MarketTick) -> tuple[bool, str]:
    """
    Legacy interface: returns (data_valid, reject_reason).
    Use classify_snapshot() for full DATA_VALID / TRADE_ELIGIBLE classification.
    """
    result = classify_snapshot(tick)
    return result.data_valid, result.reject_reason
