import numpy as np

def brier_score(y_true, y_prob):
    """
    Calculates Brier Score. 
    Lower is better (0 to 1).
    """
    if len(y_true) == 0: return 0.0
    return np.mean((y_prob - y_true) ** 2)

def log_loss_score(y_true, y_prob):
    """
    Calculates Log Loss (Cross Entropy).
    """
    if len(y_true) == 0: return 0.0
    y_prob = np.clip(y_prob, 1e-15, 1 - 1e-15)
    return -np.mean(y_true * np.log(y_prob) + (1 - y_true) * np.log(1 - y_prob))

def calculate_drawdown(pnl_series):
    """
    Calculates max drawdown from a series of cumulative PnLs.
    """
    if len(pnl_series) == 0: return 0.0
    peak = np.maximum.accumulate(pnl_series)
    drawdown = (peak - pnl_series) / np.maximum(peak, 1e-9)
    return np.max(drawdown)

def calculate_profit_factor(trades):
    gross_profit = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0)
    gross_loss = abs(sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) < 0))
    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0
    return gross_profit / gross_loss
