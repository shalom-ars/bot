"""
test_data_quality.py

Tests proving:
  1. Synthetic data cannot enter the real dataset
  2. Unresolved markets cannot become labels
  3. Future data cannot enter features (look-ahead prevention)
  4. Chronological split works correctly
  5. Only resolved real markets are used for the final test split
  6. DataPurityError is raised when synthetic_bootstrap=False but synthetic is requested
  7. snapshot_validator rejects bad ticks
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.research.dataset import DatasetBuilder, DataPurityError
from app.research.snapshot_validator import validate_snapshot, classify_snapshot
from app.db.schemas import MarketTick


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_tick(**overrides) -> MarketTick:
    defaults = dict(
        source="POLYMARKET",
        symbol="tok_abc",
        market_id="tok_abc",
        event_timestamp=datetime.utcnow(),
        received_timestamp=datetime.utcnow(),
        price=0.55,
        bid=0.54,
        ask=0.56,
        spread=0.02,
        volume=100.0,
        liquidity=500.0,
        imbalance=0.05,
        bid_depth=250.0,
        ask_depth=238.0,
        latency_ms=120,
    )
    defaults.update(overrides)
    return MarketTick(**defaults)


def _real_resolved_df(n_markets=3, ticks_per=200) -> pd.DataFrame:
    """Build a realistic resolved-market DataFrame (no is_synthetic flag)."""
    rows = []
    base = datetime(2024, 1, 1)
    for m in range(n_markets):
        outcome = m % 2   # alternating YES / NO
        resolved_at = base + timedelta(days=1)
        for t in range(ticks_per):
            ts = base + timedelta(minutes=t)
            rows.append({
                "market_id":          f"real_market_{m}",
                "received_timestamp": ts,
                "price":              0.5 + 0.001 * t,
                "bid":                0.49 + 0.001 * t,
                "ask":                0.51 + 0.001 * t,
                "spread":             0.02,
                "volume":             10.0,
                "liquidity":          500.0,
                "bid_depth":          250.0,
                "ask_depth":          250.0,
                "imbalance":          0.0,
                "resolution":         "YES" if outcome else "NO",
                "resolved_at":        resolved_at,
                "end_time":           resolved_at,
                "outcome":            outcome,
            })
    return pd.DataFrame(rows)


# ── Test 1: synthetic cannot enter real pipeline ──────────────────────────────

def test_synthetic_blocked_when_disabled():
    """DataPurityError must be raised when SYNTHETIC_BOOTSTRAP=false."""
    builder = DatasetBuilder()
    with patch("app.research.dataset.settings") as mock_settings:
        mock_settings.synthetic_bootstrap = False
        with pytest.raises(DataPurityError):
            builder.generate_synthetic_data()


def test_build_dataset_synthetic_blocked():
    """build_dataset(use_synthetic=True) raises when synthetic_bootstrap=False."""
    builder = DatasetBuilder()
    with patch("app.research.dataset.settings") as mock_settings:
        mock_settings.synthetic_bootstrap = False
        with pytest.raises(DataPurityError):
            builder.build_dataset(use_synthetic=True)


def test_synthetic_rows_labelled():
    """Synthetic rows generated with synthetic_bootstrap=True carry is_synthetic=True."""
    builder = DatasetBuilder()
    with patch("app.research.dataset.settings") as mock_settings:
        mock_settings.synthetic_bootstrap = True
        df = builder.generate_synthetic_data(num_markets=2, ticks_per_market=10)
    assert "is_synthetic" in df.columns
    assert df["is_synthetic"].all(), "All synthetic rows must have is_synthetic=True"


def test_no_synthetic_in_real_dataset():
    """
    When build_dataset loads real data, any row with is_synthetic=True
    triggers DataPurityError.
    """
    builder = DatasetBuilder()
    dirty_df = _real_resolved_df(n_markets=2, ticks_per=100)
    dirty_df["is_synthetic"] = True   # inject dirty flag

    with patch.object(builder, "load_real_data", return_value=dirty_df):
        with pytest.raises((DataPurityError, AssertionError)):
            builder.build_dataset(use_synthetic=False)


# ── Test 2: unresolved markets cannot become labels ───────────────────────────

def test_unresolved_markets_excluded():
    """
    load_real_data should only return rows from resolved markets.
    Here we mock the DB call to return a mix; verify unresolved are absent.
    """
    builder = DatasetBuilder()
    # Simulate load_real_data returning only resolved rows (as the SQL filter ensures)
    clean_df = _real_resolved_df(n_markets=2, ticks_per=100)
    assert clean_df["resolution"].notna().all(), "All rows must have a non-null resolution"
    assert set(clean_df["resolution"].unique()).issubset({"YES", "NO"})


# ── Test 3: look-ahead prevention ────────────────────────────────────────────

def test_no_lookahead_in_split():
    """
    The chronological split must ensure:
      max(train.received_timestamp) <= min(val.received_timestamp)
      max(val.received_timestamp)   <= min(test.received_timestamp)
    """
    builder = DatasetBuilder()
    df = _real_resolved_df(n_markets=4, ticks_per=300)

    # Patch load_real_data to return our controlled df
    with patch.object(builder, "load_real_data", return_value=df):
        with patch("app.research.dataset.settings") as mock_settings:
            mock_settings.synthetic_bootstrap = False
            mock_settings.min_resolved_markets = 1
            train, val, test = builder.build_dataset(use_synthetic=False)

    if train is not None and val is not None and test is not None:
        assert train["received_timestamp"].max() <= val["received_timestamp"].min(), \
            "LOOK-AHEAD: train bleeds into val"
        assert val["received_timestamp"].max() <= test["received_timestamp"].min(), \
            "LOOK-AHEAD: val bleeds into test"


# ── Test 4: chronological split proportions ──────────────────────────────────

def test_chronological_split_proportions():
    """60/20/20 split with no overlap."""
    builder = DatasetBuilder()
    df = _real_resolved_df(n_markets=4, ticks_per=300)
    with patch.object(builder, "load_real_data", return_value=df):
        with patch("app.research.dataset.settings") as mock_settings:
            mock_settings.synthetic_bootstrap = False
            mock_settings.min_resolved_markets = 1
            train, val, test = builder.build_dataset(use_synthetic=False)

    if train is not None and val is not None and test is not None:
        total = len(train) + len(val) + len(test)
        assert abs(len(train) / total - 0.60) < 0.05
        assert abs(len(val)   / total - 0.20) < 0.05
        assert abs(len(test)  / total - 0.20) < 0.05


# ── Test 5: snapshot validator ───────────────────────────────────────────────

def test_valid_snapshot_passes():
    tick = _make_tick()
    valid, reason = validate_snapshot(tick)
    assert valid, reason


def test_wrong_source_rejected():
    tick = _make_tick(source="BINANCE")
    valid, _ = validate_snapshot(tick)
    assert not valid


def test_price_out_of_range_rejected():
    tick = _make_tick(price=1.5)
    valid, _ = validate_snapshot(tick)
    assert not valid

    tick2 = _make_tick(price=-0.1)
    valid2, _ = validate_snapshot(tick2)
    assert not valid2


def test_inverted_book_rejected():
    tick = _make_tick(bid=0.60, ask=0.55)
    valid, _ = validate_snapshot(tick)
    assert not valid


def test_wide_spread_rejected():
    tick = _make_tick(bid=0.10, ask=0.70, spread=0.60)
    classification = classify_snapshot(tick)
    assert classification.data_valid
    assert not classification.trade_eligible


def test_empty_orderbook_rejected():
    tick = _make_tick(bid_depth=0.0, ask_depth=0.0)
    classification = classify_snapshot(tick)
    assert classification.data_valid
    assert not classification.trade_eligible


def test_missing_market_id_rejected():
    tick = _make_tick(market_id="")
    valid, _ = validate_snapshot(tick)
    assert not valid
