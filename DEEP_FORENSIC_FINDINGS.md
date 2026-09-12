# DEEP FORENSIC FINDINGS — JONANDA AUDIT #3

**Date:** 2026-09-12  
**Auditor:** Automated adversarial forensic pass  
**Files inspected:** All 37 backend .py files, config, models, connectors, engines, APIs

---

## P0 FINDINGS (Catastrophic)

### P0-001 — `current_exposure` is NEVER incremented after a trade executes
**File:** `app/trading/paper_engine.py`, `app/trading/risk.py`  
**Function:** `PaperEngine.execute_signal()`, `RiskManager.evaluate_trade()`

**Problem:**  
After the RiskManager approves a trade and `PaperEngine` creates a `Position` + `Trade` record in the database, `self.risk.current_exposure` is **never incremented** in memory. The only place exposure is recalculated is inside `_rehydrate_state()`, which is only called at startup.

At runtime, every subsequent `evaluate_trade()` call uses `self.current_exposure = 0.0` (from memory, never updated after trades execute), causing the total-exposure check (`(self.current_exposure + requested_size) > max_allowed_total`) to **always pass**, regardless of how many open positions exist.

This means the system can take unlimited simultaneous positions far exceeding `max_total_exposure=50%`, violating the core Phase 4 risk constraint.

**Impact:** The total exposure limit is completely non-functional during a live session. The system could enter 100 positions consuming $5,000+ of a $500 paper portfolio.

**Reproduction:** Start bot, wait for 2 BUY signals to fire on different markets. Check `current_exposure` via `/api/risk/status` after each trade. It will show 0.0 or the initial rehydrated value, not the sum of open positions.

**Fix Required:**
```python
# In paper_engine.py execute_signal(), after db.commit():
self.risk.current_exposure += size
self.risk.open_positions_count += 1
```
And in `update_positions()` when resolving:
```python
self.risk.current_exposure -= (pos.entry_price * pos.quantity)
self.risk.open_positions_count -= 1
```

**Regression Test:** Execute 10 paper trades. Assert `risk.current_exposure == sum(approved_sizes)`.

---

### P0-002 — `condition_id` in `market_info` passed to RiskManager is always set to `tick.market_id` (token ID), breaking condition-level exposure caps
**File:** `app/engine/scanner.py:257`  
**Code:**
```python
market_info = {
    "condition_id": tick.market_id,  # Simplified mapping — THIS IS WRONG
    ...
}
```

**Problem:**  
`tick.market_id` is the CLOB **token ID** (e.g., YES token). The `condition_id` should be the **parent market's condition ID** (the shared ID that ties YES and NO tokens together). By setting `condition_id = tick.market_id`, the condition-level exposure check in `RiskManager.evaluate_trade()` queries `Position.condition_id == condition_id` — but no position will ever match because positions are stored with the correct `condition_id` from the `Market` table record. The condition-level cap silently never fires.

**Impact:** A user could hold simultaneous BUY YES and BUY NO positions on the same market. The condition exposure limit (`max_condition_exposure = 10%`) is non-functional.

**Fix Required:**
```python
# In scanner.py _sync_handle_tick:
condition_id = market.condition_id if market else tick.market_id
market_info = {
    "condition_id": condition_id,
    ...
}
```

---

### P0-003 — JWT Secret has a hardcoded public fallback value in production code
**File:** `app/api/security.py:13`  
**Code:**
```python
SECRET_KEY = os.environ.get("SAAS_SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
```

**Problem:**  
If `SAAS_SECRET_KEY` is not set in the production `.env`, the application silently falls back to a hardcoded, publicly committed default secret. Any attacker who reads the repository can forge valid JWT tokens for any `user_id`, achieving full account takeover.

**Impact:** COMPLETE AUTHENTICATION BYPASS. Any attacker can forge a JWT for `user_id=1` (admin) and call admin endpoints.

**Fix Required:**  
```python
SECRET_KEY = os.environ.get("SAAS_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SAAS_SECRET_KEY environment variable is not set. Refusing to start.")
```

---

## P1 FINDINGS (Serious Correctness/Reliability)

### P1-001 — `net_pnl` in Phase 6 session stats is `daily_pnl`, not session PnL
**File:** `app/engine/paper_controller.py:68` and `:98`  
**Code:**
```python
session.net_pnl = self.risk.daily_pnl  # Wrong: daily_pnl resets at midnight
```
and
```python
"net_pnl": self.risk.daily_pnl,  # "For now assuming daily pnl is session pnl"
```

**Problem:**  
`self.risk.daily_pnl` is recalculated at every rehydration to only include trades from today's UTC date. It resets to 0 at midnight. The Phase 6 session `net_pnl` and the dashboard `net_pnl` field will **reset to 0 every day**, making it impossible to track session-level P&L across a 4–8 week validation window.

**Fix Required:**  
Compute session PnL as `sum(t.pnl for t in all_closed_trades_in_session)`. The `RiskManager` already holds `current_balance - starting_balance` as the authoritative session PnL.

---

### P1-002 — `PaperEngine.update_positions()` closes only the first open trade for a market
**File:** `app/trading/paper_engine.py:116`  
**Code:**
```python
trade = db.query(Trade).filter(Trade.market_id == market_id, Trade.status == "OPEN").first()
```

**Problem:**  
If a market somehow accumulates more than one OPEN trade (e.g., after a partial restart where the position record was deleted but the trade was not), `.first()` silently closes only one trade. The others remain OPEN forever. The system does not raise an error or log a warning.

**Fix Required:** Use `.all()` and iterate, or enforce a uniqueness constraint that prevents more than one OPEN trade per market.

---

### P1-003 — `Position` table has `unique=True` on `market_id` but `Trade` table does not
**File:** `app/db/models.py:63` vs `:35`  
**Code:**
```python
class Position(Base):
    market_id = Column(String, unique=True)  # Enforced at DB level

class Trade(Base):
    trade_id = Column(String, unique=True, index=True)  # Different key
    market_id = Column(String, index=True)  # NOT unique — multiple trades per market allowed
```

**Problem:**  
The DB prevents duplicate positions (good), but does not prevent multiple OPEN trades on the same market. After a crash-and-restart mid-execution, a second trade could be written for the same market. `update_positions()` only closes one (P1-002).

---

### P1-004 — `mock_data.py` uses crypto-named synthetic markets that bypass `source == "POLYMARKET"` check
**File:** `app/connectors/mock_data.py:14,38`  
**Code:**
```python
"POLY_BTC_UP": 0.5,
"POLY_ETH_UP": 0.5

tick = MarketTick(source="POLYMARKET_MOCK", ...)
```

**Problem:**  
The snapshot validator's first hard-reject checks `tick.source != "POLYMARKET"`. `"POLYMARKET_MOCK"` ≠ `"POLYMARKET"`, so **all mock ticks are rejected immediately** at the validator and nothing proceeds in mock mode. The mock connector is completely broken. However, the condition `settings.data_mode == "mock"` still spins up the mock loop. This is a wasted loop, but also means `data_mode=mock` is silently non-functional. This is a reliability P1, not a safety P0, because live mode is unaffected.

---

### P1-005 — Backtester uses `model_prob = 0.5` fallback for all rows when model is untrained
**File:** `app/research/backtester.py:79`  
**Code:**
```python
"prob": row.get("model_prob", 0.5)  # Mock probability if uncalibrated
```

**Problem:**  
If the model is untrained, the strategy engine returns `"untrained_baseline"` and immediately issues a SKIP. But in `backtester.py`, a dict is passed to `strategy_router.evaluate()` that is **not a `MarketTick` object** — it is a raw dict. The strategy engine's type signature expects `tick: MarketTick`. This will crash at runtime when `tick.source`, `tick.market_id` etc. are accessed as object attributes. The backtest endpoint `/backtest/run` will raise `AttributeError` on any real data.

---

### P1-006 — `unrealized_pnl` for BUY_NO is calculated with wrong sign during MTM updates
**File:** `app/trading/paper_engine.py:135-136`  
**Code:**
```python
elif pos.side == "BUY_NO" or pos.side == "SELL":
    pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
```

**Problem:**  
For a BUY_NO position, if YES price goes UP (bad for NO), `entry_price - current_price` becomes negative (correct). But this formula is checking against the YES token's price, not the NO token's price. Since we buy the NO token (with price `1 - yes_price`), the correct unrealized PnL during MTM is:
`((1 - current_price) - pos.entry_price) * pos.quantity`

The current formula will show the wrong sign/magnitude for unrealized PnL on NO positions during the life of the trade (not at resolution, which was already fixed).

---

## P2 FINDINGS (Moderate)

### P2-001 — CORS is `allow_origins=["*"]` with `allow_credentials=True`
**File:** `app/main.py:21-24`  
**Problem:** Setting both `allow_origins=["*"]` and `allow_credentials=True` is a CORS misconfiguration. Browsers will reject this combination. More importantly, it means any website can make credentialed requests to the backend if this is ever accessible without auth on some endpoints.  
**Fix:** Lock `allow_origins` to the specific frontend domain in production.

### P2-002 — `bare except:` clauses silently swallow JSON parse errors during market discovery
**File:** `app/engine/scanner.py:295,305`  
**Code:**
```python
except:
    tokens = []
    outcomes = []
```
and
```python
except:
    pass
```
**Problem:** JSON parse errors from Gamma API are silently dropped. A malformed API response causes an empty market list, which is logged nowhere. Use `except (json.JSONDecodeError, ValueError) as e: logger.warning(...)`.

### P2-003 — Access token expiry is 7 days with no refresh token mechanism
**File:** `app/api/security.py:15`  
**Code:** `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7`  
**Problem:** 7-day non-refreshable tokens with no revocation mechanism. If a token is stolen, access is guaranteed for 7 days.

### P2-004 — `get_markets`, `get_positions`, `get_trades` endpoints have no authentication
**File:** `app/api/endpoints.py:9,13,17`  
**Problem:** These three endpoints return live market, position, and trade data with no `Depends(get_current_user)`. Any unauthenticated caller can see the system's paper trade history and positions.

### P2-005 — Strategy `_skip_signal` uses hardcoded `model_prob: 0.5` and `fair_probability: 0.5`
**File:** `app/engine/strategy.py:17,23`  
**Problem:** SKIP signals stored in the database have `model_prob=0.5`. Dashboard stats compute average model probabilities over all signals including SKIPs. This pollutes the signal analytics with misleading 50% baseline values, making it look like the model is predicting uncertainty when the model wasn't even invoked.

### P2-006 — `DataCollectionStats` table is never written by any running loop
**File:** `app/db/models.py:337-354`  
**Problem:** The `DataCollectionStats` model exists but no code writes to it. Any dashboard component reading from it will always receive `null` or `0` values.

### P2-007 — Phase 6 `drawdown` is calculated as `(peak - equity) / peak` but equity includes unrealized PnL from exposure
**File:** `app/engine/paper_controller.py:69`  
**Code:**
```python
session.equity = self.risk.current_balance + self.risk.current_exposure
session.drawdown = (self.risk.peak_balance - session.equity) / self.risk.peak_balance
```
**Problem:** `current_exposure` is the amount of capital reserved in open positions, not the current market value. Adding raw exposure to balance for equity calculation double-counts the reserved capital (it was already subtracted from balance when the position was opened — except `current_balance` is never decremented either due to P0-001). This value will be wrong in two compounding directions.

### P2-008 — `admin/users` endpoint returns full `hashed_password` field
**File:** `app/api/admin.py:28`  
**Code:** `return users`  
**Problem:** SQLAlchemy returns the complete User ORM object. If the response serializer includes `hashed_password`, this leaks password hashes to admin users. Even PBKDF2 hashes should not be unnecessarily exposed.

---

## P3 FINDINGS (Minor/Cleanup)

### P3-001 — `mock_data.py` markets named `POLY_BTC_UP`, `POLY_ETH_UP`
These are crypto-price market names. Since SYNTHETIC_BOOTSTRAP=False and mock mode is broken (P1-004), no live data risk. But the naming is confusing and should reference prediction market slugs.

### P3-002 — `max_total_exposure` in `risk.py:156` uses `starting_balance` not `current_balance`
`max_allowed_total = self.starting_balance * self.max_total_exposure`
This fixes the exposure cap to the initial $100 balance regardless of compounding. Should use `current_balance`.

### P3-003 — `live_orders_submitted: 0` hardcoded in `/live/status`
**File:** `app/api/endpoints.py:193`  
Comment says "Placeholder for Phase 7". Should query from `LiveOrder` table.

### P3-004 — `TODO` comment in backtester architecture  
**File:** `app/research/backtester.py:36-41`  
Comment block describes what "would" happen but then proceeds to do it anyway. Comment is misleading.

### P3-005 — `consecutive_losses` resets to 0 on breakeven (pnl == 0.0)
**File:** `app/trading/risk.py:228-229`  
A trade that closes at exactly `pnl=0` is counted as a win and resets the streak. Breakeven trades should not reset a loss streak.

---

## LIVE TRADING LOCK VERIFICATION

**LIVE ORDER PATHS FOUND:** 0 external API calls to Polymarket trading CLOB. No `py-clob-client`, no `create_order`, no `post_order`. The `LiveExecutionEngine` hardcodes `state = "FAILED"` before any real API call could ever be written.

**LIVE ORDER PATHS BLOCKED:** `LiveExecutionEngine.execute_signal()` has 3 hard blocks:
1. `settings.execution_mode == "paper"` → returns BLOCKED immediately
2. `settings.live_trading_kill_switch` → returns BLOCKED
3. `LiveEligibilityGate.check_eligibility()` → requires all 5 conditions to pass

**PAPER ORDER PATH:** `PaperEngine.execute_signal()` → DB only. No network calls.

**STATUS:** HARD BLOCKED ✓

---

## SAFETY STATE VERIFICATION

Verified from `app/config.py`:
- `data_mode: str = "live"` ✓
- `execution_mode: str = "paper"` ✓
- `research_mode: bool = True` ✓
- `synthetic_bootstrap: bool = False` ✓
- `live_trading_enabled: bool = False` ✓
- `live_trading_kill_switch: bool = True` ✓

All defaults are safe. Overridable via `.env` but kill switch defaults True.
