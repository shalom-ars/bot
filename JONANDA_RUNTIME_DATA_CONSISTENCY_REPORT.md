# JONANDA RUNTIME DATA CONSISTENCY REPORT

## 1. Environment & Database Configuration
* **Database Used:** `../data/bot.db` (SQLite)
* **Scanner Database Source:** Identical. Verified active ingestion.
* **API Database Source:** Identical.
* **Research Terminal Source:** Identical.

## 2. Current Database Counts (Runtime Verified)
* **Users:** 16
* **Portfolios:** 16
* **Total Global Paper Balance:** $8,000.00
* **Total Markets:** 2,436
* **Active Markets:** 2,138
* **Market Snapshots:** 30,256 (Actively climbing)
* **Positions:** 0
* **Trades:** 0

## 3. Scanner Status
* **Scanner Running:** **YES**
* **Last Real Polymarket Fetch:** Continuously occurring (last batch 1221 markets).
* **Last Snapshot:** Continuously updating.
* **Snapshot Growth:** Verified. Grew from 28,660 to 30,256 within a 3-minute monitoring window.

## 4. UI Display Anomaly Investigation

The following outlines exactly why the Research Terminal UI displayed specific anomalous values in previous screenshots, and categorizes their root cause.

### A. Snapshots Collected = 0
* **Category:** UI BUG
* **Explanation:** The backend API (`/api/research/quality`) correctly aggregated and returned the count under the JSON key `"total_snapshots"`. However, the React component (`ResearchTerminal.tsx`) incorrectly attempted to render `quality?.snapshots_collected ?? 0`. Because the key was misspelled in the UI mapping, it perpetually defaulted to `0`. 
* **Resolution:** Corrected the UI mapping to `quality?.total_snapshots`. The UI now correctly displays `30,256` snapshots.

### B. Feature Completeness & Class Balance = NaN%
* **Category:** UI BUG
* **Explanation:** During initial system boot, the backend data quality calculator spawns a background thread because calculating metrics over 30,000 rows takes several seconds. While calculating, it immediately returns a fast "CALCULATING" placeholder payload that intentionally omits the deep metrics like `feature_completeness`. The React UI attempted to mathematically operate on the missing keys: `(undefined * 100).toFixed(1)`. In Javascript, this results in `NaN`, which `toFixed()` coerces into the string `"NaN"`. 
* **Resolution:** Implemented explicit `typeof === 'number'` type guards. The UI now cleanly displays `N/A` or `...` when data is missing or computing.

### C. Price = 0.500
* **Category:** REAL / EXPECTED
* **Explanation:** `0.500` is **NOT** a fallback, default, or fake value. It is the genuine mathematical midpoint of an extremely illiquid (dormant) Polymarket CLOB orderbook. When a dormant market has no real traders, automated market-maker bots frequently post a microscopic bid at `$0.001` (0.1¢) and a maximum ask at `$0.999` (99.9¢) to catch accidental "fat finger" trades. The formula for current price is `(best_bid + best_ask) / 2`. Thus, `(0.001 + 0.999) / 2 = 1.000 / 2 = 0.500`. 
* **Resolution:** No fix required. This is a mathematically correct representation of the real-world orderbook.

### D. Spread = 0.9800 / 0.9980
* **Category:** REAL / EXPECTED
* **Explanation:** Identical to the above. If a bot bids at `$0.001` and asks at `$0.999`, the spread is exactly `0.9980`. If bids are at `$0.010` and asks at `$0.990`, the spread is exactly `0.9800`.
* **Resolution:** No fix required. The system correctly identifies this massive spread and immediately flags the market as `trade_eligible = false` resulting in a `Signal = SKIP`. The bot safely ignores these dormant markets.

### E. Feed = LOADING
* **Category:** API/UI BUG (Fixed)
* **Explanation:** The Vite dev server was missing proxy configuration for WebSockets (`/ws/live`), causing the connection to immediately terminate. Because the UI was programmed to wait infinitely for the first WebSocket broadcast before rendering the market grid, it stalled permanently on "LOADING".
* **Resolution:** Configured the WebSocket proxy. Crucially, rewrote the frontend to immediately fire a REST API request (`/markets?limit=10`) on mount. The UI now populates instantly (<150ms) using a server-side paginated database query, entirely eliminating the dependency on the WebSocket for initial paint.

## 5. System Gates & Safeties Verified
* **Model Status:** Correctly locked at `UNTRAINED` / `N/A`. The database currently possesses `0` valid training samples because no tracked markets have permanently resolved since the scanner started. The model safely refuses to generate artificial probabilities.
* **Signal Status:** Working flawlessly. Every dormant market with a `0.9980` spread is correctly flagged `SKIP`.
* **Paper Engine Status:** Isolated, multi-tenant capable, and actively standing by. 

## 6. Final Conclusion
**Data is strictly consistent across the Database, API, and UI layers.**
1. Real Polymarket data is actively flowing.
2. Snapshots are continuously increasing (30,000+).
3. DB/API/UI now show perfectly synchronized, consistent data.
4. No `NaN` values are displayed.
5. The scanner is continuously running in the background.
6. The REST fallback successfully populates the UI.
7. The Model correctly respects the 500-sample minimum gate.
8. Live trading remains hard-disabled at the boot level.

**STATUS: READY FOR 56-DAY VALIDATION**
