# AGENTS.md - AIDUS Development Guide

## Project Overview

AIDUS (AI-Driven Dynamic Underwriting System) - A multi-agent, privacy-preserving credit scoring engine using Open Banking, OSINT, and behavioral biometrics.

## Quick Start

```bash
# Start all services (backend, frontend, PostgreSQL, Redis)
docker-compose up

# Backend available at http://localhost:8000
# Frontend available at http://localhost:5500
# API docs at http://localhost:8000/docs
```

## Development Commands

```bash
# Run backend locally (without Docker)
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Run tests (pytest configured but no tests yet)
pytest

# Train ML models (from backend/)
python -m ml.train_bigru
python -m ml.train_rf
```

## Architecture

### Directory Structure

```
backend/
├── agents/          # 5 specialized AI agents
├── ml/              # ML models (BiGRU, Random Forest)
├── models/          # SQLAlchemy ORM models (12 tables)
├── privacy/         # LDP, PII redaction, budget tracking
├── routers/         # FastAPI route handlers
├── schemas/         # Pydantic request/response schemas
├── services/        # External API clients, business logic (14 modules)
├── legal_audits/    # Generated Section 65B PDF certificates
client_sdk/          # Browser-based biometrics tracker
```

### Agent System (LangGraph)

- **Orchestrator** (`backend/agents/orchestrator.py`): Coordinates all agents
- **CashFlow Agent**: Evaluates financial transactions (LLM-powered)
- **OSINT Agent**: Digital identity verification (LLM-powered, has fast-path rejection)
- **Biometrics Agent**: Behavioral analysis (LLM-powered, interprets BiGRU + RF)
- **Self-Check Agent**: Cost and business rule auditing (no LLM, pure logic)
- **Explainability Agent**: Plain-language rationale generation (LLM-powered)

### Decision Thresholds

```python
SCORE_WEIGHTS = {"cashflow": 0.35, "osint": 0.25, "biometrics": 0.25, "selfcheck_modifier": 0.15}
APPROVE_THRESHOLD = 0.4   # Risk < 0.4 = APPROVED
DENY_THRESHOLD = 0.7      # Risk > 0.7 = DENIED
# Between = REVIEW_REQUIRED
```

### Privacy Pipeline

All data passes through before agent evaluation:
1. PII Redaction (11 regex patterns: Aadhaar, PAN, phone, email, etc.)
2. Minor Exclusions (30+ protected field names filtered)
3. LDP Noise Injection (Gaussian mechanism: σ ≥ Δ·√(2·ln(1.25/δ))/ε)
4. Budget Tracking (cumulative ε monitoring per applicant)

## Key Configuration

### Environment Variables (.env)

```bash
# Required for LLM
GROQ_API_KEY=gsk_...

# Mock mode (default: true)
USE_MOCK_DATA=true

# Database (Docker defaults)
DATABASE_URL=postgresql+asyncpg://aidus:aidus_secret@postgres:5432/aidus_db
REDIS_URL=redis://redis:6379/0
```

### Privacy Parameters

```bash
DEFAULT_EPSILON=1.0          # Privacy budget per query
MAX_PRIVACY_BUDGET=10.0      # Cumulative limit per applicant
GRADIENT_CLIP_NORM=1.0       # L2 norm clipping
```

## Important Patterns

### Docker Socket Requirement

Sherlock OSINT runs in isolated Docker containers. The backend mounts the Docker socket:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

Without this, Sherlock falls back to mock data automatically.

### Database Auto-Migration

Tables are created automatically on startup via `Base.metadata.create_all`. No Alembic migrations yet. Schema changes require restarting the backend.

### Mock Mode

When `USE_MOCK_DATA=true` (default):
- Finexer API calls return synthetic transactions (LLM-generated for realism)
- Sherlock returns deterministic mock platform matches (~45% hit rate)
- Docker client failures gracefully degrade to mocks
- HIBP/Digiverifier return synthetic data

### ML Models

**BiGRU Bot Detector** (`backend/ml/bigru_model.py`):
- Architecture: BiGRU(2 layers, 128 hidden) -> Dense(64) -> Dense(1, Sigmoid)
- Input: (batch, 200 timesteps, 6 features)
- Output: Bot probability (0.0=human, 1.0=bot)
- Ensemble weight: 60%

**Random Forest Kinetic Classifier** (`backend/ml/train_rf.py`):
- Features: [mean_velocity, max_velocity, mean_acceleration, jitter, path_straightness, pause_count, click_count]
- Ensemble weight: 40%
- Falls back to heuristic when model not loaded

### Legal Certification

Every OSINT scan generates a Section 65B (Indian Evidence Act / BSA 2023) PDF certificate with SHA-256 integrity hashes. Stored in `backend/legal_audits/`.

## API Endpoints

| Module | Prefix | Purpose |
|--------|--------|---------|
| Consent | `/api/v1/consent/` | OAuth consent management |
| Financial | `/api/v1/financial/` | Bank data aggregation (in consent.py) |
| OSINT | `/api/v1/osint/` | Digital identity verification |
| Biometrics | `/api/v1/biometrics/` | Trajectory & fingerprint capture |
| Privacy | `/api/v1/privacy/` | LDP operations |
| Underwriting | `/api/v1/underwriting/` | Full evaluation pipeline |

## External Dependencies

| Service | API | Mock Fallback |
|---------|-----|---------------|
| Groq LLM | `api.groq.com` | Heuristic in each agent |
| Finexer | `api.finexer.com/v1` | LLM-generated synthetic transactions |
| HaveIBeenPwned | `haveibeenpwned.com/api/v3` | Deterministic mock breaches |
| Digiverifier | `api.digiverifier.com/v1` | Mock PAN/Aadhaar/UAN |
| Sherlock | Docker container | Mock ~45% hit rate on 18 platforms |

## Client SDK

`client_sdk/evtrack.js` - Browser-based behavioral biometrics:
- Captures mouse/touch/scroll at 150ms polling intervals
- Generates device fingerprint (Canvas SHA-256, WebGL vendor/renderer hash)
- Sends trajectory batches of 50 points to `/api/v1/biometrics/trajectory`
- Sends fingerprint to `/api/v1/biometrics/fingerprint`
- CAPI event deduplication via `/api/v1/biometrics/event`

## Known Issues

### Critical (Security/Privacy)

- **CORS wildcard**: `allow_origins=["*"]` in main.py - must restrict in production
- **PAN stored in plaintext**: Database stores PAN unencrypted (Aadhaar is hashed)
- **Privacy budget in-memory only**: Resets on server restart (should use PostgreSQL/Redis)
- **No authentication/authorization**: All endpoints publicly accessible

### High Priority

- **No rate limiting**: `/underwriting/evaluate` triggers LLM + Docker - expensive DoS target
- **Privacy budget pre-check overly conservative**: Assumes 3 agents run even when flags disable some

### Medium Priority

- **Mock Aadhaar returns protected data**: `gender` and `age_band` fields bypass minor exclusion filter
- **`legal_certification.cert_dir` uses relative path**: Breaks if CWD differs from backend root
- **Sherlock Docker timeout**: No outer timeout on executor call - can block thread pool
- **Consent callback uses query params**: Schema `ConsentCallbackRequest` defined but unused
- **`email_intelligence._check_registrations`**: Only works for test/demo emails, dead in production
- **No Alembic migrations**: Schema changes require server restart
- **Privacy budget pre-check assumes 3 agents**: May reject valid queries when fewer agents run

### Low Priority

- **`ConsentCallbackRequest` schema unused**: Dead code
- **`AdjustScoreRequest` schema unused**: Dead code
- **`UnderwritingEvaluateRequest.force_model_tier` unused**: Dead code
- **`smpc_stub.encrypted_sum`**: Returns non-functional dict
- **`budget_tracker.get_budget_status`**: Division by zero if `max_budget=0`

### Fixed

- **Missing `.gitignore`**: Added root [.gitignore](file:///d:/Praneeth_works/Dynamic_underwriting/.gitignore) protecting sensitive environment files (`.env`), Python caches, ML binary models, legal certificates, logs, and IDE settings.
- **`requires_review` always False** (selfcheck_agent.py): Now sets `requires_review = True` when flags raised
- **Consent revoke logs wrong previous status** (consent_manager.py): Now captures status before mutation
- **Double commit in consent router** (consent.py): Replaced `db.commit()` with `db.flush()`
- **`total_distance` computed incorrectly** (trajectory_analyzer.py): Now uses sum of Euclidean distances
- **Duplicate httpx** (requirements.txt): Removed duplicate entry

### Missing

- No test suite (pytest configured but empty)
- No CI/CD pipeline
- No linting/type checking configuration

## Development Tips

1. **Start with mock mode** - Set `USE_MOCK_DATA=true` to avoid external API dependencies
2. **Check Docker socket** - If Sherlock fails, verify Docker is running and socket is accessible
3. **Privacy budget** - Each agent evaluation consumes ε; monitor via `/api/v1/privacy/budget/{applicant_id}`
4. **ML models** - BiGRU and Random Forest models in `backend/ml/saved_models/` are persisted across restarts
5. **API docs** - Always check `/docs` for current endpoint schemas
6. **Legal certificates** - OSINT scans generate PDFs in `backend/legal_audits/` (234 already generated)
7. **Mock data generation** - Finexer mock mode uses Groq to generate realistic Indian bank transactions
8. **Agent fast-paths** - OSINT agent has rejection/approval fast-paths to save LLM costs on obvious cases
