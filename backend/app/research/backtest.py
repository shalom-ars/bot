import pandas as pd
import numpy as np
from app.research.metrics import brier_score, log_loss_score, calculate_drawdown, calculate_profit_factor
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class EventDrivenBacktester:
    def __init__(self, model):
        self.model = model
        self.starting_balance = 100.0
        self.risk_pct = 0.01

    def run_backtest(self, test_df: pd.DataFrame):
        balance = self.starting_balance
        trades = []
        equity_curve = [balance]
        
        y_true = []
        y_prob = []
        
        skipped = 0
        
        # Group by market to simulate independent trajectories
        for market_id, group in test_df.groupby('market_id'):
            group = group.sort_values('received_timestamp')
            
            position = None
            
            for _, tick in group.iterrows():
                # Extract features for prediction
                features = [
                    tick.get('spread', 0),
                    tick.get('orderbook_imbalance', 0),
                    tick.get('short_momentum', 0),
                    tick.get('rolling_volatility', 0),
                    tick.get('distance_from_50', 0)
                ]
                
                # Need 2D array for sklearn
                prob_up, uncertainty, model_name = self.model.predict(np.array(features).reshape(1, -1))
                market_prob = tick['price']
                
                y_true.append(tick['outcome'])
                y_prob.append(prob_up)
                
                raw_edge = prob_up - market_prob
                
                # Effective edge approximation
                spread = tick['spread']
                estimated_slippage = spread / 2
                effective_edge = raw_edge - estimated_slippage
                
                # Strategy logic
                if not position:
                    if effective_edge > settings.min_edge:
                        # BUY Signal
                        size_usd = balance * self.risk_pct
                        shares = size_usd / (market_prob + estimated_slippage)
                        
                        position = {
                            'entry_price': market_prob + estimated_slippage,
                            'shares': shares,
                            'cost': size_usd
                        }
                        balance -= size_usd
                    else:
                        skipped += 1
                        
            # Market Resolves
            if position:
                outcome = group.iloc[-1]['outcome']
                if outcome == 1:
                    # Won: shares resolve to $1
                    payout = position['shares'] * 1.0
                else:
                    # Lost: shares resolve to $0
                    payout = 0
                    
                pnl = payout - position['cost']
                balance += payout
                trades.append({
                    'market_id': market_id,
                    'pnl': pnl,
                    'return': pnl / position['cost']
                })
                equity_curve.append(balance)
                
        # Metrics
        win_rate = len([t for t in trades if t['pnl'] > 0]) / len(trades) if trades else 0.0
        net_pnl = balance - self.starting_balance
        max_dd = calculate_drawdown(equity_curve)
        pf = calculate_profit_factor(trades)
        
        brier = brier_score(np.array(y_true), np.array(y_prob))
        logloss = log_loss_score(np.array(y_true), np.array(y_prob))
        
        return {
            "total_trades": len(trades),
            "win_rate": win_rate,
            "net_pnl": net_pnl,
            "max_drawdown": max_dd,
            "profit_factor": pf,
            "brier_score": brier,
            "log_loss": logloss,
            "skipped": skipped
        }
