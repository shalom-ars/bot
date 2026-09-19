import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mode: str = "paper"
    starting_balance: float = 500.0
    risk_per_trade: float = 0.02
    max_daily_loss: float = 0.05
    max_consecutive_losses: int = 3
    min_edge: float = 0.03
    min_confidence: float = 0.60
    max_spread: float = 0.03

    # API Configuration
    polymarket_enabled: bool = True
    data_stale_threshold_ms: int = 10000
    reconnect_delay_seconds: int = 1
    max_reconnect_delay_seconds: int = 30
    data_mode: str = "live"         # 'live' or 'mock'
    execution_mode: str = "paper"
    research_mode: bool = True

    # Strategy / Trade eligibility thresholds
    min_time_remaining_sec: int = 30
    max_time_remaining_sec: int = 300

    # --- Data Quality / Synthetic Safety ---
    # When False: synthetic data is completely prohibited from the real pipeline.
    synthetic_bootstrap: bool = False

    # Maximum spread for RESEARCH DATA storage (structural check only, not trade check)
    # Set very wide — we want to collect all structurally valid observations.
    max_research_spread: float = 0.999

    # Maximum spread for a market to be TRADE ELIGIBLE (tight — strategy constraint)
    max_trade_spread: float = 0.05

    # Minimum total depth (bid+ask) to be TRADE ELIGIBLE
    min_trade_depth: float = 100.0

    # Minimum liquidity for TRADE ELIGIBLE
    min_trade_liquidity: float = 1000.0

    # Minimum requirements before a REAL backtest is permitted
    min_resolved_markets: int = 10
    min_valid_samples: int = 500
    min_class_balance: float = 0.20
    min_feature_completeness: float = 0.80
    
    # --- PHASE 7: Live Execution Architecture ---
    live_trading_enabled: bool = False
    live_trading_kill_switch: bool = True  # MUST default to True for safety
    live_initial_capital: float = 500.0
    live_max_capital: float = 500.0

    # Phase 8: SaaS
    saas_secret_key: str = ""

    # Server & Network Configuration
    server_host: str = "13.140.56.78"
    server_port: int = 8000
    backend_url: str = "http://13.140.56.78:8000"

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
