import pandas as pd
import numpy as np
from app.research.features import calculate_features

def test_calculate_features():
    # Create dummy data
    rows = []
    price = 0.5
    for i in range(100):
        rows.append({
            'received_timestamp': pd.Timestamp('2023-01-01') + pd.Timedelta(seconds=i),
            'price': price,
            'bid': price - 0.01,
            'ask': price + 0.01,
            'spread': 0.02,
            'volume': 100,
            'liquidity': 500,
            'bid_depth': 250,
            'ask_depth': 250
        })
        price += 0.001
        
    df = pd.DataFrame(rows)
    features = calculate_features(df)
    
    assert not features.empty
    assert 'return_1' in features.columns
    assert 'short_momentum' in features.columns
    assert 'orderbook_imbalance' in features.columns
    
    # Check that short momentum works (lag 5)
    # price increases by 0.001 each step, so lag 5 is 0.005
    last_momentum = features.iloc[-1]['short_momentum']
    assert np.isclose(last_momentum, 0.005)
