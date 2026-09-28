# AquaFlow Professional V9 — delivery & deployment

## Local
1. Install Python 3.12+ / 3.13.
2. Run `start-professional.bat`.
3. Open `http://127.0.0.1:8799`.

## API
- Health: `/api/health`
- Swagger: `/api/docs`
- Login: `/api/auth/login`
- Session: `/api/auth/me`
- Bootstrap: `/api/bootstrap`
- Sync: `/api/sync`
- Audit: `/api/audit` (admin)

## Security before production
- Set a long random `AQUAFLOW_SECRET`.
- Set `AQUAFLOW_COOKIE_SECURE=1` behind HTTPS.
- Use PostgreSQL for multi-user production workloads.
- Replace demo passwords and seed users.
- Use Argon2id or bcrypt through a maintained password library.
- Put the API behind HTTPS + reverse proxy, rate limiting and log monitoring.
- Move service photos to object storage.
- Add scheduled backups and restore drills.
- Restrict CORS to exact production origins.
- Add server-side per-role permissions for each CRUD endpoint.

## Testing
Run `python -m pytest backend/tests -q` after installing requirements and pytest.

## Architecture
Browser UI -> FastAPI -> SQLite (local reference) / PostgreSQL (production).
The UI retains a local-first fallback for offline use; when the API is available, successful login loads relational server state and writes changes through the sync endpoint.
