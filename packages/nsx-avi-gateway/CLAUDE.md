# NSX-AVI Gateway

NSX-T and AVI Load Balancer API Gateway for multi-site management using FastAPI.

## Tech Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI with Uvicorn
- **Auth**: PyJWT (JWT), passlib (bcrypt)
- **Async**: aiofiles, httpx
- **Logging**: structlog
- **VMware**: NSX-T SDK, AVI SDK (installed separately)
- **CI/CD**: GitLab CI

## Development Commands

```bash
# Setup virtual environment
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests with coverage
pytest --cov=app --cov-report=html

# Code quality
ruff check .
ruff format .
mypy app/

# View coverage report
open htmlcov/index.html
```

## Project Structure
- `app/` - FastAPI application code
- `tests/` - Test suite (unit, integration, e2e)
- `config/` - Configuration files
- `logs/` - Application logs

## Suggested Claude Code Plugins

### MCP Servers
- **filesystem** - For editing configuration files
- **docker** - Container management

### Skills
- **nsx-avi-reference** - Essential for NSX-T and AVI API operations, data models, and configuration patterns

### Recommended Workflow
1. Use `ruff check` and `ruff format` before committing
2. Run `pytest` with coverage to validate changes
3. Use `mypy` for type checking
4. Reference NSX-T and AVI API docs via the nsx-avi-reference skill
