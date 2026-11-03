# KuSys Rebuild Specification

**Status:** Normative Wiederherstellungs- und Implementierungsspezifikation  
**Stand:** 2026-09-24  
**Zweck:** Diese Spezifikation beschreibt KuSys so vollständig, dass die Anwendung in einer neuen Entwicklungs-, Test- oder lokalen Produktivumgebung reproduzierbar neu aufgebaut werden kann.

> Normative Begriffe: **MUSS** = verbindlich, **SOLL** = Standard/empfohlene Umsetzung mit begründbarer Abweichung, **KANN** = optionale Erweiterung.

---

## 1. Produktziel

KuSys unterstützt Anbieter aus Anlagen- und Systembau entlang der Kette:

**Kundendokument → Prüfschritt → Anforderungen → Arbeitspakete → Terminplan → Angebot**

Die Anwendung verarbeitet deutsch- und englischsprachige Kundendokumente, erzeugt fachlich nachvollziehbare Anforderungen und Arbeitspakete, plant diese terminlich und kalkuliert daraus versionierte, freigabefähige Angebote inklusive DOCX- und Excel-Ausgabe.

Die Oberfläche ist deutsch. Angebote können deutsch oder englisch erzeugt werden.

---

## 2. Reproduzierbarkeitsziel

Ein Neuaufbau MUSS aus folgenden Artefakten möglich sein:

1. diesem Dokument,
2. `kusys-environment.yaml`,
3. Quellcode-Repository,
4. Lockfiles für Frontend und Backend,
5. Datenbankmigrationen,
6. Docker-/Compose-Dateien,
7. kommentierter Konfigurationsvorlage,
8. synthetischen Testfixtures,
9. Backup-/Restore-Skripten,
10. automatisierten Tests.

Eine Umgebung gilt als reproduziert, wenn:

- alle Container/Prozesse starten,
- Datenbankmigrationen erfolgreich laufen,
- die Demo-Daten geladen werden können,
- Upload → Prüfschritt → Ersatzanalyse → Arbeitspakete → Terminplan → Angebot → DOCX funktioniert,
- sämtliche Muss-Akzeptanztests erfolgreich sind,
- ein Backup erstellt und wiederhergestellt werden kann.

---

## 3. Zielumgebungen

### 3.1 Lokale Produktiv-/Pilotinstallation

- Betrieb auf lokalem Server oder leistungsfähigem Arbeitsplatz.
- Start der gesamten Anwendung mit einem Befehl via Docker Compose.
- Kein Cloudbetrieb erforderlich.
- Internetzugang nur für externe KI-/OCR-Anbieter nötig; lokaler Ersatzmodus MUSS offline funktionieren.

### 3.2 Entwicklung

- Windows 11, macOS und aktuelles Ubuntu/Linux.
- Frontend und Backend lokal ohne Docker startbar.
- PostgreSQL darf lokal oder per Container laufen.

### 3.3 Test/CI

- vollständig automatisierbar,
- temporäre PostgreSQL-Datenbank,
- keine echten KI-Anbieter notwendig,
- OCR und KI vollständig mockbar,
- synthetische Kundendokumente.

---

## 4. Verbindlicher Technologie-Stack

### 4.1 Frontend

- React **19.3.0**
- TypeScript
- Vite
- React Router
- TanStack Query
- TanStack Table
- MUI
- TipTap für Rich Text
- dnd-kit für Vorlagen-/Bausteinsortierung

### 4.2 Backend

- Python **3.14.7**
- FastAPI **0.140.3**
- Pydantic 2.x, exakt per Lockfile pinnen
- SQLAlchemy **2.0.54**
- Alembic **1.20.0**

### 4.3 Datenbank und Infrastruktur

- PostgreSQL **18.x**; für Images auf einen konkreten Patchstand pinnen
- Redis Open Source **8.10.x**; konkreten Patchstand im Compose-Image pinnen
- Celery **5.7.x**; konkreten Patchstand im Python-Lockfile pinnen

### 4.4 Dokumente

- PDF: PyMuPDF + pdfplumber
- DOCX lesen/schreiben: python-docx
- Excel: openpyxl
- OCR lokal: OCRmyPDF + Tesseract
- DOCX-Vorlagen: eigene Template-Abstraktion oberhalb python-docx

### 4.5 KI

- eigene `AIProvider`-Abstraktion
- CrewAI als optionale Orchestrierungsschicht
- direkter Provideradapter möglich
- regelbasierter Ersatzmodus ist unabhängig von CrewAI und MUSS immer funktionieren

### 4.6 Architekturform

KuSys wird als **modularer Monolith** umgesetzt.

Getrennte Prozesse:

- Frontend
- Backend/API
- Worker
- Scheduler
- PostgreSQL
- Redis

Backend und Worker teilen dieselbe Domänen- und Anwendungscodebasis.

---

## 5. Repository-Struktur

Empfohlene verbindliche Zielstruktur:

```text
kusys/
├── apps/
│   ├── frontend/
│   └── backend/
├── packages/
│   ├── api-contracts/
│   └── shared-types/
├── backend/
│   ├── kusys/
│   │   ├── auth/
│   │   ├── tenancy/
│   │   ├── projects/
│   │   ├── documents/
│   │   ├── review/
│   │   ├── analysis/
│   │   ├── requirements/
│   │   ├── planning/
│   │   ├── pricing/
│   │   ├── offers/
│   │   ├── templates/
│   │   ├── artifacts/
│   │   ├── audit/
│   │   └── common/
│   ├── migrations/
│   └── tests/
├── fixtures/
│   ├── documents/
│   └── demo-data/
├── ops/
│   ├── docker/
│   ├── backup/
│   ├── restore/
│   └── health/
├── config/
│   ├── kusys.example.yaml
│   └── model-catalog.example.yaml
├── docker-compose.yml
├── docker-compose.dev.yml
├── kusys-environment.yaml
├── README.md
└── Makefile or cross-platform task runner
```

---

## 6. Konfigurationsmodell

### 6.1 Format

Primäres Format: YAML.

Priorität:

1. sichere Systemdefaults,
2. YAML-Konfiguration,
3. Umgebungsvariablen,
4. firmenweite DB-Einstellungen,
5. Projekteinstellungen,
6. angebots-/laufbezogene Einstellungen.

Spezifischere Ebene gewinnt.

### 6.2 Secrets

Secrets werden NICHT in YAML eingecheckt.

Mindestens:

- DB-Passwort
- Master-Key für Secret-Verschlüsselung
- KI-API-Schlüssel
- externe OCR-Schlüssel

werden über Umgebungsvariablen oder Secret-Dateien eingebunden.

### 6.3 Zeitzonen

- technische Timestamps: UTC
- Firmenzeitzone als IANA-Zeitzone
- Vorgabe: `Europe/Berlin`
- Geschäftsdaten ohne Uhrzeit als lokale Kalenderdaten speichern

---

## 7. Mandanten- und Rollenmodell

KuSys ist mandantenfähig.

### 7.1 Rollen

1. **Plattform-Admin** – technischer Betreiber; kein automatischer fachlicher Firmenzugriff.
2. **Firmen-Admin** – vollständiger Zugriff innerhalb einer Firma.
3. **Projektleiter** – vollständiger Zugriff auf zugeordnete Projekte inklusive Kosten.
4. **Projektmitarbeiter** – vollständiger Zugriff auf zugeordnete Projekte inklusive Kosten.
5. **Kunde** – externer Teilnehmer; nur ausdrücklich veröffentlichte Inhalte.

Projektleiter und Projektmitarbeiter unterscheiden sich hauptsächlich bei Verantwortung/Freigaben, nicht bei Kostensicht.

### 7.2 Plattform-Admin-Zugriff

Der Plattform-Admin MUSS für fachlichen Zugriff auf Firma A eine ausdrückliche, zeitlich begrenzte Freigabe durch einen Firmen-Admin erhalten.

Eine Freigabe speichert:

- Firma
- Anfragender
- Freigebender
- Grund
- Zeitraum
- Status
- Audit-Ereignisse

### 7.3 Projektteams

- Projekte besitzen eigene Teams.
- Benutzer können je Projekt unterschiedliche Projektrollen haben.
- Projektzugriff erfolgt über Mitgliedschaften.

### 7.4 Kundenportal

Als Soll-Ausbaustufe:

- veröffentlichte Dokumentversionen ansehen,
- neue Fassungen hochladen,
- Kommentare/Änderungsvorschläge,
- Klärungspunkte beantworten,
- freigegebene Angebotsdokumente herunterladen.

Der Kunde darf keine internen Stammstände direkt verändern.

---

## 8. Projekt- und Stammdaten

### 8.1 Firma

- Firmenname
- Anschrift
- Land
- E-Mail
- Telefon
- Ansprechpartner
- USt-IdNr.
- Standardwährung
- Standardsprache
- Zeitzone
- Nummernkreise

### 8.2 Kunde

- Firmenname
- Kundennummer
- Anschrift
- Land
- Ansprechpartner
- Abteilung
- E-Mail
- Telefon

### 8.3 Projekt

- interne UUID
- Projektnummer
- Projektname
- Kurzbeschreibung
- Kunde
- Kundenansprechpartner
- interner Projektverantwortlicher
- Projektteam
- Status
- Vertraulichkeitskennzeichen
- Dokument-/Angebotssprache
- geplanter Projektstart
- Erstell-/Änderungszeitpunkte

### 8.4 Angebot

- Angebotsnummer
- Variante
- Version
- Angebotsdatum
- Empfänger
- Kundenreferenz
- internes Aktenzeichen
- Gültigkeit
- Sprache
- Währung
- Status
- Ersteller/Freigeber/Versanddaten

### 8.5 Währung und Rundung

- ausschließlich EUR in v1
- Geld: 2 Dezimalstellen
- Stunden: ganze Stunden
- Geld immer mit Dezimalarithmetik, keine binären Floats

---

## 9. Datenhaltung und Versionierung

### 9.1 Grundprinzip

Fachliche Objekte besitzen:

- interne UUID,
- sichtbaren fachlichen Schlüssel soweit relevant,
- fachliche Revision,
- technischen `lock_version`-Zähler,
- `created_at`, `updated_at`, `created_by`,
- optional `deleted_at`, `deleted_by`, `delete_reason`.

### 9.2 Soft Delete

Normale fachliche Löschungen sind Soft Deletes.

Betroffen u. a.:

- Projekte
- Anforderungen
- Abschnitte

Soft-gelöschte Daten:

- verschwinden aus normalen Listen,
- bleiben historisch/auditierbar,
- können mit Berechtigung wiederhergestellt werden,
- werden nicht erneut nummeriert.

### 9.3 Unveränderliche Stände

Unveränderlich nach Abschluss/Freigabe:

- abgeschlossene Analyseläufe
- Baselines
- freigegebene Angebotsversionen
- versendete DOCX-Artefakte
- Snapshots der verwendeten Rate-Card und Vorlagen

---

## 10. Kern-Datenmodell

Mindestens folgende Aggregate/Tabellen:

```text
Tenant
User
TenantMembership
PlatformAccessRequest
PlatformAccessGrant
Customer
Project
ProjectMembership
Document
DocumentVersion
ExtractedBlock
ReviewRevision
Section
SectionRevision
AnalysisRun
AnalysisStep
Requirement
RequirementRevision
RequirementRelation
RequirementCostAttribution
ClarificationItem
ClarificationRevision
WorkPackage
WorkPackageRevision
WorkPackageDependency
RateCard
RateCardRole
WorkCalendar
Holiday
Baseline
BaselineRequirement
Offer
OfferVersion
OfferScopeItem
OfferPosition
MaterialItem
OfferTextBlock
OfferSnapshot
DocumentTemplate
DocumentTemplateVersion
PublishedArtifact
FileArtifact
AIProviderConfig
AIModelPrice
AIUsageEvent
Job
Session
LoginEvent
PresenceSession
AuditEvent
```

Mandantenbezogene Daten tragen zwingend `tenant_id`.

---

## 11. Dokumenteingang

### 11.1 Formate und Grenzen

- PDF, DOCX, PNG
- max. 200 MB pro Datei
- max. 500 Seiten pro PDF/DOCX
- max. 25.000 × 25.000 Pixel pro PNG
- firmenweit konfigurierbar

### 11.2 Dateiprüfung

Prüfen:

- Endung
- MIME-Typ
- Dateisignatur
- Lesbarkeit
- erlaubtes Format
- optional lokaler Virenscanner

Passwortgeschützte PDF/DOCX werden abgelehnt.

### 11.3 Mehrere Dokumente und Versionen

- Projekt darf mehrere logische Dokumente besitzen.
- Jedes Dokument besitzt eigene Versionskette.
- Ein Analyselauf verwendet mehrere Dokumente, aber höchstens eine ausgewählte Version je logischem Dokument.
- Auswahl wird unveränderlich am Analyselauf gespeichert.

### 11.4 Fundstellen

PDF:

- Dokumentversion
- Seite
- Blockposition/Koordinaten

DOCX:

- Dokumentversion
- Gliederungspfad
- Blocktyp
- Blocknummer
- Absatz-/Listenindex
- bei Tabellen: Tabellen-/Zeilen-/Zellposition
- Originaltextauszug + Prüfsumme

Gerenderte DOCX-Seitenzahl darf angezeigt werden, ist aber nicht normative Referenz.

PNG = eine Seite.

### 11.5 Tabellen

Speichern:

- Originalstruktur inkl. verbundener Zellen
- normalisierte Zeilenrepräsentation
- Zellpositionen
- Kopfzeilenbezug

### 11.6 OCR

- DOCX: nie OCR
- PNG: immer OCR
- PDF: jede Seite prüfen; Standardgrenze 120 sichtbare Zeichen
- hat mindestens eine Seite zu wenig Text: gesamtes PDF technisch durch OCR
- Auswahl der finalen Textquelle erfolgt je Seite anhand Qualität
- bestehende Textebene und OCR-Ergebnis bleiben intern erhalten

Qualitätsstatus je Seite:

- gut
- prüfen
- unzureichend

Lokale OCR ist Grundvoraussetzung. Externe OCR standardmäßig deaktiviert.

---

## 12. Prüfschritt

### 12.1 Abschnittsarten

- Überschrift
- Absatz
- Listenpunkt
- Tabellenzeile

### 12.2 Textebenen

Je Abschnitt:

1. unveränderlicher Quelltext
2. normalisierter Text
3. bearbeiteter Text

### 12.3 Kategorien

- Anforderung
- Kontext

Manuelle Entscheidung hat Vorrang.

Automatische Regelpriorität:

1. manuelle Entscheidung
2. Überschrift → Kontext
3. eindeutige Ist-Beschreibung → Kontext
4. Kontextkapitel → Kontext
5. Anforderungsformulierung/Modalverb → Anforderung
6. sonst Kontext

Gemischte Absätze werden möglichst in atomare Fragmente geteilt. Bei Unsicherheit als Anforderung + Prüfhinweis.

### 12.4 Streichen vs. Löschen

**Streichen:** sichtbar, ausgeschlossen, wieder einschließbar.  
**Löschen:** Soft Delete, im Papierkorb, wiederherstellbar.

### 12.5 Neu aufbauen

Erzeugt neue aktive Prüfschrittrevision aus unverändertem Extraktionsstand.

Zurückgesetzt werden quellbezogene manuelle Bearbeitungen; alte Revision bleibt historisch lesbar.

Manuelle Abschnitte standardmäßig behalten.

### 12.6 Freigabe

Analyse nur auf freigegebener Prüfschrittrevision.

Folgende Änderungen heben Freigabe auf:

- Text
- Kategorie
- Streichen/Wiedereinschließen
- Löschen/Wiederherstellen
- Ergänzen
- Teilen/Zusammenführen
- Abschnittsart/Überschriftenebene
- Reihenfolge
- Textquelle/OCR
- Sprache mit Kategorisierungsauswirkung
- Dokumentversionsauswahl
- Neuaufbau

---

## 13. KI-/Analyse-Workflow

### 13.1 Agenten

Agent 1 – Requirements Engineer:

- nur freigegebene Anforderungsabschnitte
- atomare Anforderungen
- deutsch: `Das System soll ...`
- englisch: `The system shall ...`
- Priorität strukturiert: muss/soll/kann
- mindestens eine Fundstelle

Agent 2 – Projektplaner:

- Arbeitspakete
- Name/Beschreibung
- Rolle
- Aufwand
- Anforderungen
- Abhängigkeiten
- Phase
- übergreifend-Kennzeichen

### 13.2 Feste Schemas

Schemas sind versioniert im Code und nicht frei durch Admins editierbar.

Jeder Lauf speichert verwendete Schemaversion.

### 13.3 Analyseläufe

- niemals überschreiben
- jeder Lauf unveränderlich
- Ergebnisse zunächst in isoliertem Arbeitsbereich
- erst nach allen Gates als aktiver Stand aktivierbar
- bei geänderter Eingabe während des Laufs Ergebnis als veraltet kennzeichnen

### 13.4 Atomarität

Fehler in späterem Schritt aktiviert keine Teilergebnisse.

Teilergebnisse dürfen zur Diagnose im Lauf erhalten bleiben.

### 13.5 Textgrenze

Standard 60.000 Zeichen.

Bei Überschreitung:

- niemals abschneiden
- entlang Dokument/Kapitel/Abschnitt chunking
- Ergebnisse global zusammenführen und deduplizieren

### 13.6 Ersatzmodus

MUSS deterministisch ohne API-Schlüssel funktionieren.

- Anforderungen aus normativen Sätzen
- Priorität regelbasiert
- Klärungspunkte aus TBD/unklar/etc.
- standardmäßig ein Arbeitspaket je Anforderung
- Rollen über konfigurierbare Begriffsmatrix
- Aufwand über Größenmatrix

### 13.7 Anbieter/Modelle

Konfigurationsebenen:

1. Firmenstandard
2. Projektstandard
3. optional je Agent

`auto` wird über lokalen versionierten Modellkatalog auf exakte Modell-ID aufgelöst und am Lauf gespeichert.

### 13.8 Kosten

- Kostenanzeige in EUR
- Anbieterwährung + Umrechnungskurs speichern
- alle tatsächlich entstandenen Gebühren zählen, auch Fehler/Abbruch/Retry
- Projektleiter und Projektmitarbeiter dürfen Kosten sehen
- Firmen-Admin darf Limits und Freigaben definieren

### 13.9 Vertraulichkeit

Für vertrauliche Projekte nur freigegebene Bereitstellungsprofile.

Profil enthält:

- Anbieter
- Endpoint
- Region
- Deployment/Konto
- erlaubte Modelle
- Verarbeitungskennzeichen

Optionales Redacting für Namen, E-Mails, Telefone, Anschriften und projektspezifische Begriffe.

Placeholder-Mapping verschlüsselt speichern.

---

## 14. Anforderungen und Klärungsliste

### 14.1 Schlüssel

- projektweit fortlaufend `REQ-0001` etc.
- immer höchste Nummer + 1
- keine Wiederverwendung

### 14.2 Manuelle Anforderungen

Bleiben bei Neuanalyse erhalten.

### 14.3 Teilen

Ursprung bleibt historisch als `abgelöst durch Teilung`.

Neue Anforderungen erhalten neue Schlüssel und verweisen auf Ursprung.

Arbeitspaketbezüge werden angeboten, nie still übernommen.

### 14.4 Löschen

Soft Delete mit Pflicht-Löschgrund und Impact-Vorschau.

Freigegebene/versendete Angebote bleiben unverändert.

### 14.5 Klärungspunkte

Herkunft:

- automatisch
- manuell
- Kunde

Status:

- offen
- beantwortet
- erledigt
- durch neuen Analysestand überholt

Mehrere Anforderungen/Fundstellen pro Punkt zulässig.

Kundenantwort → zunächst `beantwortet – interne Prüfung ausstehend`.

### 14.6 Versionierung und Baselines

Fachliche Revision und technischer Lock-Zähler getrennt.

Baseline enthält unveränderlich:

- alle aktiven Anforderungen
- exakte Revisionen
- Schlüssel/Titel/Text/Priorität
- Fundstellen
- Dokumentversionsbezüge
- Ablöse-/Teilungsbeziehungen
- Herkunft
- Name/Datum/Ersteller
- Gesamtprüfsumme

Angebot darf nur auf eingefrorenem Anforderungsstand versendet werden.

### 14.7 Budget je Anforderung

Jede Anforderung KANN ein eigenes kaufmännisches Budget bzw. einen Zielwert in EUR erhalten.

Gespeichert werden mindestens:

- `budget_eur` optional
- optionaler maximal akzeptierter Preis
- Quelle des Budgets (manuell, Kunde, Import)
- Ersteller/Änderer und Zeitpunkt
- fachliche Revision der Anforderung, für die das Budget gilt

Budget und berechneter Verkaufspreis sind strikt getrennte Begriffe:

- **Budget** = wirtschaftlicher Ziel-/Grenzwert der Anforderung
- **zugeordneter Verkaufspreis** = kalkulatorischer Anteil des aktuellen Angebots, der dieser Anforderung zugerechnet wird

KuSys zeigt daraus mindestens:

- zugeordnete Selbstkosten
- zugeordneten Verkaufspreis
- Deckungsbeitrag
- Budgetabweichung absolut und in Prozent
- verbleibenden Budgetspielraum bzw. Budgetüberschreitung

Beispiel:

```text
REQ-0042 – Fernwartungszugang
Budget:                    18.000,00 €
Zugeordnete Selbstkosten:   8.400,00 €
Zugeordneter Verkauf:      13.200,00 €
Deckungsbeitrag:            4.800,00 €
Budgetspielraum:            4.800,00 €
```

### 14.8 Kaufmännische Attribution je Anforderung

KuSys MUSS Kosten und Verkaufspreise nachvollziehbar auf Anforderungen attribuieren können.

Grundlage sind:

- verknüpfte Arbeitspakete
- verknüpfte Sachpositionen
- deren Skalierungsart
- deren Umfangsanteil
- übergreifende Pakete gemäß globalem Angebotsumfang

Bei einem Arbeitspaket mit mehreren Anforderungen wird der Paketwert standardmäßig gleichgewichtet auf die aktiven verknüpften Anforderungen verteilt, sofern keine explizite Gewichtung gepflegt ist.

Optional KANN je Beziehung zwischen Arbeitspaket und Anforderung ein Gewicht hinterlegt werden. Dann gilt die proportionale Verteilung gemäß Gewichtssumme.

Die Summe der attribuierten Anforderungswerte MUSS mit den entsprechenden kalkulierten Gesamtwerten des Angebots konsistent sein. Rundungsdifferenzen werden deterministisch der betragsmäßig größten betroffenen Anforderung zugeschlagen.

### 14.9 Beziehungen zwischen Anforderungen

Anforderungen können gerichtete und klassifizierte Beziehungen untereinander besitzen. Mindestens folgende Beziehungstypen werden unterstützt:

- `requires` – benötigt
- `required_by` – wird benötigt von (inverse Darstellung von `requires`)
- `enables` – ermöglicht/bedingt
- `conflicts_with` – steht im Konflikt mit
- `related_to` – fachlich verwandt
- `replaces` / `replaced_by` – ersetzt / wird ersetzt durch
- `split_from` / `split_into` – aus Teilung entstanden / geteilt in

Gespeichert werden:

- Quellanforderung
- Zielanforderung
- Beziehungstyp
- optionale Begründung
- Herkunft (manuell, KI, Import)
- Ersteller/Agent und Zeitpunkt
- Status aktiv/inaktiv

Die KI DARF Beziehungen vorschlagen. Automatisch vorgeschlagene Abhängigkeiten müssen als solche erkennbar und manuell änderbar sein.

### 14.10 Impact- und What-if-Analyse

Vor dem Abwählen, Soft-Löschen oder wesentlichen Ändern einer Anforderung berechnet KuSys direkte und indirekte Auswirkungen.

Die Analyse umfasst mindestens:

- direkt abhängige Anforderungen
- transitiv/indirekt abhängige Anforderungen
- Konflikte
- betroffene Arbeitspakete
- betroffene Sachpositionen
- Stundenänderung
- Terminplanänderung
- kritischer-Pfad-Auswirkung
- Selbstkostenänderung
- Verkaufspreisänderung
- Deckungsbeitragsänderung
- Budgetabweichung
- betroffene Angebotsvarianten

Beispiel:

```text
Entfall REQ-0017
Direkt betroffen: REQ-0042
Indirekt betroffen: REQ-0061, REQ-0074
Betroffene Arbeitspakete: AP-021, AP-024, AP-028
Stundenwirkung: -96 h
Preiswirkung: -21.400,00 €
Terminwirkung: -6 Arbeitstage
```

Die What-if-Berechnung verändert den gespeicherten Datenstand NICHT. Erst eine bestätigte Aktion übernimmt die Änderung.

---

## 15. Arbeitspakete, Aufwand und Planung

### 15.1 Aufwand

Je Paket:

- minimal
- wahrscheinlich
- maximal
- ganze Stunden
- `0 ≤ min ≤ wahrscheinlich ≤ max`

Nullstunden-Pakete als Meilensteine zulässig.

Erwartungswert:

`(min + 4 × wahrscheinlich + max) / 6`

Streuung:

`(max - min) / 6`

### 15.2 Risiko

Vorschlag je Angebot:

`(Σ Erwartungswerte + Σ Streuungen) / Σ Planwerte - 1`

- auf ganze Prozent runden
- mindestens 0 %
- bei 0 Planstunden: Vorschlag 0 %, Status nicht berechenbar
- Statistik nur auf Arbeitsaufwand
- angewandter Zuschlag wirkt auf Arbeit + Sachpositionen

### 15.3 Resource Leveling

ECHTES Resource Leveling.

Rolle besitzt verfügbare FTE. Paket besitzt `maximal nutzbare FTE`, Vorgabe 1,0.

Paketdauer:

`Aufwand / (Stunden pro Tag × tatsächlich nutzbare FTE)`

auf ganze Arbeitstage aufrunden, mindestens 1 Tag bei Aufwand > 0.

### 15.4 Planungspriorität

1–5, Vorgabe 3.

Reihenfolge bei Konkurrenz:

1. Abhängigkeiten
2. kritischer Pfad
3. Planungspriorität
4. fachliche Reihenfolge
5. stabile Paket-ID

### 15.5 Kalender

- echter Wochenkalender
- Feiertage
- Betriebsferien
- projektspezifische Sperrtage

Nichtarbeitstag → nächster Arbeitstag.

### 15.6 Kritischer Pfad

Vorwärts-/Rückwärtsrechnung.

Alle Pakete mit Gesamtpuffer 0 sind kritisch; mehrere kritische Pfade möglich.

### 15.7 Zyklen

- erkennen
- temporäre Kante für Planvorschau ignorieren
- niemals automatisch dauerhaft löschen
- fachliche Korrektur vor finaler Freigabe erforderlich

### 15.8 Phasen

- Konzept
- Spezifikation
- Realisierung
- Integration
- Abnahme
- Übergreifend

Phasen sind Gruppierung, keine versteckten Zwangsabhängigkeiten.

### 15.9 Masterplan und Angebotsplan

- ein Master-Projektplan
- je Angebotsvariante abgeleitete Terminansicht
- anteiliger Aufwand reduziert im Angebotsplan auch Dauer
- Paket kann `proportional` oder `vollständig bei Verwendung` sein

### 15.10 Gantt

- Tag/Woche/Monat/Quartal
- Filter Rolle/Phase/kritisch
- Abhängigkeiten
- Meilensteine
- Kapazitätskonflikte
- Master/Angebotsplan-Vergleich
- kein freies Drag&Drop zur Umgehung der Planung

---

## 16. Rate-Card

Je Rolle:

- stabile UUID
- eindeutiger Name
- Aliasse
- Art intern/extern
- Kapazität FTE

Intern:

- interner Kostensatz
- Verkaufssatz

Extern:

- Einkaufssatz
- Aufschlag
- Verkaufssatz

Deckungsbeitrag intern:

`Verkaufswert - interne Kosten`

Deckungsbeitragsquote:

`DB / Verkaufswert × 100`

Projekt-Rate-Card wird bei Projektanlage aus Firmenvorlage kopiert und danach unabhängig.

Vorlage neu laden nur mit Diff und manueller Entscheidung bei verwendeten Rollen.

Freigegebene Angebote werden durch Rate-Card-Änderungen niemals geändert.

---

## 17. Angebote

### 17.1 Varianten

- mehrere Varianten je Projekt
- genau eine primär
- neue Variante leer oder als Kopie; Standard Kopie

### 17.2 Umfang

Je Anforderung enthalten/nicht enthalten.

Schnellauswahl:

- alle
- nur Muss
- Muss + Soll
- keine

### 17.3 Anteilige Verrechnung

Für proportionale Pakete:

`gewählte verknüpfte Anforderungen / alle aktiven verknüpften Anforderungen`

Anteilstunden kaufmännisch auf ganze Stunden; positiver Anteil mindestens 1 h.

Sachpositionen dürfen mehrere Anforderungen referenzieren und folgen derselben Logik.

### 17.4 Kundensicht der Positionen

Extern bevorzugt Leistungsblöcke statt interner Arbeitspakete.

Vorlage kann steuern, ob Stunden/Stundensätze sichtbar sind. Standard: nur Beschreibung + Positionspreis.

### 17.5 Summen

Ausschließlich serverseitig autoritativ.

Rechenweg:

`Netto → + Risiko → - Rabatt → Zwischensumme → + MwSt. → Brutto`

Geldwerte: 2 Dezimalstellen.

### 17.6 Zahlungsplan

angebotsspezifisch.

Default:

- Konzept 10 %
- Spezifikation 15 %
- Realisierung 45 %
- Integration 20 %
- Abnahme 10 %

Summe exakt 100 %.

Basis: netto nach Risiko und Rabatt, vor MwSt.

### 17.7 Status

`Entwurf → zur Freigabe → freigegeben → versendet → angenommen|abgelehnt`

`zur Freigabe → Entwurf` mit Pflichtkommentar.

Vier-Augen-Prinzip standardmäßig aktiv.

Ab `freigegeben` unveränderlich; Änderungen nur neue Version als Entwurf.

### 17.8 Unveränderlicher Snapshot

Bei Freigabe einfrieren:

- Kopf-/Kundendaten
- Baseline
- Umfang
- Anforderungsrevisionen
- Arbeitspakete
- Rate-Card
- Kosten/Verkauf
- Sachpositionen
- Risiko/Rabatt/MwSt.
- Summen
- Zahlungsplan
- Terminplan
- Texte
- Vorlage/Logo/Header/Footer
- Übersetzungen
- DOCX
- Prüfsumme

### 17.9 Preiswirkung je Anforderung

Für jede Angebotsvariante zeigt KuSys die kaufmännische Wirkung einzelner Anforderungen.

Je Anforderung werden mindestens ausgewiesen:

- Budget/Zielwert, sofern vorhanden
- attribuierte Selbstkosten
- attribuierter Verkaufspreis
- Deckungsbeitrag
- Budgetabweichung
- Preiswirkung bei Entfall

Die Funktion "Umfang ändern" zeigt vor dem Speichern zusätzlich je hinzugefügter oder entfernter Anforderung:

- Stunden vorher/nachher
- Netto vorher/nachher
- Brutto vorher/nachher
- Differenz
- Terminwirkung
- Folgeauswirkungen auf abhängige Anforderungen

Bei gemeinsam genutzten Arbeitspaketen oder Sachpositionen darf nicht deren voller Wert als Entfallwirkung angesetzt werden. Es ist ausschließlich der tatsächlich wegfallende kalkulatorische Anteil anzusetzen.

### 17.10 Budgetbasierte Angebotsanalyse

KuSys zeigt je Angebotsvariante aggregiert:

- Summe aller gepflegten Anforderungsbudgets
- Summe attribuierter Verkaufspreise für budgetierte Anforderungen
- Gesamtbudgetabweichung
- Anforderungen über Budget
- Anforderungen mit verbleibendem Budgetspielraum

Diese Sicht dient der Angebotsoptimierung und verändert die autoritative serverseitige Kalkulation nicht.

---

## 18. Frei konfigurierbare Abgabedokumente

Je Firma mehrere versionierte Vorlagen.

Konfigurierbar:

- Logo
- Absenderadresse
- Seitenformat/Ränder
- Schriftarten/Farben
- Header/Footer
- erste Seite/Folgeseiten separat
- Rich-Text-Bausteine
- Systembausteine
- Platzhalter
- Deutsch/Englisch
- Wasserzeichen
- Bedingungen für Sichtbarkeit
- optional eigene DOCX-Mastervorlage

Vorlagenstatus:

- Entwurf
- veröffentlicht
- archiviert

Veröffentlichte Vorlagenversionen werden nicht direkt verändert.

Angebot speichert konkrete Vorlagenversion.

Makros, ausführbarer Code und aktive externe Inhalte sind nicht zulässig.

Unbekannte Pflichtplatzhalter oder fehlende Pflichtübersetzungen blockieren Freigabe.

---

## 19. Excel-Export

Projekt-Workbook mit mindestens:

- Zusammenfassung
- Anforderungen
- Arbeitspakete
- Terminplan
- Klärungsliste
- je Angebot eigenes Kalkulationsblatt
- Rollen-/Kostenübersicht intern
- Sachpositionen

Varianten:

- extern: nur Verkaufswerte
- intern: zusätzlich Einkauf/Kosten/Aufschlag/Deckungsbeitrag

Excel enthält echte Formeln, wo sinnvoll; serverseitiger Wert bleibt autoritativ.

Export Deutsch oder Englisch.

---

## 20. Authentifizierung und Sicherheit

### 20.1 Benutzername

- installationsweit eindeutig
- case-insensitive
- 3–80 Zeichen
- Buchstaben/Ziffern/`. - _`

### 20.2 Passwörter

- mindestens 12 Zeichen
- max. 128
- mindestens Buchstabe + Zahl
- Argon2id bevorzugt; bcrypt Fallback
- nie Klartext speichern

### 20.3 Sessions

- serverseitige Session
- HttpOnly Cookie
- SameSite=Lax
- Secure in produktionsnahem Betrieb
- Inaktivitätslimit 480 Minuten
- absolutes Limit 24 h
- mehrere parallele Sessions zulässig

### 20.4 Login-Schutz

- 5 Fehlversuche → 300 s Sperre als Grundwert
- zusätzliche IP-/Username-Drosselung
- keine dauerhafte Sperre
- Login-Audit 180 Tage

### 20.5 CSRF

Alle Cookie-authentifizierten schreibenden Requests brauchen CSRF-Schutz.

### 20.6 Secret-Verschlüsselung

API-Schlüssel verschlüsseln.

Master-Key außerhalb DB und Repository, via Env oder Secret-Datei.

### 20.7 Datei-Zugriff

Originale und Exporte nur über autorisierte Endpunkte ausliefern; keine frei erreichbaren statischen Pfade.

### 20.8 Logs

Technische Logs enthalten niemals:

- Kundentext
- Passwörter
- API-Schlüssel
- Redaktions-Mappings

Nur IDs, Error Codes, Correlation IDs.

---

## 21. Optimistic Locking und Mehrbenutzerbetrieb

Bearbeitbare Entitäten tragen `lock_version`.

Client sendet `expected_version`.

Bei Konflikt:

- HTTP 409
- eigener Stand
- aktueller Serverstand
- geänderte Felder
- letzter Bearbeiter/Zeitpunkt

Konfliktdaten werden rollenbezogen gefiltert.

Bulk-Aktionen sind atomar: ein Konflikt → ganze Operation abbrechen.

Projektanwesenheit via Heartbeat:

- alle 30 s
- nach 90 s inaktiv

Anzeige:

- Name
- Projektrolle
- geöffneter Bereich
- Aktivstatus

---

## 22. Hintergrundjobs

Lange Vorgänge:

- OCR
- Analyse
- Exporte
- große Neuberechnungen

laufen als persistente Jobs.

Anforderungen:

- Browser schließen überstehen
- Backend-/Worker-Neustart überstehen
- Job-ID persistent
- idempotente Schritte
- Zustände mindestens: queued/running/succeeded/failed/cancel_requested/cancelled/unknown
- Ergebnisse niemals doppelt aktivieren

Fortschritt über SSE.

Projektanwesenheit kann WebSocket verwenden.

---

## 23. API-Struktur

Basis: `/api/v1`

```text
/auth
/tenants
/users
/customers
/projects
/projects/{id}/members
/projects/{id}/documents
/documents/{id}/versions
/projects/{id}/review
/review-revisions/{id}/sections
/projects/{id}/analysis-runs
/projects/{id}/requirements
/requirements/{id}/revisions
/projects/{id}/clarifications
/projects/{id}/work-packages
/projects/{id}/rate-card
/projects/{id}/schedule
/projects/{id}/baselines
/projects/{id}/offers
/offers/{id}/versions
/offer-versions/{id}/preview
/offer-versions/{id}/approve
/offer-versions/{id}/export
/templates
/templates/{id}/versions
/jobs/{id}
/jobs/{id}/events
/artifacts/{id}
```

Lange Prozesse starten mit `202 Accepted` + `job_id`.

Rechteprüfung MUSS vor fachlicher Objektsuche erfolgen, sodass unberechtigte Zugriffe 403 liefern, bevor Existenz offengelegt wird.

---

## 24. Dateispeicher

v1: lokales Dateisystem hinter Storage-Adapter.

DB speichert:

- Artefakt-ID
- Tenant/Projekt
- Version
- MIME
- Größe
- SHA-256
- Storage-Key
- Status

Nicht fachlich auf Rohpfade verweisen.

Späterer Wechsel auf S3-kompatiblen Speicher muss ohne Domänenänderung möglich sein.

---

## 25. Backup und Restore

### 25.1 Backup-Inhalt

Vollbackup enthält:

- PostgreSQL-Dump
- kompletten Artefaktspeicher
- Konfigurationssnapshot ohne Klartext-Secrets
- Applikations-/Migrationsversion
- Manifest mit SHA-256-Prüfsummen

### 25.2 Pflicht vor Migration

Schemaänderung oder vollständiger Reset nur wenn vorheriges Backup erfolgreich validiert wurde.

### 25.3 Rotation

Letzte 20 Vollbackups pro Installation behalten.

### 25.4 Restore

Restore muss:

1. Dienste stoppen,
2. Sicherung validieren,
3. aktuellen Stand optional sichern,
4. DB wiederherstellen,
5. Artefakte wiederherstellen,
6. Migration-/Versionskompatibilität prüfen,
7. Konsistenzprüfung durchführen,
8. Anwendung starten.

---

## 26. Start und Deployment

### 26.1 Produktiv/Pilot lokal

Verbindlich:

```bash
docker compose up -d
```

Optional Wrapper:

```bash
./kusys up
```

### 26.2 Entwicklung

```bash
./kusys dev
```

### 26.3 Port-Fallback

Wunschports konfigurierbar.

Bei Belegung:

- bis zu 20 Folgeports prüfen
- Frontend-Backend-Verknüpfung automatisch anpassen
- strict mode bricht sofort ab

---

## 27. Performance-Ziele

Referenzhardware:

- 8 moderne CPU-Kerne
- 32 GB RAM
- NVMe SSD
- keine GPU erforderlich

Referenzprojekt:

- 100 Seiten PDF
- ca. 5.000 Abschnitte
- 1.000 Anforderungen
- 500 Arbeitspakete
- 10 Angebotsvarianten
- bis 20 parallele Benutzer

Ziele:

- 100 Seiten PDF mit Textebene: < 60 s vom gespeicherten Upload bis nutzbarem Prüfschritt
- OCR 100 Seiten: Ziel ≤ 10 min; Überschreitung warnt, bricht aber nicht automatisch ab
- normale UI/API-Schritte: < 1 s
- Plan-/Angebotsneuberechnung: < 2 s

---

## 28. Demo-/Testdaten

Pflicht-Demomandant:

- **Firma:** VAZA Demo Engineering GmbH
- **Adresse:** Beispielweg 12, 10115 Berlin, Deutschland
- **Kontakt:** Sophie Schneider
- **E-Mail:** sophie.schneider@example.com
- **Telefon:** +49 30 000000-10
- **USt-IdNr.:** DE000000000 (klar als Testwert kennzeichnen)

Kunde:

- Nordstern Verpackungstechnik GmbH
- KD-10001
- Hafenallee 25, 20457 Hamburg
- Anna Becker, Technischer Einkauf
- anna.becker@example.org
- +49 40 000000-20

Projekt:

- PX-2400 – Modernisierung Verpackungslinie
- PRJ-2026-0001
- RFQ-PX2400-2026-17
- ANG-2026-0001
- Dokumente: Lastenheft v1/v2 + Sicherheitsanforderungen v1

Alle Testdaten sind synthetisch.

---

## 29. Teststrategie

Jedes Akzeptanzkriterium benötigt mindestens einen automatisierten Test.

Zulässige Ebenen:

- Unit
- Domain
- API
- Integration
- DB
- Export
- Browser E2E

Jeder Test trägt Story-/Akzeptanzkennung.

Beispiel:

```text
US_17_AC_03_agent_output_schema_is_valid
```

### Browser

- vollständige Suite auf Chromium
- kritische Journeys zusätzlich Chrome, Edge, Firefox, WebKit/Safari-Kompatibilität

### KI

- vollständig mockbar
- keine echten Anbieter in Pflicht-CI

### OCR

- reguläre Tests via Mock
- optionale echte OCR-Integrationssuite

### DOCX/Excel

- strukturelle Tests
- ausgewählte visuelle Referenztests für DOCX
- Formeln und Serverwerte vergleichen

### Performance

- kleine Regressionstests in CI
- offizielle Benchmarks in separater Pipeline auf Referenzhardware

---

## 30. Wiederherstellungsprozedur einer leeren Umgebung

### 30.1 Voraussetzungen

- Git
- Docker + Docker Compose
- mindestens 32 GB RAM empfohlen
- 20+ GB freier Speicher für Entwicklung/Test

### 30.2 Schritte

1. Repository klonen.
2. exakt dokumentierten Commit/Tag auschecken.
3. `.env` aus `.env.example` erzeugen.
4. Master-Key und DB-Passwort sicher setzen.
5. `config/kusys.example.yaml` nach `config/kusys.yaml` kopieren.
6. Docker-Images anhand der gepinnten Tags ziehen/bauen.
7. `docker compose up -d postgres redis`.
8. Backend-Migrationen ausführen.
9. Demo-Daten laden.
10. vollständigen Stack starten.
11. Health prüfen.
12. Ersatzmodus-End-to-End-Test ausführen.
13. DOCX-/Excel-Smoke-Test ausführen.
14. Backup erzeugen.
15. Restore-Test in frischer Testinstanz durchführen.

### 30.3 Definition „erfolgreich wiederhergestellt“

- Health = healthy/degraded nur bei bewusst fehlenden optionalen Diensten
- Login funktioniert
- Demo-Projekt sichtbar
- Dokumentupload funktioniert
- Prüfschritt freigebbar
- Ersatzanalyse erzeugt Anforderungen und Arbeitspakete
- Terminplan berechenbar
- Angebot kalkulierbar
- DOCX generierbar
- Backup + Restore erfolgreich

---

## 31. Versions- und Build-Disziplin

Für echte Reproduzierbarkeit MUSS jeder Release enthalten:

- Git-Tag
- Frontend-Lockfile
- Python-Lockfile mit Hashes
- exakte Docker-Image-Tags, möglichst Digests
- DB-Migrations-Head
- Modell-/Schema-Versionen
- `kusys-environment.yaml`
- SBOM
- Changelog
- Backup-/Restore-Kompatibilitätsangabe

Keine Produktivumgebung darf mit `latest`-Docker-Tags gebaut werden.

---

## 32. Abweichungen vom ursprünglichen Story-Stand

Folgende später bestätigten Entscheidungen überschreiben ältere Storyformulierungen:

1. **Projektlöschung ist Soft Delete**, nicht physisches Löschen.
2. **Rollenmodell erweitert** auf Plattform-Admin, Firmen-Admin, Projektleiter, Projektmitarbeiter, Kunde.
3. **Projektmitarbeiter dürfen Kosten sehen.**
4. Plattform-Admin erhält fachlichen Firmenzugriff nur nach expliziter temporärer Freigabe.
5. Mehrere Dokumente und versionierte Lastenhefte je Projekt sind zulässig.
6. Analyseläufe werden nicht überschrieben, sondern versioniert gespeichert.
7. Freigegebene/versendete Angebote sind unveränderliche Snapshots.
8. Abgabedokumente sind vollständig konfigurierbar und versioniert.
9. Interne Rollen besitzen internen Kostensatz und Verkaufssatz.
10. Terminplanung verwendet echtes Resource Leveling.
11. Anforderungen können ein eigenes Budget/Zielwert in EUR besitzen.
12. Kosten und Verkaufspreise werden nachvollziehbar auf Anforderungen attribuiert.
13. Anforderungen können klassifizierte Abhängigkeiten untereinander besitzen.
14. Änderungen und Entfall einer Anforderung besitzen eine nicht-destruktive What-if-/Impact-Vorschau inklusive Preis- und Terminwirkung.

Bei Konflikten zwischen älteren User Stories und dieser Spezifikation gilt diese bestätigte Entscheidungsliste.

---

## 33. Umsetzungsreihenfolge

### Phase 1 – Muss-Durchstich

1. Mandanten/Auth/Rollen
2. Projekte/Kunden/Dokumentversionen
3. PDF/DOCX/PNG + OCR
4. Prüfschritt
5. Ersatzanalyse + AI-Adapter
6. Anforderungen/Klärungspunkte/Budgets/Abhängigkeiten/Impact
7. Arbeitspakete/Rate-Card
8. Resource Leveling + Terminplan
9. Angebotskalkulation
10. Vorlagen + DOCX
11. Excel
12. Audit/Locking/Backups
13. Akzeptanztests

### Phase 2 – Soll

- echte KI-Anbieter/CrewAI
- Kundenportal
- erweiterte Kostensteuerung
- Übersetzung
- Angebotsfreigaben/Statusausbau
- Baseline-Komfortfunktionen

### Phase 3 – Kann

- weiterführende Versions-/Impact-Komfortfunktionen
- zusätzliche Integrationen

---

## 34. Definition of Done für KuSys v1

KuSys v1 ist fertig, wenn:

- alle Muss-Stories gemäß finaler Entscheidungen umgesetzt sind,
- Upload bis DOCX als vertikaler Durchstich funktioniert,
- jede Muss-Akzeptanzbedingung mindestens einen automatisierten Test besitzt,
- alle Sicherheitsgrenzen serverseitig geprüft werden,
- keine fachlichen Snapshots rückwirkend veränderbar sind,
- Backup und Restore nachgewiesen funktionieren,
- Entwicklung und Docker-Installation reproduzierbar sind,
- Demo-Daten vollständig vorhanden sind,
- eine Story-/Test-Abdeckungsmatrix erzeugt werden kann.

---

## 35. Maßgebliche Artefakte je Release

Ein Release-Archiv MUSS mindestens enthalten:

```text
KuSys_Rebuild_Spec.md
kusys-environment.yaml
docker-compose.yml
config/kusys.example.yaml
.env.example
frontend lockfile
backend lockfile
migrations/
fixtures/
backup scripts
restore scripts
SBOM
CHANGELOG.md
```

Diese Kombination bildet die technische Wiederherstellungsbasis der Anwendung.
