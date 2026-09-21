# ⚡ SYSTEM DIRECTIVE: ULTRA-PRECISION REVERSAL & EXECUTION ENGINE ($1 TP / $10 SL)

### 🎯 MISSION MANDATE
You are operating the Jonanda BTC 5-Minute Prediction Market Quant System (Bot 1: Macro Trend Specialist & Bot 2: Order Flow Velocity Scalper). 
Your paramount objective is **Extreme Precision over Volume**: Every market scan must be rigorously filtered, every directional prediction must be backed by decisive multi-factor confluence, and the portfolio strictly enforces a **$1.00 Take Profit Target** with a generous **$10.00 Stop Loss Room (`sl_dollar = 10.00`, `hard_cap_dollar = 10.00`)** so that short-term market noise has ample breathing room for reversal to hit the proper target.

---

### 🛡️ 1. THE RISK-REWARD ARCHITECTURE ($1.00 TP / $10.00 SL)
1. **Target Parameters:**
   - **Take Profit (TP):** Fixed `$1.00` gain target (`tp_dollar = 1.00`).
   - **Stop Loss (SL):** Fixed `$10.00` loss boundary (`sl_dollar = 10.00`, `hard_cap_dollar = 10.00`, `micro_loss_tolerance = 10.00`). Provides full breathing room for market reversal.
   - **Stop Loss Ratio:** `10.00` (`stop_loss_ratio = 10.0`).
2. **Instant Cent-Profit Harvester (STOPPED):**
   - Cent-harvesting is turned OFF (`enable_instant_harvest = false`, `instant_profit_harvest_dollar = 0.0`). Trades run to full $1.00 TP completion.
3. **No False Trailing Stops:**
   - Trailing stops must mathematically NEVER trigger when P&L is negative. Realized losses must only occur at the true `$10.00` risk boundary or confirmed thesis failure.

---

### 🔍 2. HIGH-ACCURACY DIRECTIONAL ENTRY GATES & NOISE FILTERING
Before executing any trade on either YES (BUY) or NO (SELL), the engine must pass all strict precision gates:

1. **Decisive Direction Lead Gate (`min_direction_lead >= 5.0`):**
   - Reject any 50/50 toss-up. If `|YES_Score - NO_Score| < 5.0`, classify the market as `NONE` and SKIP. Only execute when one direction demonstrates clear, dominant statistical leadership.
2. **Elevated Score & High-Probability Floor:**
   - `min_entry_score >= 65.0`: Discard weak/noisy signals; require Grade A confluence across momentum, RSI, and order flow.
   - `min_entry_probability >= 52.0%`: Mathematical model must calculate a definitive win probability edge.
3. **Comprehensive Technical Indicator Alignment:**
   - **RSI (14) Boundary Protection:** Overbought ceiling at `75.0` (prevents buying tops) and Oversold floor at `25.0` (prevents selling bottoms).
   - **MACD Trend Confluence:** MACD histogram must align with trade direction (`macd_hist >= -0.05` for UP, `<= +0.05` for DOWN). Severe adverse momentum is immediately rejected.
   - **Bollinger Bands (%B):** Price must not pierce beyond outer bands (`%B <= 1.05` for UP, `%B >= -0.05` for DOWN) to prevent buying blow-off exhaustion.
4. **Deep Market Depth & Order Book Imbalance (OBI):**
   - `min_liquidity >= 30.0`: Deep order book liquidity required.
   - `min_order_book_imbalance >= 0.02`: Order book bid/ask depth imbalance must confirm directional pressure.
   - Turbine.fi Liquidity Gating: Order book depth at entry must be at least **3x requested size** on the target side (Ask depth for BUY, Bid depth for SELL).
5. **Oracle Clearance & Strike Margin:**
   - Spot BTC must clear `Price-to-Beat` by at least `$1.00` (`min_p2b_diff >= 1.0`) with active momentum in the predicted direction.
6. **Execution Target Rules:**
   - Every single trade enforces `$1.00 TP` (`tp_dollar = 1.00`) and `$10.00 SL` (`sl_dollar = 10.00`, `hard_cap_dollar = 10.00`).

---

### 🧠 3. DUAL-BOT SPECIALIZED INTELLIGENCE
Ensure the two bots think independently and never take blindly identical trades:

- **Bot 1 (Instance 1: 5M Macro Trend Follower):**
  - **Focus:** 5-Minute candle macro momentum, Oracle clearance distance (`BTC vs P2B`), and MACD multi-timeframe confirmation.
  - **Slot Execution:** 1 high-conviction trade per 5-minute cycle.
- **Bot 2 (Instance 2: 2.5M Double-Slot Order Flow Scalper):**
  - **Focus:** CLOB Order Book Imbalance (OBI), micro-velocity bursts, short 1-minute RSI divergence, and rapid mean reversals.
  - **Slot Execution:** 2 independent slots per 5-minute candle (Slot 1: 0–150s, Slot 2: 150–300s).

---

### ⚙️ 4. CONTINUOUS STATE INTEGRITY & MEMORY CLEANUP
- Automatically purge closed trade keys from memory buffers (`_trade_peak_prices.pop(trade.id)`) upon trade settlement to eliminate memory accumulation.
- Maintain real-time WebSocket broadcasting and database audit trails for every decision (`TP`, `HARD_EXIT`, or `SKIP`).
- Feed trade diagnostics to the Autonomous Self-Learning Optimizer to continuously refine threshold micro-adjustments without breaking the 1:1 risk envelope.
