# Story / acceptance coverage matrix

Normative Quelle ist `KuSys_Rebuild_Spec.md`. Die automatisierte Suite kombiniert fokussierte Domain-Tests mit zwei großen API-Integrationsszenarien; dadurch werden fachliche Invarianten separat und der gesamte kritische Durchstich gemeinsam geprüft.

| Bereich | Automatisierter Nachweis | Implementierung |
|---|---|---|
| Auth, Sessions, CSRF, Rollen | `test_us_00_ac_01_complete_upload_to_published_offer_flow` | `kusys/auth`, `tenancy` |
| Plattform-Admin ohne automatische Facheinsicht | gleicher Full-flow-Test | `auth/service.py`, `tenancy/api.py` |
| Dokumentupload/-extraktion | gleicher Full-flow-Test mit synthetischem DOCX | `documents` |
| Prüfschritt/Freigabegate | Full-flow + `test_us_00_ac_02_extended_v1_editing_surfaces` | `review` |
| Deterministischer Ersatzmodus | `test_US13_AC_06_deterministic_requirement_extraction` | `analysis/providers.py` |
| KI-Konfiguration/Secret-Verbergung | `test_us_00_ac_02_extended_v1_editing_surfaces` | `ai_config` |
| Requirement Budget/Revision/Locking | Full-flow-Test | `requirements`, `common/locking.py` |
| Gleichgewichtete Attribution/Rundung | `test_US14_AC_08_equal_attribution_and_rounding` | `pricing/engine.py` |
| Gewichtete Attribution | `test_US14_AC_08_weighted_attribution` | `pricing/engine.py` |
| Transitive What-if-Analyse | `test_US14_AC_10_requirement_removal_is_non_destructive_and_transitive` + Full-flow | `analysis/impact.py` |
| Resource Leveling/FTE | zwei `test_US15_AC_03_*` | `planning/engine.py` |
| Kalender/Feiertage | `test_US15_AC_05_calendar_skips_weekends_and_holidays` + API-Integrationsfall | `planning`, `calendars` |
| CPM/kritischer Pfad | `test_US15_AC_06_dependency_and_critical_path` | `planning/engine.py` |
| Zyklenerkennung | `test_US15_AC_07_cycle_is_rejected` | `planning/engine.py`, `planning/api.py` |
| Sachpositionen | `test_us_00_ac_02_extended_v1_editing_surfaces` | `commercial` |
| Angebot/Kalkulation/Four-eyes/Immutabilität | Full-flow-Test | `offers`, `pricing` |
| DOCX/XLSX-Export | Full-flow-Test prüft OOXML-Ausgabe | `offers/export.py` |
| Kundenportal | Full-flow: published-only Download + Klärungsantwort | `portal`, `artifacts` |
| Jobs | Full-flow: Upload-/Analysejob | `jobs` |
| Alembic Fresh Upgrade | Releaseprüfung auf leerer DB | `backend/migrations` |
| Browserjourneys | `apps/frontend/e2e/full-flow.spec.ts` | React + Playwright; Zielhost-Ausführung erforderlich |
| Backup/Restore | ausführbare Validierungs-/Restore-Skripte | `ops/backup`, `ops/restore`; Zielhost-Ausführung erforderlich |
| SBOM/Release | `./kusys verify` | `ops/release`, `SBOM.cdx.json` |

Die vollständige Zuordnung aller Spezifikationskapitel ist zusätzlich in `ACCEPTANCE_MATRIX.md` dokumentiert. Zielumgebungs-Gates werden in `IMPLEMENTATION_STATUS.md` getrennt von tatsächlich ausgeführten Nachweisen geführt.
