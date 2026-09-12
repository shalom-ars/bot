# BUG AUDIT INVENTORY

## Overview
This document maps the entire Jonanda SaaS architecture for the final bug audit.

### 1. Backend Layer (Python, FastAPI, SQLAlchemy)
**Core Engine:**
- `app/engine/scanner.py`: Core event loop, orchestrator.
- `app/engine/paper_controller.py`: Phase 6 logic.
- `app/engine/user_engine.py`: Phase 8 SaaS logic.
- `app/engine/edge.py`, `app/engine/strategy.py`: Quant systems.

**Trading & Risk:**
- `app/trading/risk.py`: Risk limits (Daily loss, DD).
- `app/trading/paper_engine.py`: Execution.
- `app/trading/live_engine.py`, `app/trading/eligibility.py`: Phase 7 hard-block.

**API & Security:**
- `app/api/auth.py`, `app/api/users.py`, `app/api/admin.py`
- `app/api/security.py`: JWT, Hashlib.
- `app/api/health.py`: Status checks.

**Connectors & Database:**
- `app/connectors/polymarket.py`
- `app/db/session.py`, `app/db/models.py`
- `scripts/migrate_to_postgres.py`, `scripts/backup_db.sh`, `scripts/restore_db.sh`

### 2. Frontend Layer (React, Vite, Tailwind)
- `src/App.tsx`: Routing.
- `src/components/Layout.tsx`, `AuthLayout.tsx`.
- `src/pages/LandingPage.tsx`, `Dashboard.tsx`, `ResearchTerminal.tsx`.
- `src/pages/auth/Login.tsx`, `Signup.tsx`.

### 3. Mobile Layer (React Native, Expo)
- `src/navigation/AppNavigator.tsx`
- `src/screens/HomeScreen.tsx`, `LoginScreen.tsx`
- `src/services/api.ts`
- `src/store/authStore.ts`

### 4. Tests
- `backend/tests/`: 50 pytests validating auth, models, strategy, data_quality, paper_test.

*Action items: Deep code review tracing Polymarket socket down to user_trades.*
