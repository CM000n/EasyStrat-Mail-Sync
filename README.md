# EasyVerein-Strato E-Mail Synchronisierung

Exportiert E-Mail-Adressen aktiver Mitglieder aus [EasyVerein](https://easyverein.com/) und ermöglicht den Abgleich mit E-Mail-Weiterleitungen bei [Strato](https://www.strato.de/).

## Funktionsweise

```text
┌─────────────────┐         ┌──────────────────┐
│   EasyVerein    │         │      Strato      │
│  (API v2.0)     │         │   (manuell)      │
│                 │         │                  │
│  Mitglieder mit │  ──→    │  Weiterleitungs- │
│  E-Mail-Adresse │ export  │  Liste           │
│                 │         │                  │
│  (Source of     │  ←──    │  Vergleichs-     │
│   Truth)        │ compare │  Report          │
└─────────────────┘         └──────────────────┘
```

**EasyVerein ist der Single Point of Truth:**

- Exportiert werden nur aktive Mitglieder (ohne Kündigungsdatum)
- Das Tool zeigt genau welche E-Mails hinzugefügt/entfernt werden müssen
- Die Änderungen in Strato werden manuell durchgeführt

## Schnellstart

```bash
# 1. E-Mails aus EasyVerein exportieren
cd easystrat
python main.py --export

# 2. Deine aktuellen Strato-Weiterleitungen in eine Datei kopieren (z.B. strato.txt)
#    Eine E-Mail pro Zeile

# 3. Vergleichen und Report anzeigen
python main.py --compare strato.txt

# 4. Angezeigte Änderungen manuell in Strato durchführen
```

## Voraussetzungen

### EasyVerein

- EasyVerein Account mit API-Zugang
- API-Key aus dem EasyVerein Portal (Einstellungen → API)

## Installation

### 1. Virtuelle Umgebung erstellen (empfohlen)

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
```

### 2. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 3. Konfiguration anlegen

```bash
cp .env.example .env
```

`.env` bearbeiten und den EasyVerein API-Key eintragen:

```bash
EV_API_KEY=dein_api_key_hier
```

## Verwendung

### E-Mails exportieren

```bash
cd easystrat
python main.py --export              # Einfache Liste (TXT)
python main.py --export --csv        # Mit Mitgliederdetails (CSV)
python main.py --export -o liste.txt # In bestimmte Datei
```

### Mit Strato-Liste vergleichen

```bash
python main.py --compare strato.txt
```

### Verbindung testen

```bash
python main.py --test
```

### Debug-Ausgaben

```bash
python main.py --debug --export
```

## Beispielausgabe

### Export

```bash
2026-02-06 09:12:13 - INFO - Rufe E-Mail-Adressen aus EasyVerein ab...
2026-02-06 09:12:13 - INFO - Mitglieder verarbeitet: 172, übersprungen: 116, eindeutige E-Mails: 167
2026-02-06 09:12:13 - INFO - ✅ 167 E-Mail-Adressen exportiert nach: emails_20260206_091130.txt
```

### Vergleich

```bash
============================================================
VERGLEICHSREPORT: EasyVerein ↔ Strato
============================================================

EasyVerein (Source of Truth): 167 E-Mails
Strato-Datei:                 165 E-Mails
Übereinstimmend:              163 E-Mails

🟢 IN STRATO HINZUZUFÜGEN (4):
   (Diese E-Mails sind in EasyVerein aber NICHT in Strato)
   + neues.mitglied1@example.com
   + neues.mitglied2@example.com

🔴 AUS STRATO ZU ENTFERNEN (2):
   (Diese E-Mails sind in Strato aber NICHT mehr in EasyVerein)
   - ausgetretenes.mitglied@example.com

============================================================
```

## Projektstruktur

```text
easystrat_mail_sync/
├── easystrat/               # Python-Package
│   ├── __init__.py          # Package-Initialisierung
│   ├── main.py              # Hauptskript mit CLI
│   ├── config.py            # Konfigurationsmodul
│   ├── easyverein_client.py # EasyVerein API Client
│   ├── export.py            # Export- und Vergleichsmodul
│   ├── strato_selenium.py   # Strato Webmail Automation
│   ├── strato_sieve.py      # Sieve-Filter Verwaltung
│   ├── sync.py              # Synchronisationslogik
│   └── sync_selenium.py     # Selenium-basierte Synchronisation
├── requirements.txt         # Python-Abhängigkeiten
├── .env.example             # Beispiel-Konfiguration
└── README.md                # Diese Dokumentation
```

## Fehlerbehebung

### "EasyVerein-Verbindung fehlgeschlagen"

- API-Key im EasyVerein Portal erneuern (gilt 30 Tage)
- Prüfe ob API-Zugriff aktiviert ist
- Stelle sicher, dass der API-Key in `.env` korrekt eingetragen ist

### Keine E-Mail-Adressen gefunden

- Mitglieder müssen eine E-Mail-Adresse in den Kontaktdaten hinterlegt haben (`privateEmail` oder `companyEmail`)
- Nur aktive Mitglieder (ohne Kündigungsdatum) werden berücksichtigt
- Gekündigte Mitglieder werden automatisch übersprungen

### Viele Warnungen "hat keine E-Mail-Adresse"

- Das ist normal - nicht alle Mitglieder haben eine E-Mail hinterlegt
- Mit `--debug` siehst du Details zu jedem Mitglied

## Sicherheitshinweise

- Die `.env` Datei enthält deinen API-Key und sollte **niemals** in Git eingecheckt werden
- Der API-Key gilt 30 Tage und muss danach im EasyVerein-Portal erneuert werden

## Lizenz

MIT License
