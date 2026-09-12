# Polymarket Quant Bot - MVP

A local-first quantitative trading bot for Polymarket prediction markets.

**IMPORTANT: This is a PAPER-TRADING MVP only.** It simulates trades locally based on live market data and statistical models. It does NOT implement real-money order execution and does NOT require or use private keys or real trading credentials.

## Features
- **Paper Trading Engine**: Simulates execution, tracks P&L, and manages positions locally in SQLite.
- **Data Connectors**: Connects to Polymarket (via REST) and Binance (via WebSocket) for live market data.
- **Risk Management**: Enforces daily loss limits, maximum consecutive losses, and risk-per-trade.
- **Baseline Probability Model**: Uses a basic Logistic Regression model for statistical probability estimates.
- **React Dashboard**: A professional dark-themed trading terminal to view active markets, positions, and risk status.

## Prerequisites
- Python 3.11+ (tested on Windows)
- Node.js (for the frontend)

## Installation & Setup

1. **Clone/Download** this repository.
2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and adjust the paper-trading limits.
   ```
   MODE=paper
   STARTING_BALANCE=100
   RISK_PER_TRADE=0.01
   MAX_DAILY_LOSS=0.05
   ```
3. **Run the Startup Script**:
   Double-click `start.bat`. This will automatically start the backend on port 8000 and the frontend on port 5173.

Alternatively, you can start them manually:
**Backend**:
```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
**Frontend**:
```cmd
cd frontend
npm install
npm run dev
```

## Architecture
- `backend/app/main.py`: Entry point for FastAPI.
- `backend/app/engine/`: Core logic for feature generation, market scanning, and probability modeling.
- `backend/app/trading/`: Paper execution and risk limits.
- `backend/app/connectors/`: External API/WS interactions.
- `frontend/`: React + Vite + Tailwind CSS dashboard.

## Disclaimer
This is for educational and simulation purposes only. Do not use the logic here for real-money trading without extensive historical backtesting and authentication upgrades.
