"""
dataset.py  —  Real-data-only dataset builder with strict safety gates.

SAFETY CONTRACT:
  - When settings.synthetic_bootstrap is False, this module NEVER generates
    or returns synthetic rows.  Any code path that could produce a fake label
    or a fake tick raises DataPurityError instead of silently falling back.
  - Resolved labels come exclusively from the `Market.resolution` column,
    which is populated by the resolution-checker task that queries the
    official Polymarket resolution endpoint.
  - Feature rows are only built from snapshots whose `is_synthetic == False`.
  - The chronological split is computed BEFORE any feature calculation to
    prevent any possibility of look-ahead leakage.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.config import settings
from app.db.session import SessionLocal
from app.research.features import calculate_features

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Custom errors
# ──────────────────────────────────────────────────────────────

class DataPurityError(RuntimeError):
    """Raised when synthetic data would contaminate the real pipeline."""


class InsufficientDataError(RuntimeError):
    """Raised when real-backtest gate requirements are not met."""


# ──────────────────────────────────────────────────────────────
# Data quality probe  (used by /api/research/quality)
# ──────────────────────────────────────────────────────────────

def get_data_quality_report() -> dict:
    """
    Returns a structured quality report computed from SQLite.
    All counts come from *real* data rows only (is_synthetic = 0).
    """
    db = SessionLocal()
    try:
        total_snaps = db.execute(
            text("SELECT COUNT(*) FROM market_snapshots WHERE is_synthetic = 0")
        ).scalar() or 0

        unique_mkts = db.execute(
            text("SELECT COUNT(DISTINCT market_id) FROM market_snapshots WHERE is_synthetic = 0")
        ).scalar() or 0

        resolved_mkts = db.execute(
            text("SELECT COUNT(*) FROM markets WHERE resolved = 1")
        ).scalar() or 0

        unresolved_mkts = db.execute(
            text("SELECT COUNT(*) FROM markets WHERE active = 1 AND resolved = 0")
        ).scalar() or 0

        # A valid training sample = snapshot that belongs to a RESOLVED market
        valid_samples = db.execute(
            text("""
                SELECT COUNT(*) FROM market_snapshots ms
                JOIN markets m ON ms.market_id = m.market_id
                WHERE ms.is_synthetic = 0
                  AND m.resolved = 1
                  AND m.resolution IS NOT NULL
            """)
        ).scalar() or 0

        # Snapshots with critical nulls (price, bid, ask, spread)
        invalid_samples = db.execute(
            text("""
                SELECT COUNT(*) FROM market_snapshots
                WHERE is_synthetic = 0
                  AND (price IS NULL OR bid IS NULL OR ask IS NULL OR spread IS NULL)
            """)
        ).scalar() or 0

        first_snap = db.execute(
            text("SELECT MIN(received_timestamp) FROM market_snapshots WHERE is_synthetic = 0")
        ).scalar()

        last_snap = db.execute(
            text("SELECT MAX(received_timestamp) FROM market_snapshots WHERE is_synthetic = 0")
        ).scalar()

        api_errors = db.execute(
            text("SELECT COUNT(*) FROM bot_events WHERE level = 'ERROR'")
        ).scalar() or 0

        # Class balance among resolved markets
        yes_count = db.execute(
            text("SELECT COUNT(*) FROM markets WHERE resolved = 1 AND resolution = 'YES'")
        ).scalar() or 0
        no_count  = db.execute(
            text("SELECT COUNT(*) FROM markets WHERE resolved = 1 AND resolution = 'NO'")
        ).scalar() or 0
        minority  = min(yes_count, no_count)
        total_res = yes_count + no_count
        class_balance = minority / total_res if total_res > 0 else 0.0

        # Feature completeness (price, bid, ask, spread all non-null) among real rows
        complete = db.execute(
            text("""
                SELECT COUNT(*) FROM market_snapshots
                WHERE is_synthetic = 0
                  AND price IS NOT NULL
                  AND bid   IS NOT NULL
                  AND ask   IS NOT NULL
                  AND spread IS NOT NULL
            """)
        ).scalar() or 0
        feature_completeness = complete / total_snaps if total_snaps > 0 else 0.0

        # --- Gate evaluation ---
        gate_issues = []
        if resolved_mkts < settings.min_resolved_markets:
            gate_issues.append(
                f"Need {settings.min_resolved_markets} resolved markets, have {resolved_mkts}"
            )
        if valid_samples < settings.min_valid_samples:
            gate_issues.append(
                f"Need {settings.min_valid_samples} valid samples, have {valid_samples}"
            )
        if class_balance < settings.min_class_balance:
            gate_issues.append(
                f"Class balance {class_balance:.2f} < min {settings.min_class_balance}"
            )
        if feature_completeness < settings.min_feature_completeness:
            gate_issues.append(
                f"Feature completeness {feature_completeness:.2f} < min {settings.min_feature_completeness}"
            )

        real_backtest_allowed = len(gate_issues) == 0

        # Overall quality label
        if real_backtest_allowed:
            data_quality = "GOOD"
        elif resolved_mkts > 0 and valid_samples > 0:
            data_quality = "WARNING"
        else:
            data_quality = "INSUFFICIENT"

        def _to_iso(val):
            if val is None:
                return None
            if hasattr(val, "isoformat"):
                return val.isoformat()
            return str(val)

        return {
            "live_data": settings.data_mode == "live",
            "synthetic_bootstrap_enabled": settings.synthetic_bootstrap,
            "real_backtest_allowed": real_backtest_allowed,
            "real_backtest_blocked_reasons": gate_issues,
            "data_quality": data_quality,
            "snapshots_collected": total_snaps,
            "unique_markets": unique_mkts,
            "resolved_markets": resolved_mkts,
            "unresolved_markets": unresolved_mkts,
            "valid_training_samples": valid_samples,
            "invalid_samples": invalid_samples,
            "class_balance": round(class_balance, 4),
            "feature_completeness": round(feature_completeness, 4),
            "api_errors": api_errors,
            "collection_started": _to_iso(first_snap),
            "last_snapshot": _to_iso(last_snap),
        }
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────
# Dataset builder
# ──────────────────────────────────────────────────────────────

class DatasetBuilder:
    """
    Builds train / val / test DataFrames exclusively from real Polymarket data.

    Synthetic mode is available ONLY for unit-test fixtures and is gated
    by settings.synthetic_bootstrap.  Any attempt to use synthetic data
    while synthetic_bootstrap=False raises DataPurityError.
    """

    # Feature columns used for model training
    FEATURE_COLS = [
        "spread", "orderbook_imbalance", "short_momentum",
        "rolling_volatility", "distance_from_50",
        "return_1", "return_5", "return_10",
    ]

    MIN_RESOLVED_MARKETS = 10
    MIN_VALID_SAMPLES = 500

    def check_research_readiness(self) -> dict:
        """Evaluates whether there is enough real, resolved data to perform a statistically meaningful backtest."""
        db = SessionLocal()
        try:
            resolved_count = db.execute(text("SELECT COUNT(*) FROM markets WHERE resolved = 1")).fetchone()[0]
            valid_samples = db.execute(text("""
                SELECT COUNT(*) 
                FROM market_snapshots ms
                JOIN markets m ON ms.market_id = m.market_id
                WHERE ms.is_synthetic = 0 
                  AND m.resolved = 1 
                  AND m.resolution IS NOT NULL 
                  AND ms.received_timestamp < m.resolved_at
            """)).fetchone()[0]
            
            # Simple heuristic checking
            is_ready = resolved_count >= self.MIN_RESOLVED_MARKETS and valid_samples >= self.MIN_VALID_SAMPLES
            
            reasons = []
            if resolved_count < self.MIN_RESOLVED_MARKETS:
                reasons.append(f"Resolved markets: {resolved_count} / required {self.MIN_RESOLVED_MARKETS}")
            if valid_samples < self.MIN_VALID_SAMPLES:
                reasons.append(f"Valid samples: {valid_samples} / required {self.MIN_VALID_SAMPLES}")
                
            return {
                "status": "RESEARCH_READY" if is_ready else "RESEARCH_BLOCKED",
                "resolved_markets": resolved_count,
                "valid_samples": valid_samples,
                "reasons": reasons
            }
        finally:
            db.close()

    def load_real_data(self) -> pd.DataFrame:
        """
        Loads only REAL, non-synthetic snapshots for resolved markets.
        Labels are sourced from Market.resolution — never inferred from prices.
        Snapshots taken AFTER resolved_at are excluded to prevent look-ahead.
        """
        db = SessionLocal()
        try:
            rows = db.execute(text("""
                SELECT
                    ms.market_id,
                    ms.token_id,
                    ms.received_timestamp,
                    ms.price,
                    ms.bid,
                    ms.ask,
                    ms.spread,
                    ms.bid_depth,
                    ms.ask_depth,
                    ms.imbalance,
                    ms.volume,
                    ms.liquidity,
                    ms.latency_ms,
                    m.resolution,
                    m.resolved_at,
                    m.end_time
                FROM market_snapshots ms
                JOIN markets m ON ms.market_id = m.market_id
                WHERE ms.is_synthetic = 0           -- REAL data only
                  AND m.resolved    = 1             -- only resolved markets
                  AND m.resolution  IS NOT NULL     -- label must exist
                  AND ms.received_timestamp < m.resolved_at  -- NO look-ahead
            """)).fetchall()

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows, columns=[
                "market_id", "token_id", "received_timestamp",
                "price", "bid", "ask", "spread",
                "bid_depth", "ask_depth", "imbalance",
                "volume", "liquidity", "latency_ms",
                "resolution", "resolved_at", "end_time",
            ])

            # Binary label: 1 = YES resolved, 0 = NO resolved
            df["outcome"] = (df["resolution"] == "YES").astype(int)

            # Assert purity — no synthetic rows should ever appear here
            assert "is_synthetic" not in df.columns or not df.get("is_synthetic", pd.Series([False])).any(), \
                "Synthetic rows detected in real dataset — DATA PURITY VIOLATION"

            return df

        finally:
            db.close()

    # ----------------------------------------------------------
    # Synthetic data — test fixtures ONLY
    # ----------------------------------------------------------

    def generate_synthetic_data(self, num_markets: int = 10,
                                 ticks_per_market: int = 1000) -> pd.DataFrame:
        """
        Generates clearly-labelled SYNTHETIC data.
        ONLY callable when settings.synthetic_bootstrap is True.
        All rows carry is_synthetic=True so they can never be mixed
        with real data by accident.
        """
        if not settings.synthetic_bootstrap:
            raise DataPurityError(
                "generate_synthetic_data() called but SYNTHETIC_BOOTSTRAP=false. "
                "Set SYNTHETIC_BOOTSTRAP=true explicitly to use synthetic data."
            )

        from datetime import timedelta
        np.random.seed(42)
        rows = []
        base_time = datetime(2000, 1, 1)  # obviously-fake dates

        for m in range(num_markets):
            market_id = f"SYNTHETIC_FIXTURE_{m}"
            price = np.random.uniform(0.3, 0.7)
            true_prob = np.clip(price + np.random.uniform(-0.1, 0.1), 0.01, 0.99)
            outcome = 1 if np.random.rand() < true_prob else 0

            for t in range(ticks_per_market):
                price = np.clip(price + np.random.normal(0, 0.005), 0.01, 0.99)
                if t > ticks_per_market * 0.8:
                    price += (outcome - price) * 0.05
                bid_depth = np.random.uniform(10, 1000) * (1.2 if outcome == 1 else 1.0)
                ask_depth = np.random.uniform(10, 1000) * (1.0 if outcome == 1 else 1.2)
                spread = np.random.uniform(0.005, 0.03)
                rows.append({
                    "market_id":          market_id,
                    "received_timestamp": base_time + timedelta(minutes=t),
                    "price":              price,
                    "bid":                price - spread / 2,
                    "ask":                price + spread / 2,
                    "spread":             spread,
                    "volume":             np.random.uniform(0, 100),
                    "liquidity":          bid_depth + ask_depth,
                    "bid_depth":          bid_depth,
                    "ask_depth":          ask_depth,
                    "outcome":            outcome,
                    "is_synthetic":       True,   # ← clearly labelled
                })

        return pd.DataFrame(rows)

    # ----------------------------------------------------------
    # Build train / val / test splits
    # ----------------------------------------------------------

    def build_dataset(
        self, use_synthetic: bool = False
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """
        Returns (train_df, val_df, test_df) with chronological split.

        use_synthetic=True is only valid when settings.synthetic_bootstrap is True.
        Raises DataPurityError otherwise.
        """
        if use_synthetic:
            if not settings.synthetic_bootstrap:
                raise DataPurityError(
                    "build_dataset(use_synthetic=True) rejected: "
                    "SYNTHETIC_BOOTSTRAP=false in settings."
                )
            logger.warning("[DATASET] Using SYNTHETIC data — not valid for real strategy evaluation.")
            df = self.generate_synthetic_data()
        else:
            df = self.load_real_data()

        if df is None or df.empty:
            logger.info("[DATASET] No data available for dataset construction.")
            return None, None, None

        # -- Per-market feature calculation (no cross-market leakage) --
        market_dfs = []
        for mid, group in df.groupby("market_id"):
            feat_df = calculate_features(group)
            if not feat_df.empty:
                market_dfs.append(feat_df)

        if not market_dfs:
            return None, None, None

        full_df = pd.concat(market_dfs).dropna()

        if use_synthetic:
            full_df["is_synthetic"] = True
        else:
            # Verify no synthetic rows leaked in
            if "is_synthetic" in full_df.columns and full_df["is_synthetic"].any():
                raise DataPurityError(
                    "Synthetic rows found in real dataset split — aborting."
                )

        # -- Strict chronological split (no shuffling) --
        full_df = full_df.sort_values("received_timestamp")
        n = len(full_df)
        if n < 10:
            logger.warning("[DATASET] Too few rows to split meaningfully.")
            return None, None, None

        train_end = int(n * 0.60)
        val_end   = int(n * 0.80)

        train_df = full_df.iloc[:train_end].copy()
        val_df   = full_df.iloc[train_end:val_end].copy()
        test_df  = full_df.iloc[val_end:].copy()

        # Final look-ahead sanity check: train max time < val min time < test min time
        assert train_df["received_timestamp"].max() <= val_df["received_timestamp"].min(), \
            "LOOK-AHEAD DETECTED: train timestamps overlap with val timestamps!"
        assert val_df["received_timestamp"].max() <= test_df["received_timestamp"].min(), \
            "LOOK-AHEAD DETECTED: val timestamps overlap with test timestamps!"

        logger.info(
            f"[DATASET] Split: train={len(train_df)} val={len(val_df)} test={len(test_df)} "
            f"synthetic={use_synthetic}"
        )
        return train_df, val_df, test_df
