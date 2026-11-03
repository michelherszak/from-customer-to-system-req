# KuSys version manifest — 2026-09-24

Stable releases were selected; alpha/beta/RC releases were excluded.

## Runtime and infrastructure
- Python 3.14.7 (`python:3.14.7-slim`)
- Node.js 26.10.0 (`node:26.10.0-alpine3.24`)
- PostgreSQL 18.6 (`postgres:18.6-alpine3.24`)
- Redis Open Source 8.10.2 (`redis:8.10.2-alpine`)
- Nginx 1.31.6 (`nginx:1.31.6-alpine3.24-slim`)

## Backend direct dependencies
- FastAPI 0.141.1
- Uvicorn 0.51.0
- Pydantic 2.13.5
- pydantic-settings 2.15.0
- SQLAlchemy 2.0.54
- Alembic 1.20.0
- psycopg 3.3.6
- Celery 5.6.3
- redis-py 8.1.0
- python-multipart 0.0.32
- python-docx 1.2.0
- openpyxl 3.1.5
- PyMuPDF 1.28.2
- pdfplumber 0.11.10
- OCRmyPDF 17.12.1
- PyYAML 6.0.3
- argon2-cffi 25.1.0
- cryptography 50.0.1
- pytest 9.1.1
- pytest-cov 7.1.0
- httpx 0.28.1
- Ruff 0.16.8

## Frontend direct dependencies
- React / React DOM 19.3.0
- React Router 8.3.1
- Material UI 9.4.0
- TanStack Query 5.103.2
- TanStack Table 9.2.4
- Tiptap React / Starter Kit 3.31.3
- dnd-kit core 6.3.1
- Vite 8.3.0
- @vitejs/plugin-react 6.1.1
- TypeScript 7.0.2
- Playwright Test 1.63.0

`kusys-environment.yaml`, `backend/pyproject.toml`, `backend/requirements.lock`, `apps/frontend/package.json`, and the Compose/Docker files are the machine-readable release references.
