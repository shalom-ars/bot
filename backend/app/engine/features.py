import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class FeatureEngine:
    def __init__(self):
        self.history = {} # symbol -> list of dicts

    def add_tick(self, symbol, data: dict):
        if symbol not in self.history:
            self.history[symbol] = []
        data['timestamp'] = datetime.utcnow()
        self.history[symbol].append(data)
        
        # Keep only last 2000 ticks for multi-timeframe
        if len(self.history[symbol]) > 2000:
            self.history[symbol] = self.history[symbol][-2000:]

    def get_features(self, symbol, time_remaining_sec):
        if symbol not in self.history or len(self.history[symbol]) < 2:
            return None
        
        df = pd.DataFrame(self.history[symbol])
        df.set_index('timestamp', inplace=True)
        
        current = df.iloc[-1]
        hist_len = len(df)
        
        # Safe momentum calculations (1m, 5m, 15m)
        def get_return(seconds):
            cutoff = df.index[-1] - pd.Timedelta(seconds=seconds)
            past_data = df.loc[:cutoff]
            if not past_data.empty:
                past_price = past_data.iloc[-1]['price']
                if past_price > 0:
                    return (current['price'] / past_price) - 1.0
            return 0.0

        r_60s = get_return(60)
        r_300s = get_return(300)
        r_900s = get_return(900)

        # Volatility
        vol = df['price'].pct_change().std() * np.sqrt(hist_len) if hist_len > 10 else 0.0
        if np.isnan(vol):
            vol = 0.0
            
        # Orderbook
        bid_depth = current.get('bid_depth', 0.0) or 0.0
        ask_depth = current.get('ask_depth', 0.0) or 0.0
        total_depth = bid_depth + ask_depth
        imbalance = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0.0
        
        return {
            "symbol": symbol,
            "poly_price": float(current['price']),
            "spread": float(current.get('spread', 0.0) or 0.0),
            "imbalance": float(imbalance),
            "depth": float(total_depth),
            "short_momentum_1m": float(r_60s),
            "momentum_5m": float(r_300s),
            "momentum_15m": float(r_900s),
            "rolling_volatility": float(vol),
            "distance_from_50": float(current['price'] - 0.5),
            "time_remaining_sec": time_remaining_sec,
            "history_length": hist_len
        }
