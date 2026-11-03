# KuSys v1 implementation status

Stand: 2026-09-24

## Implementierter Produktumfang

Das Repository enthält die vollständige Quellimplementierung des in `KuSys_Rebuild_Spec.md` beschriebenen KuSys-v1-Kerns entlang der durchgehenden Kette:

**Kundendokument → Prüfschritt → Analyse → Anforderungen → Arbeitspakete → Terminplan → Kalkulation → Angebot → DOCX/XLSX**

Enthalten sind insbesondere:

- Mandanten, Benutzer, Firmen-/Projektrollen, Plattform-Admin-Freigaben und Kundenportal;
- serverseitige Sessions, CSRF, Argon2id, Login-Sperren, verschlüsselte externe Secrets und autorisierter Artefaktzugriff;
- Projekte/Kunden, Dokument- und Versionsverwaltung, PDF/DOCX/PNG-Extraktion und lokaler OCR-Pfad;
- versionierter Prüfschritt mit Freigabe, Bearbeiten, Ausschließen, Soft-Delete, Wiederherstellen, Teilen und Zusammenführen;
- unveränderliche Analyseläufe, deterministischer Offline-Provider und OpenAI-kompatibler Provideradapter mit Modellfreigaben und Usage-/Preiserfassung;
- Anforderungen, Revisionen, Budgets, Klärungspunkte, Relationen, Baselines, Kostenattribution und transitive nicht-destruktive What-if-/Impact-Analyse;
- Arbeitspakete, Abhängigkeiten, Firmen-Rate-Card → unabhängige Projektkopie, interne/externe Sätze, FTE-Kapazitäten, Arbeitskalender und Feiertage;
- Resource Leveling, PERT-Risikokennzahl, Vorwärts-/Rückwärtsrechnung, Float und kritischer Pfad;
- Sachpositionen, Angebotsvarianten und -umfang, proportionale Verrechnung, Risiko/Rabatt/MwSt., Zahlungsplan, Deckungsbeitrag und Budgetwirkung;
- Vier-Augen-Freigabe, unveränderliche Angebotssnapshots, frei strukturierbare Angebotspositionen/Textbausteine und veröffentlichte Artefakte;
- versionierte Abgabedokument-Vorlagen, DOCX-/XLSX-Export;
- persistente Jobs, Celery/Redis, SSE, Audit, Presence und Optimistic Locking;
- Alembic-Migrationen, synthetische Demo-/Fixtures, Backup/Restore, SBOM, Releaseprüfung und Port-Fallback.

Die Zuordnung der Spezifikationskapitel zu Quellcode und Nachweisen steht in `ACCEPTANCE_MATRIX.md`; die automatisierten fachlichen Tests stehen in `STORY_TEST_MATRIX.md`.

## In dieser Assembly-Umgebung verifiziert

- `python -m compileall`: **bestanden**.
- Backend-/Domain-/API-Tests: **11/11 bestanden**.
- Vollständiger API-Integrationsdurchstich: **bestanden** (Login/CSRF, Upload/Extraktion, Prüfschritt, Analyse/Aktivierung, Anforderungen, Locking, Impact, Planung, Angebot, Vier-Augen-Freigabe, Frozen DOCX, XLSX, Kundenportal und Plattform-Admin-Isolation).
- Frische Alembic-Migration: **bestanden**, Head `0002_offer_commercial_fields`, **52 Tabellen** inkl. `alembic_version` gezählt.
- YAML-/Compose-/Konfigurations-Parsing: **bestanden**.
- TypeScript-Syntaxtranspilation: **bestanden**.
- CycloneDX-SBOM-Erzeugung: **bestanden**.
- Deterministischer Planning/Pricing-Benchmark mit 500 Arbeitspaketen: **bestanden** (lokal deutlich unter dem 2-s-Rechenziel; dies ersetzt nicht den Referenzhardware-Benchmark).
- Port-Fallback-Resolver: **bestanden** für freie Standardports.

## Noch auszuführende Zielumgebungs-Gates

Diese Assembly-Umgebung hat keinen nutzbaren Docker-Daemon und keinen zuverlässigen Zugriff auf die npm/Python-Registries. Deshalb werden folgende Dinge ausdrücklich **nicht** als bereits ausgeführt behauptet:

1. transitive `apps/frontend/package-lock.json` via `npm` und `backend/uv.lock` auf Python 3.14 erzeugen/prüfen;
2. `npm ci`, vollständiger TypeScript-Typecheck und Vite-Produktionsbuild;
3. Playwright-Suite in Chromium/Chrome/Edge/Firefox/WebKit;
4. Build und Start des kompletten Docker-Compose-Stacks;
5. PostgreSQL-Backup → Restore in einer frischen Zielinstanz;
6. offizieller Performance-Benchmark auf der in der Spec definierten Referenzhardware;
7. Container-Tags zusätzlich zu Digests auflösen und diese für einen signierten Produktivrelease dokumentieren.

Dafür sind die ausführbaren Befehle im Repository enthalten:

```bash
./kusys locks
./kusys verify
./kusys up
cd apps/frontend && npm run test:e2e
PYTHONPATH=backend python ops/performance/benchmark.py
./kusys backup
./kusys restore <backup-directory>
```

Damit ist dies ein **source-complete KuSys-v1-Release-Kandidat**. „Produktionsabgenommen“ sollte er erst nach erfolgreichem Durchlauf der oben genannten Zielumgebungs-Gates genannt werden.
