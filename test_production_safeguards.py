import unittest
import sys
import os
import sqlite3

class TestProductionSafeguards(unittest.TestCase):
    def test_live_trading_hard_blocked(self):
        # 1. LIVE TRADING ENABLED = FALSE checks
        with open("backend/app/config.py", "r") as f:
            content = f.read()
            self.assertIn('execution_mode: str = "paper"', content)
            self.assertIn('live_trading_enabled: bool = False', content)
            self.assertIn('live_trading_kill_switch: bool = True', content)
        
    def test_startup_lock_enforced(self):
        # Test that main.py startup event has the hard block
        with open("backend/app/main.py", "r") as f:
            content = f.read()
            self.assertIn('if settings.live_trading_enabled or settings.execution_mode == "live":', content)
            self.assertIn('raise RuntimeError("REAL TRADING IS DISABLED IN THIS BUILD. Phase 7 hard-block active.")', content)

    def test_mock_connector_uses_correct_source(self):
        # Mock connector must use "POLYMARKET" so it is not dropped by snapshot_validator
        with open("backend/app/connectors/mock_data.py", "r") as f:
            content = f.read()
            self.assertIn('source="POLYMARKET"', content)
            self.assertNotIn('source="POLYMARKET_MOCK"', content)

    def test_buy_no_math_correction(self):
        # P1-006 fix check
        with open("backend/app/trading/paper_engine.py", "r") as f:
            content = f.read()
            # Ensure unrealized PnL uses no_token_price = 1.0 - current_price
            self.assertIn('no_token_price = 1.0 - current_price', content)
            self.assertIn('pos.unrealized_pnl = (no_token_price - pos.entry_price)', content)

    def test_exposure_updates_on_trade(self):
        # P0-001 fix check
        with open("backend/app/trading/paper_engine.py", "r") as f:
            content = f.read()
            self.assertIn('self.risk.current_exposure += size', content)
            self.assertIn('self.risk.open_positions_count += 1', content)
            
            # Decrement on resolution
            self.assertIn('self.risk.current_exposure = max(0.0, self.risk.current_exposure - position_cost)', content)

    def test_condition_id_mapped_correctly(self):
        # P0-002 fix check
        with open("backend/app/engine/scanner.py", "r") as f:
            content = f.read()
            self.assertIn('real_condition_id = market.condition_id if market and market.condition_id else tick.market_id', content)
            self.assertIn('"condition_id": real_condition_id,', content)

    def test_jwt_secret_not_hardcoded(self):
        # P0-003 fix check
        with open("backend/app/api/security.py", "r") as f:
            content = f.read()
            self.assertIn('raise RuntimeError(', content)
            self.assertIn('FATAL: SAAS_SECRET_KEY environment variable is not set.', content)

    def test_phase6_net_pnl_corrected(self):
        # P1-001 fix check
        with open("backend/app/engine/paper_controller.py", "r") as f:
            content = f.read()
            self.assertIn('session.net_pnl = self.risk.current_balance - session.initial_balance', content)
            self.assertNotIn('session.net_pnl = self.risk.daily_pnl', content)

if __name__ == "__main__":
    unittest.main()
