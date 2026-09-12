import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from app.research.backtester import Backtester

def test_backtester_blocked_on_insufficient_data():
    with patch('app.research.dataset.DatasetBuilder.check_research_readiness') as mock_ready:
        mock_ready.return_value = {
            "status": "RESEARCH_BLOCKED",
            "resolved_markets": 0,
            "valid_samples": 0,
            "reasons": ["Insufficient data"]
        }
        
        backtester = Backtester()
        result = backtester.run_backtest()
        
        assert result["status"] == "BLOCKED"
        assert result["reason"] == "INSUFFICIENT REAL DATA"
        assert result["resolved_markets"] == 0

def test_backtester_chronological_pass():
    with patch('app.research.dataset.DatasetBuilder.check_research_readiness') as mock_ready, \
         patch('app.research.dataset.DatasetBuilder.build_dataset') as mock_build, \
         patch('app.research.backtester.SessionLocal') as mock_session:
         
        mock_ready.return_value = {
            "status": "RESEARCH_READY",
            "resolved_markets": 10,
            "valid_samples": 500,
            "reasons": []
        }
        
        # Mock empty test df to trigger the next block
        mock_build.return_value = (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        
        backtester = Backtester()
        result = backtester.run_backtest()
        
        assert result["status"] == "BLOCKED"
        assert result["reason"] == "Insufficient test splits after chronological filter"
