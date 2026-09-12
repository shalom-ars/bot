import pandas as pd
import numpy as np

def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates Polymarket-only features from a DataFrame of MarketSnapshots.
    Expects columns: ['received_timestamp', 'price', 'bid', 'ask', 'spread', 'volume', 'liquidity', 'bid_depth', 'ask_depth']
    """
    if df.empty or len(df) < 60:
        return pd.DataFrame()
        
    df = df.sort_values('received_timestamp').copy()
    
    # Fill NAs
    df['bid_depth'] = df['bid_depth'].fillna(0)
    df['ask_depth'] = df['ask_depth'].fillna(0)
    
    # PRICE RETURNS
    for lag in [1, 3, 5, 10, 30, 60]:
        df[f'return_{lag}'] = df['price'].pct_change(periods=lag).fillna(0)
        
    # MOMENTUM
    df['short_momentum'] = df['price'] - df['price'].shift(5).fillna(df['price'])
    df['medium_momentum'] = df['price'] - df['price'].shift(30).fillna(df['price'])
    df['momentum_acceleration'] = df['short_momentum'] - df['short_momentum'].shift(5).fillna(0)
    
    # VOLATILITY
    df['rolling_volatility'] = df['price'].rolling(window=30, min_periods=1).std().fillna(0)
    df['short_volatility'] = df['price'].rolling(window=10, min_periods=1).std().fillna(0)
    df['volatility_change'] = df['short_volatility'] - df['rolling_volatility']
    
    # ORDER BOOK
    df['orderbook_imbalance'] = (df['bid_depth'] - df['ask_depth']) / (df['bid_depth'] + df['ask_depth'] + 1e-9)
    df['relative_spread'] = df['spread'] / (df['price'] + 1e-9)
    df['depth_ratio'] = df['bid_depth'] / (df['ask_depth'] + 1e-9)
    
    # ACTIVITY
    df['volume_change'] = df['volume'].diff().fillna(0) if 'volume' in df.columns else 0.0
    
    # MARKET
    df['distance_from_50'] = df['price'] - 0.5
    
    # Time remaining - we'd need end_time joined to this df, but we'll simulate or calculate later.
    
    df = df.fillna(0)
    return df
