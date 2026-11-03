# KuSys 1.0

KuSys transforms customer documents into traceable requirements, engineering work packages, a resource-leveled schedule with critical-path analysis, and versioned quotations with requirement-level budget and price impact.

The normative functional source is `KuSys_Rebuild_Spec.md`.

## Product workflow

1. Upload PDF, DOCX, or PNG customer documents.
2. Extract text/tables and run OCR where required.
3. Review, normalize, classify, exclude or edit source sections; approve a review revision.
4. Run deterministic offline analysis (or plug in an external `AIProvider`) to create atomic requirements, clarifications, work packages and traceability.
5. Maintain requirement budgets, relations, revisions and non-destructive impact/what-if analyses.
6. Maintain work packages, dependencies, rate card, role/FTE capacity and calendar.
7. Calculate resource leveling, schedule, float and critical path.
8. Build multiple offer variants/scopes; calculate cost, sales price, risk, discount, VAT, margin, budget deviations and requirement attribution.
9. Release with four-eyes approval. The exact baseline/calculation/template is frozen and an immutable DOCX is generated.
10. Export DOCX/XLSX; publish immutable artifacts to the customer portal.

## Architecture

KuSys is a modular monolith with separate runtime processes:

- React/TypeScript frontend behind Nginx
- FastAPI API
- Celery worker
- Celery beat scheduler
- PostgreSQL
- Redis
- local filesystem artifact storage behind an adapter

The backend code is organized by domain (`auth`, `documents`, `review`, `analysis`, `requirements`, `planning`, `pricing`, `offers`, `templates`, `artifacts`, `audit`). Authoritative pricing and planning logic is server-side and deterministic.

## Start a local/pilot installation

Requirements: Docker + Docker Compose. 32 GB RAM is recommended for the reference workload.

```bash
cp .env.example .env
# Edit KUSYS_DB_PASSWORD and KUSYS_MASTER_KEY.
cp config/kusys.example.yaml config/kusys.yaml
./kusys up
```

Open `http://localhost:5173`.

Demo accounts (synthetic data, common password `KuSys-Demo-2026`):

- `sophie.schneider` — company admin
- `max.mustermann` — project lead / normal demo author
- `lea.pruefer` — independent project lead for four-eyes approval
- `kunde.nordstern` — customer portal
- `platform.admin` — platform admin with no automatic tenant access

Change all demo passwords before any real use.

## Development

```bash
./kusys dev
```

The development Compose overlay uses an inline job mode so document extraction/analysis can be exercised without waiting for a separate worker; the production Compose file runs API, worker and scheduler separately.

Backend only:

```bash
cd backend
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
alembic -c alembic.ini upgrade head
python -m kusys.seed
uvicorn kusys.main:app --reload
```

Frontend only:

```bash
cd apps/frontend
npm install
npm run dev
```

## Tests

```bash
./kusys test
./kusys verify
```

Cross-browser E2E after the stack is running:

```bash
cd apps/frontend
npx playwright install
npm run test:e2e -- --project=chromium
# compatibility suite:
npm run test:e2e
```

The Playwright config includes Chromium, Chrome, Edge, Firefox and WebKit.

## Backup / restore

```bash
./kusys backup
./kusys restore backups/kusys-YYYYMMDDTHHMMSSZ
```

A full backup contains a PostgreSQL custom-format dump, artifact archive, secrets-free configuration snapshot, version/migration metadata and SHA-256 manifest. Restore validates the manifest before changing the installation. `./kusys migrate` creates a validated backup before upgrading an existing schema.

## Release locks and SBOM

All direct dependencies and container images are exactly pinned. Resolve transitive locks on a registry-connected release host:

```bash
./kusys locks
./kusys verify
```

See `LOCKFILE_STATUS.md` for why resolved locks are not fabricated in this archive. `SBOM.cdx.json` is a CycloneDX component manifest and `RELEASE_MANIFEST.sha256` covers the release files.

## Configuration and secrets

Precedence is defaults → YAML → environment; environment wins. The example YAML contains no secrets. Database passwords, the master key and external AI/OCR keys belong in environment variables or secret files. Production should set secure cookies and terminate HTTPS in front of Nginx.

## Demo/rebuild validation

A successful target-environment rebuild should prove:

- migrations apply to a fresh PostgreSQL database;
- demo seed is visible and login works;
- Upload → Review → Analysis → Requirements → Work packages → Schedule → Offer → DOCX works;
- released offers are immutable;
- customer sees only explicitly published artifacts;
- backup + restore succeeds;
- Playwright critical journeys pass;
- the reference performance targets are measured separately.

See `IMPLEMENTATION_STATUS.md`, `ACCEPTANCE_MATRIX.md` and `STORY_TEST_MATRIX.md` for the exact implementation and verification status of this archive.
