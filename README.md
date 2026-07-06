# NSX-T/AVI API Gateway

Production-ready FastAPI gateway for managing 20+ NSX-T and AVI Load Balancer sites with OAuth2/JWT authentication, async job tracking, idempotency, API versioning, comprehensive audit logging, and operation allowlist enforcement.

## Features

✅ **OAuth2/JWT Authentication** - Token-based auth with role-based permissions (admin, operator, readonly)
✅ **Async Job Tracking** - Non-blocking operations with status polling via job IDs
✅ **Idempotency** - Prevent duplicate operations with `Idempotency-Key` header support
✅ **API Versioning** - `/api/v1/` prefix for backward compatibility
✅ **Full CRUD Operations** - GET, POST, PATCH support (DELETE blocked by default)
✅ **OpenAPI/Swagger Docs** - Auto-generated interactive API documentation
✅ **Operation Allowlist** - Default-deny with configurable allowed operations per role
✅ **Structured Audit Logging** - JSONL format for compliance and state reconstruction
✅ **Multi-Site Support** - Manage 20+ NSX-T/AVI sites from single endpoint
✅ **Error Handling** - Standardized HTTP status codes and error responses
✅ **SDK-Free Integrations** - NSX-T Policy API and AVI Controller calls use raw `httpx` REST clients

## Architecture

```
nsx-avi-gateway/
├── app/
│   ├── api/v1/          # Versioned API endpoints
│   ├── auth/            # JWT, OAuth2, RBAC
│   ├── core/            # Job tracker, idempotency, allowlist, audit log
│   ├── clients/         # NSX-T/AVI REST clients (httpx)
│   ├── models/          # Pydantic request/response models
│   ├── operations/      # Async operation handlers
│   ├── middleware/      # Request ID, error handling
│   └── main.py          # FastAPI app with lifespan
├── config/
│   ├── sites.yml        # 20+ site configurations
│   └── operations_allowlist.yml  # Permitted operations
├── logs/
│   └── audit.jsonl      # Structured audit trail
└── tests/               # Unit and integration tests
```

## Quick Start

### 1. Installation

```bash
cd nsx-avi-gateway

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Install dev dependencies (optional)
pip install -e ".[dev]"
```

### 2. Configuration

```bash
# Copy example configurations
cp .env.example .env
cp config/sites.yml.example config/sites.yml
cp config/operations_allowlist.yml.example config/operations_allowlist.yml

# Edit .env and set JWT secret plus password hashes
nano .env
# Set GATEWAY_JWT_SECRET_KEY to a strong random value:
# openssl rand -hex 32
#
# Set GATEWAY_ADMIN_PASSWORD_HASH, GATEWAY_OPERATOR_PASSWORD_HASH,
# and GATEWAY_READONLY_PASSWORD_HASH to explicit passlib hashes

# Configure your NSX-T/AVI sites
nano config/sites.yml
```

### 3. Run the Server

```bash
# Development mode (with auto-reload)
python -m app.main

# Or using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. Access API Documentation

Open your browser to:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

## API Usage

### Authentication

```bash
# Get access token
export OPERATOR_PASSWORD='...'
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=operator&password=${OPERATOR_PASSWORD}"

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}

# Use token in subsequent requests
export TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

### Create NSX-T Segment (Async)

```bash
curl -X POST "http://localhost:8000/api/v1/nsxt/dc1-prod/segments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: segment-web-001-create" \
  -d '{
    "name": "seg-web-001",
    "tier1_gateway": "/infra/tier-1s/T1-Gateway",
    "subnets": ["10.1.100.0/24"],
    "vlan": 100,
    "tags": [{"scope": "app", "tag": "web"}]
  }'

# Response:
{
  "job_id": "job_a1b2c3d4e5f6",
  "operation": "nsxt.segment.create",
  "site_id": "dc1-prod",
  "status": "pending",
  "progress": 0,
  "created_at": "2025-12-27T10:30:45Z",
  "user": "operator",
  "idempotency_key": "segment-web-001-create"
}
```

### Check Job Status

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/job_a1b2c3d4e5f6" \
  -H "Authorization: Bearer $TOKEN"

# Response:
{
  "job_id": "job_a1b2c3d4e5f6",
  "operation": "nsxt.segment.create",
  "site_id": "dc1-prod",
  "status": "completed",
  "progress": 100,
  "created_at": "2025-12-27T10:30:45Z",
  "completed_at": "2025-12-27T10:31:15Z",
  "result": {
    "segment_id": "seg-web-001",
    "state": "success",
    "path": "/infra/segments/seg-web-001"
  }
}
```

### List Sites

```bash
curl -X GET "http://localhost:8000/api/v1/sites?environment=production" \
  -H "Authorization: Bearer $TOKEN"
```

### List Jobs with Filtering

```bash
curl -X GET "http://localhost:8000/api/v1/jobs?status=running&site_id=dc1-prod&page=1&page_size=50" \
  -H "Authorization: Bearer $TOKEN"
```

## Configuration

### Environment Variables (.env)

```bash
# Application
GATEWAY_APP_NAME="NSX-T/AVI API Gateway"
GATEWAY_DEBUG=false

# JWT Authentication (required)
GATEWAY_JWT_SECRET_KEY=
GATEWAY_JWT_ALGORITHM=HS256
GATEWAY_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Explicit local user password hashes (required)
GATEWAY_ADMIN_PASSWORD_HASH=
GATEWAY_OPERATOR_PASSWORD_HASH=
GATEWAY_READONLY_PASSWORD_HASH=

# Job Tracking
GATEWAY_JOB_RETENTION_MINUTES=1440  # 24 hours
GATEWAY_JOB_CLEANUP_INTERVAL_SECONDS=300  # 5 minutes
GATEWAY_MAX_CONCURRENT_JOBS=50

# API Timeouts
GATEWAY_API_CONNECTION_TIMEOUT=30
GATEWAY_API_OPERATION_TIMEOUT=300  # 5 minutes

# Idempotency
GATEWAY_IDEMPOTENCY_CACHE_TTL_SECONDS=86400  # 24 hours

# Logging
GATEWAY_LOG_LEVEL=INFO
GATEWAY_LOG_FORMAT=json
GATEWAY_AUDIT_LOG_PATH=logs/audit.jsonl
```

### Site Configuration (config/sites.yml)

```yaml
sites:
  - site_id: "dc1-prod"
    name: "DC1 Production"
    region: "us-east"
    nsxt:
      manager_url: "https://nsxt-dc1.example.com"
      username: "api-gateway"
      password: "${ENV:NSXT_DC1_PASSWORD}"  # From environment variable
      verify_ssl: true
    avi:
      controller_url: "https://avi-dc1.example.com"
      username: "api-gateway"
      password: "${ENV:AVI_DC1_PASSWORD}"
      tenant: "admin"
      api_version: "22.1.3"
    tags:
      environment: production
      cost_center: engineering
```

### NSX-T and AVI Client Pattern

The gateway uses direct `httpx.AsyncClient` calls for both platforms:

- `app/clients/nsxt_client.py` talks to the NSX-T Policy API
- `app/clients/avi_client.py` talks to the AVI Controller REST API

No VMware SDK packages are required in `pyproject.toml`.

### Operations Allowlist (config/operations_allowlist.yml)

```yaml
nsxt:
  segments:
    - create
    - read
    - update
    # DELETE not listed = blocked

  blocked:
    - "tier0_gateways.*"      # Block all T0 operations
    - "segments.delete"        # Prevent segment deletion
    - "security_policies.*"    # Block security changes

avi:
  virtual_services:
    - create
    - read
    - update

  pools:
    - create
    - read
    - update
    - delete  # Pools can be safely deleted

role_overrides:
  admin:
    additional_permissions:
      - "nsxt.segments.delete"
      - "avi.virtual_services.delete"
```

## Authentication & Authorization

### Explicit Authentication Configuration

The service no longer ships with any built-in user credentials. You must set all of
the following before startup:

- `GATEWAY_JWT_SECRET_KEY`
- `GATEWAY_ADMIN_PASSWORD_HASH`
- `GATEWAY_OPERATOR_PASSWORD_HASH`
- `GATEWAY_READONLY_PASSWORD_HASH`

If any are missing, the app fails fast with a clear startup error.

The usernames remain `admin`, `operator`, and `readonly`, and the RBAC role mapping
is unchanged.

Generate password hashes with passlib:

```bash
python -c "from getpass import getpass; from app.auth.oauth2 import get_password_hash; print(get_password_hash(getpass()))"
```

### Permission Format

Permissions follow the pattern: `platform:resource:action`

Examples:
- `nsxt:segment:create`
- `avi:virtual_service:read`
- `nsxt:*` (wildcard - all NSX-T operations)
- `avi:pool:*` (all pool operations)

## Idempotency

Prevent duplicate operations by including `Idempotency-Key` header:

```bash
curl -X POST "http://localhost:8000/api/v1/nsxt/dc1-prod/segments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: unique-operation-key-12345" \
  -d '{"name": "seg-web-001", ...}'
```

- Same key within 24 hours returns cached response
- Response includes `X-Idempotency-Replay: true` header for cached responses

## Audit Logging

All operations are logged to `logs/audit.jsonl` in structured JSON format:

```json
{
  "timestamp": "2025-12-27T10:30:45.123Z",
  "event_type": "operation.started",
  "user": "operator",
  "operation": "nsxt.segment.create",
  "site_id": "dc1-prod",
  "job_id": "job_xyz789",
  "idempotency_key": "segment-web-001-create",
  "request_body": {...}
}
```

Query audit logs:

```bash
# Get all operations by user
cat logs/audit.jsonl | jq 'select(.user == "operator")'

# Get failed operations
cat logs/audit.jsonl | jq 'select(.event_type == "operation.failed")'

# Get operations on specific site
cat logs/audit.jsonl | jq 'select(.site_id == "dc1-prod")'
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_inventory.py

# Run integration tests only
pytest tests/integration/
```

## Development

### Code Quality

```bash
# Format code
ruff format app/ tests/

# Lint code
ruff check app/ tests/

# Type checking
mypy app/
```

### Project Structure

```
app/
├── api/v1/              # API endpoints (auth, jobs, sites, nsxt, avi)
├── auth/                # JWT (jwt.py), OAuth2 (oauth2.py), RBAC (rbac.py)
├── core/                # Core business logic
│   ├── inventory.py     # Site YAML parser
│   ├── job_tracker.py   # Async job tracking
│   ├── idempotency.py   # Idempotency key cache
│   ├── allowlist.py     # Operation validation
│   └── audit_log.py     # Structured logging
├── clients/             # httpx-based REST clients
│   ├── base_client.py   # Retry/timeout logic
│   ├── nsxt_client.py   # NSX-T operations
│   └── avi_client.py    # AVI operations
├── models/              # Pydantic models
│   ├── auth.py          # User, Token, UserInfo
│   ├── job.py           # JobResponse, JobDetail, JobStatus
│   ├── nsxt.py          # NSX-T request/response
│   ├── responses.py     # Standard responses
│   └── errors.py        # Error responses
├── operations/          # Operation handlers
│   ├── base.py          # BaseOperation with run_async()
│   └── nsxt/segments.py # Segment operations
├── middleware/          # HTTP middleware
│   ├── request_id.py    # Request ID injection
│   └── error_handler.py # Global error handling
└── main.py              # FastAPI app entry point
```

## Production Deployment

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```bash
# Build and run
docker build -t nsx-avi-gateway .
docker run -p 8000:8000 --env-file .env nsx-avi-gateway
```

### Production Checklist

- [ ] Change `GATEWAY_JWT_SECRET_KEY` to strong random value (`openssl rand -hex 32`)
- [ ] Set `GATEWAY_DEBUG=false`
- [ ] Set `GATEWAY_ADMIN_PASSWORD_HASH`, `GATEWAY_OPERATOR_PASSWORD_HASH`, and `GATEWAY_READONLY_PASSWORD_HASH`
- [ ] Configure site passwords via environment variables or Vault
- [ ] Enable SSL/TLS (use reverse proxy like Nginx)
- [ ] Set up log rotation for audit logs
- [ ] Configure CORS origins if needed
- [ ] Run with multiple workers: `--workers 4`
- [ ] Set up monitoring and alerting
- [ ] Review and customize operations allowlist
- [ ] Verify explicit auth credentials are configured before startup

## API Reference

### Endpoints

#### Authentication
- `POST /api/v1/auth/token` - Obtain JWT access token
- `GET /api/v1/auth/me` - Get current user info

#### Jobs
- `GET /api/v1/jobs/{job_id}` - Get job status and result
- `GET /api/v1/jobs` - List jobs with filtering
- `POST /api/v1/jobs/{job_id}/cancel` - Cancel job (admin only)
- `GET /api/v1/jobs/stats/summary` - Get job statistics

#### Sites
- `GET /api/v1/sites` - List all sites
- `GET /api/v1/sites/{site_id}` - Get site details
- `POST /api/v1/sites/reload` - Reload site inventory (admin only)

#### NSX-T
- `POST /api/v1/nsxt/{site_id}/segments` - Create segment
- `PATCH /api/v1/nsxt/{site_id}/segments/{segment_id}` - Update segment

#### Health
- `GET /health` - Basic health check (unauthenticated)

## Troubleshooting

### Common Issues

**1. "Site configuration file not found"**
```bash
cp config/sites.yml.example config/sites.yml
nano config/sites.yml  # Configure your sites
```

**2. "Operations allowlist file not found"**
```bash
cp config/operations_allowlist.yml.example config/operations_allowlist.yml
```

**3. "Could not validate credentials"**
- Check JWT secret key is set in `.env`
- Check the required `*_PASSWORD_HASH` variables are set
- Verify token hasn't expired (60 minutes default)
- Use correct username/password

**4. "Operation blocked"**
- Check `config/operations_allowlist.yml`
- Verify user role has required permissions
- Review audit logs for details

## License

MIT License

## Support

For issues and feature requests, please contact the infrastructure team.

---

**Built with FastAPI, Pydantic, and ❤️ for network automation**
