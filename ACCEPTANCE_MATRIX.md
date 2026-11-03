# KuSys v1 — Spezifikations-/Implementierungsmatrix

Stand: 2026-09-24. Diese Matrix ordnet die normative `KuSys_Rebuild_Spec.md` der Implementierung zu. „Implementiert“ bedeutet Quellcode vorhanden; „verifiziert“ bedeutet zusätzlich durch die lokale Releaseprüfung oder automatisierte Tests geprüft. Externe Dienste/Browser/Docker benötigen die im Status beschriebenen Zielumgebungsprüfungen.

| Spec | Bereich | Implementierung | Nachweis |
|---|---|---|---|
| 1–6 | Produkt, Reproduzierbarkeit, Stack, Repo, Konfiguration | Modularer Monolith, YAML/Env-Konfiguration, Docker/Dev-Struktur | `docker-compose*.yml`, `kusys-environment.yaml`, `config/`, `VERSIONS.md` |
| 7 | Mandanten/Rollen/Plattformfreigabe/Kunde | Sessions, Tenant-/Projektrollen, zeitbegrenzte Plattformfreigabe, Kundenportal | `backend/kusys/auth`, `tenancy`, `portal`; Full-flow-Test |
| 8–10 | Stamm-/Projektdaten, Versionierung, Kernmodell | SQLAlchemy-Modelle aller spezifizierten Aggregate, Soft Delete, Revision/Lock-Version | `backend/kusys/persistence/models.py`, Alembic; frische Migration = 52 Tabellen |
| 11 | Dokumenteingang | PDF/DOCX/PNG, Signatur/MIME/Größenprüfung, Extraktion, OCR-Workflow, versionierte Artefakte/Fundstellen | `backend/kusys/documents`; Full-flow-Test |
| 12 | Prüfschritt | Revisionen, Kategorien, Freigabe, bearbeiten/streichen/löschen/wiederherstellen/teilen/zusammenführen | `backend/kusys/review`; API-/Integrationstests |
| 13 | KI-/Analyseworkflow | persistente Analyseläufe, feste Schemas, Chunking/Deduplizierung, deterministischer Fallback, OpenAI-kompatibler Provider, verschlüsselte Keys, Usage-Kosten | `backend/kusys/analysis`, `ai_config`; Rule-based-/Integrationstests |
| 14 | Anforderungen/Klärung/Budget/Beziehungen/Impact | Revisionen, Baselines, Budgets, Relationen, Kostenattribution, transitive nicht-destruktive What-if-Analyse | `requirements`, `impact`, `pricing`; Unit-/Integrationstests |
| 15 | Arbeitspakete/Planung | PERT-Werte, Risiko-Vorschlag, echte Rollenkapazität, Kalender/Feiertage, CPM, Zyklusprüfung, Angebotsplan | `planning`, `calendars`; Planning-/Full-flow-Tests |
| 16 | Rate-Card | Firmenvorlage, Projektkopie, interne/externe Rollen, Sätze, FTE, Diff/Reload ohne stilles Löschen verwendeter Rollen | `services/calculation.py`, `planning/api.py` |
| 17 | Angebote | Varianten, Scope, anteilige Pakete/Material, Risiko/Rabatt/MwSt., Zahlungsplan, Vier-Augen, immutable Snapshot, Positionen/Textbausteine | `offers`; Full-flow-Test |
| 18 | Abgabedokumente | versionierte Templates, Bausteine, Header/Footer, Sprachen, Template-Snapshots, Artefaktpublikation | `templates`, `offers/export.py` |
| 19 | Excel | internes Projekt-Workbook mit Anforderungen, AP, Plan, Klärungen, Kalkulation, Rollen, Material, Angebot | `offers/export.py`; Exporttest im Full-flow |
| 20 | Sicherheit | Argon2id, serverseitige Session, HttpOnly/SameSite/Secure, CSRF, Login-Sperre, verschlüsselte Secrets, autorisierte Artefakte | `auth`, `common/security.py`; Full-flow-Test |
| 21 | Mehrbenutzerbetrieb | `lock_version`, HTTP 409 mit Konfliktdaten, Presence-Heartbeat | `common/locking.py`, `presence`; Integrationstest |
| 22 | Hintergrundjobs | persistente Jobs, Celery/Redis, Idempotenz, Cancel, SSE-Fortschritt | `jobs`, Worker/Scheduler Compose |
| 23 | API | `/api/v1`, domänenbezogene Router, 202/Job-IDs für lange Prozesse | `backend/kusys/main.py` und Module |
| 24 | Dateispeicher | Storage-Adapter, lokale Artefakte, DB-Metadaten/SHA-256, autorisierter Download | `artifacts`, `common/storage.py` |
| 25 | Backup/Restore | DB + Artefakte + Config/Version + Manifest/Hashes, Rotation, Restoreprüfung | `ops/backup`, `ops/restore` |
| 26 | Start/Deployment | Compose, Dev-Compose, Wrapper; Port-Fallback +20 und Strict Mode | `./kusys`, `ops/port-fallback.sh` |
| 27 | Performance | deterministische Rechenbenchmark + Ziele in Konfiguration | `ops/performance/benchmark.py`; Zielhost-Benchmark erforderlich |
| 28 | Demo/Testdaten | synthetischer Mandant/Kunde/Projekt/Benutzer | `backend/kusys/seed.py`, `fixtures/` |
| 29 | Tests | Unit/Domain/API/Integration/Export + Playwright-Suite | `backend/tests`, `apps/frontend/e2e`; lokale Backend-Suite verifiziert |
| 30–31 | Wiederherstellung/Release | Migrations-, Seed-, Health-, Lock-, Verify-, SBOM- und Manifest-Skripte | `ops/`, `./kusys` |
| 32–35 | bestätigte Entscheidungen, Reihenfolge, DoD, Releaseartefakte | Entscheidungen im Code/Status gespiegelt; Release-Archiv/SHA-Manifest wird erzeugt | `IMPLEMENTATION_STATUS.md`, `release-manifest.sha256` |

## Zielumgebungs-Gates

Die Quellimplementierung ist vollständig assembliert. Vor produktiver Abnahme müssen auf einer registry- und Docker-fähigen Zielmaschine zusätzlich `./kusys locks`, `./kusys verify`, Docker-Start, Playwright, Backup→Restore und der Performance-Benchmark erfolgreich laufen. Diese Checks werden nicht als „bestanden“ behauptet, wenn sie in der Assembly-Umgebung technisch nicht ausführbar waren.
