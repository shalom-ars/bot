import pytest
from unittest.mock import patch, MagicMock
from app.engine.paper_controller import PaperTestController
from app.db.models import PaperTestSession
from datetime import datetime

def test_paper_controller_initialization_creates_new():
    with patch('app.engine.paper_controller.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db
        
        # First query (check active): None
        # Second query (retrieve new): MagicMock with initial_balance=500.0
        mock_new_session = MagicMock(initial_balance=500.0)
        mock_db.query().filter().order_by().first.return_value = None
        mock_db.query().filter_by().first.return_value = mock_new_session

        # Mock the risk manager
        risk_mock = MagicMock()

        controller = PaperTestController(risk_mock)

        # Verify it created a new one with $500
        assert controller.session_id is not None
        mock_db.add.assert_called_once()

def test_paper_controller_resumes_existing():
    with patch('app.engine.paper_controller.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db

        # Active session found
        mock_session_record = MagicMock(session_id="pts_123", initial_balance=500.0)
        mock_db.query().filter().order_by().first.return_value = mock_session_record
        mock_db.query().filter_by().first.return_value = mock_session_record

        # Mock the risk manager
        risk_mock = MagicMock()

        controller = PaperTestController(risk_mock)

        # Verify it resumed
        assert controller.session_id == "pts_123"

def test_update_session_stats():
    with patch('app.engine.paper_controller.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db

        mock_session_record = MagicMock(session_id="pts_123", initial_balance=500.0)
        mock_db.query().filter().order_by().first.return_value = mock_session_record
        mock_db.query().filter_by().first.return_value = mock_session_record

        risk_mock = MagicMock()
        risk_mock.current_balance = 520.0
        risk_mock.current_exposure = 30.0
        risk_mock.peak_balance = 550.0

        controller = PaperTestController(risk_mock)
        controller.update_session_stats()

        assert mock_session_record.current_balance == 520.0
        assert mock_session_record.equity == 550.0
        # draw down from peak (550 - 550) / 550 = 0
        assert mock_session_record.drawdown == 0.0

def test_health_status_format():
    with patch('app.engine.paper_controller.SessionLocal') as MockSession:
        mock_db = MagicMock()
        MockSession.return_value = mock_db

        mock_session_record = MagicMock(
            session_id="pts_123",
            start_time=datetime.utcnow(),
            status="RUNNING",
            initial_balance=500.0,
            drawdown=0.10,
            win_rate=0.55,
            closed_trades=10
        )

        mock_db.query().filter_by().first.return_value = mock_session_record
        mock_db.query().filter().order_by().first.return_value = mock_session_record

        risk_mock = MagicMock()
        risk_mock.current_balance = 450.0
        risk_mock.current_exposure = 10.0
        risk_mock.daily_pnl = -50.0
        risk_mock.open_positions_count = 1
        risk_mock.is_paused = False

        controller = PaperTestController(risk_mock)
        status = controller.get_health_status()

        assert status["paper_test_status"] == "RUNNING"
        assert status["session_id"] == "pts_123"
        assert status["balance"] == 450.0
        assert status["equity"] == 460.0
        assert status["win_rate"] == 0.55
