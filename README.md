# EasyVerein-Strato E-Mail Synchronisierung

Automatisiert die Synchronisierung von E-Mail-Weiterleitungen zwischen [EasyVerein](https://easyverein.com/) und [Strato Webmail](https://webmail.strato.de/).

## Funktionsweise

```text
┌─────────────────┐                     ┌──────────────────┐
│   EasyVerein    │                     │  Strato Webmail  │
│  (API v2.0)     │                     │   (Selenium)     │
│                 │                     │                  │
│  Mitglieder mit │  ───────────────►   │  Filterregeln    │
│  E-Mail-Adresse │    automatische     │  MC_email@...    │
│                 │   Synchronisierung  │                  │
│  (Source of     │                     │  Weiterleitungen │
│   Truth)        │                     │  an Mitglieder   │
└─────────────────┘                     └──────────────────┘
```

**EasyVerein ist der Single Point of Truth:**

- Nur aktive Mitglieder (ohne Kündigungsdatum) werden synchronisiert
- Pro Mitglied wird eine individuelle Filterregel in Strato erstellt
- Regeln haben das Format `MC_email@example.com` (Prefix konfigurierbar)
- Änderungen werden automatisch via Selenium durchgeführt

## Schnellstart

```bash
# 1. Trockenlauf - zeigt was synchronisiert würde
easystrat sync

# 2. Synchronisierung durchführen (nur hinzufügen)
easystrat sync --apply

# 3. Mit Löschungen (entfernt Regeln für ausgetretene Mitglieder)
easystrat sync --apply --allow-delete
```

## Voraussetzungen

### EasyVerein

- EasyVerein Account mit API-Zugang
- API-Key aus dem EasyVerein Portal (Einstellungen → API)

### Strato

- Strato E-Mail-Konto mit Webmail-Zugang
- Chrome/Chromium Browser installiert (für Selenium)

### System

- Python 3.10+
- Chrome oder Chromium Browser

## Installation

### Mit Poetry (empfohlen)

```bash
# Poetry installieren (falls noch nicht vorhanden)
curl -sSL https://install.python-poetry.org | python3 -

# Abhängigkeiten installieren
poetry install

# Shell mit aktivierter Umgebung starten
poetry shell
```

### Alternative mit pip

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Konfiguration

### .env Datei anlegen

```bash
cp .env.example .env
```

### Erforderliche Umgebungsvariablen

```bash
# EasyVerein API
EV_API_KEY=dein_api_key_hier

# Strato Webmail
STRATO_EMAIL=deine-email@deine-domain.de
STRATO_PASSWORD=dein_strato_passwort
```

### Optionale Umgebungsvariablen

```bash
# EasyVerein - Nur bestimmte Gruppe synchronisieren
EV_GROUP_ID=12345
EV_GROUP_NAME=Männerchor

# Strato - Anpassungen
STRATO_RULE_PREFIX=MC_           # Prefix für Regelnamen (Standard: MC_)
STRATO_INDIVIDUAL_RULES=true     # Individuelle Regeln pro Mitglied (Standard: true)

# Logging
LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR
```

## Verwendung

### Synchronisieren

```bash
# Trockenlauf (zeigt nur was passieren würde)
easystrat sync

# Änderungen durchführen (nur neue Regeln erstellen)
easystrat sync --apply

# Auch Regeln für ausgetretene Mitglieder löschen
easystrat sync --apply --allow-delete

# Mit sichtbarem Browser (für Debugging)
easystrat sync --apply --no-headless
```

### E-Mails exportieren

```bash
easystrat export              # Einfache Liste (TXT)
easystrat export --csv        # Mit Mitgliederdetails (CSV)
easystrat export -o liste.txt # In bestimmte Datei
```

### Mit lokaler Datei vergleichen

```bash
easystrat compare strato.txt
```

### Verbindungen testen

```bash
easystrat test                 # EasyVerein und Strato testen
easystrat test --strato-only   # Nur Strato testen
easystrat test --no-headless   # Mit sichtbarem Browser
```

### Debug-Modus

```bash
LOG_LEVEL=DEBUG easystrat sync --apply
# oder
easystrat --debug sync --apply
```

### Hilfe anzeigen

```bash
easystrat --help
easystrat sync --help
```

## Beispielausgabe

### Synchronisierung

```bash
$ easystrat sync --apply

2026-02-07 00:15:00 - INFO - ============================================================
2026-02-07 00:15:00 - INFO - EasyVerein-Strato E-Mail-Synchronisierung (Selenium)
2026-02-07 00:15:00 - INFO - ============================================================
2026-02-07 00:15:00 - INFO - Modus: Individuelle Regeln (Prefix: MC_)
2026-02-07 00:15:01 - INFO - Teste Verbindungen...
2026-02-07 00:15:02 - INFO - ✅ EasyVerein: OK
2026-02-07 00:15:05 - INFO - ✅ Strato Webmail: OK
2026-02-07 00:15:06 - INFO - Starte Vergleich...
2026-02-07 00:15:08 - INFO - 45 verwaltete E-Mail-Regeln gefunden (Prefix: 'MC_')
2026-02-07 00:15:09 - INFO - EasyVerein: 48 E-Mails | Strato: 45 E-Mails | Hinzufügen: 3 | Entfernen: 0 | Unverändert: 45
2026-02-07 00:15:09 - INFO - Führe Änderungen durch...
2026-02-07 00:15:15 - INFO - ✅ Regel erstellt: MC_neues.mitglied@example.com
2026-02-07 00:15:21 - INFO - ✅ Regel erstellt: MC_weiteres.mitglied@example.com
2026-02-07 00:15:27 - INFO - ✅ Regel erstellt: MC_drittes.mitglied@example.com
2026-02-07 00:15:27 - INFO - Synchronisierung abgeschlossen: 3 erstellt, 0 gelöscht
```

### Trockenlauf

```bash
$ easystrat sync

2026-02-07 00:10:00 - INFO - ============================================================
2026-02-07 00:10:00 - INFO - EasyVerein-Strato E-Mail-Synchronisierung (Selenium)
2026-02-07 00:10:00 - INFO - ============================================================
2026-02-07 00:10:00 - WARNING - TROCKENLAUF - Keine Änderungen werden vorgenommen!
2026-02-07 00:10:05 - INFO - EasyVerein: 48 E-Mails | Strato: 45 E-Mails | Hinzufügen: 3 | Entfernen: 0

🟢 HINZUZUFÜGEN (3):
   + neues.mitglied@example.com
   + weiteres.mitglied@example.com
   + drittes.mitglied@example.com

2026-02-07 00:10:05 - INFO - Trockenlauf abgeschlossen. Nutze --apply für echte Änderungen.
```

## Projektstruktur

```text
easystrat_mail_sync/
├── easystrat/               # Python-Package
│   ├── __init__.py          # Package-Initialisierung
│   ├── cli.py               # Click CLI (Haupteinstiegspunkt)
│   ├── config.py            # Konfigurationsmodul
│   ├── easyverein_client.py # EasyVerein API Client
│   ├── export.py            # Export- und Vergleichsmodul
│   ├── strato_selenium.py   # Strato Webmail Automation (Selenium)
│   ├── sync_selenium.py     # Selenium-basierte Synchronisation
│   ├── strato_sieve.py      # Sieve-Filter (Legacy, nicht verwendet)
│   └── sync.py              # Legacy-Synchronisation
├── pyproject.toml           # Poetry-Konfiguration & Abhängigkeiten
├── .env.example             # Beispiel-Konfiguration
└── README.md                # Diese Dokumentation
```

## Wichtige Hinweise

### Strato-Limit

⚠️ **Strato erlaubt maximal 50 Weiterleitungsregeln pro Postfach.** Bei Erreichen des Limits schlägt das Erstellen neuer Regeln fehl.

### Sicherheit beim Löschen

Regeln werden standardmäßig **nicht** automatisch gelöscht. Dies schützt vor versehentlichem Datenverlust bei API-Fehlern. Verwende `--allow-delete` nur wenn du sicher bist.

### Browser-Automatisierung

Die Strato-Synchronisierung verwendet Selenium mit Chrome/Chromium. Bei Problemen:

- `--no-headless` zeigt den Browser für Debugging
- Debug-Screenshots werden als `debug_*.png` gespeichert

## Fehlerbehebung

### "EasyVerein-Verbindung fehlgeschlagen"

- API-Key im EasyVerein Portal erneuern (gilt 30 Tage)
- Prüfe ob API-Zugriff aktiviert ist
- Stelle sicher, dass der API-Key in `.env` korrekt eingetragen ist

### "Strato Webmail-Verbindung fehlgeschlagen"

- Prüfe E-Mail und Passwort in `.env`
- Teste manuellen Login unter https://webmail.strato.de/
- Chrome/Chromium muss installiert sein

### "Konnte 'Umleiten nach' nicht auswählen"

- Möglicherweise wurde das Strato-Limit von 50 Regeln erreicht
- Lösche nicht mehr benötigte Regeln manuell in Strato

### Keine E-Mail-Adressen gefunden

- Mitglieder müssen eine E-Mail-Adresse haben (`privateEmail` oder `companyEmail`)
- Nur aktive Mitglieder (ohne Kündigungsdatum) werden berücksichtigt
- Bei Gruppenfilterung: Prüfe `EV_GROUP_ID`

### Debug-Informationen sammeln

```bash
LOG_LEVEL=DEBUG easystrat sync --no-headless
```

Dies zeigt detaillierte Logs und öffnet den Browser sichtbar.

## Sicherheitshinweise

- Die `.env` Datei enthält sensible Zugangsdaten und sollte **niemals** in Git eingecheckt werden
- Der EasyVerein API-Key gilt 30 Tage und muss danach erneuert werden
- Strato-Passwort sollte ein starkes, einzigartiges Passwort sein

## Lizenz

MIT License
