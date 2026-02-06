#!/usr/bin/env python3
"""
EasyVerein-Strato E-Mail-Synchronisierung

Synchronisiert E-Mail-Adressen aktiver Mitglieder aus EasyVerein
mit den Weiterleitungen im Strato Webmail (via Selenium).

EasyVerein ist der Single Point of Truth.

Verwendung:
    python main.py --sync             # Vergleicht und zeigt Änderungen (Trockenlauf)
    python main.py --sync --apply     # Führt Änderungen durch
    python main.py --export           # Exportiert E-Mails in eine TXT-Datei
    python main.py --test             # Testet Verbindungen
"""

import argparse
import sys
from pathlib import Path

from config import load_config, setup_logging, SyncConfig


def parse_args() -> argparse.Namespace:
    """Parst die Kommandozeilenargumente."""
    parser = argparse.ArgumentParser(
        description="EasyVerein-Strato E-Mail-Synchronisierung",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s --sync                   # Vergleicht EasyVerein mit Strato (Trockenlauf)
  %(prog)s --sync --apply           # Führt Änderungen durch  
  %(prog)s --export                 # Exportiert EasyVerein E-Mails in TXT
  %(prog)s --export --csv           # Exportiert als CSV mit Namen
  %(prog)s --compare strato.txt     # Vergleicht mit manueller Datei
  %(prog)s --test                   # Testet alle Verbindungen
  %(prog)s --test-strato            # Testet nur Strato Webmail Login

Hinweis:
  Erstelle eine .env Datei basierend auf .env.example mit deinen Zugangsdaten.
        """,
    )
    
    # Hauptaktionen
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Synchronisiert EasyVerein mit Strato (Standard: Trockenlauf)"
    )
    
    parser.add_argument(
        "--export",
        action="store_true",
        help="Exportiert E-Mail-Adressen aus EasyVerein"
    )
    
    parser.add_argument(
        "--compare",
        type=Path,
        metavar="DATEI",
        help="Vergleicht mit manueller Strato-Datei (eine E-Mail pro Zeile)"
    )
    
    parser.add_argument(
        "--test",
        action="store_true",
        help="Testet alle Verbindungen (EasyVerein + Strato)"
    )
    
    parser.add_argument(
        "--test-strato",
        action="store_true",
        help="Testet nur Strato Webmail Login"
    )
    
    # Optionen
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Führt Änderungen tatsächlich durch (nur mit --sync)"
    )
    
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Export als CSV mit Mitgliederdetails"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Ausgabedatei für Export"
    )
    
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Browser sichtbar anzeigen (für Debugging)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug-Ausgaben aktivieren"
    )
    
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help="Pfad zur .env Datei"
    )
    
    return parser.parse_args()


def test_connections(config: SyncConfig, logger, strato_only: bool = False) -> bool:
    """Testet die Verbindungen."""
    from easyverein_client import EasyVereinClient
    
    success = True
    
    if not strato_only:
        # EasyVerein testen
        logger.info("Teste EasyVerein-Verbindung...")
        ev_client = EasyVereinClient(config.easyverein, logger)
        if ev_client.test_connection():
            logger.info("✅ EasyVerein: OK")
        else:
            logger.error("❌ EasyVerein: FEHLGESCHLAGEN")
            success = False
    
    # Strato testen
    if config.strato_webmail:
        logger.info("Teste Strato Webmail-Verbindung...")
        from strato_selenium import StratoSeleniumClient, StratoWebmailConfig as SeleniumConfig
        
        client = StratoSeleniumClient(
            SeleniumConfig(
                email=config.strato_webmail.email,
                password=config.strato_webmail.password,
                webmail_url=config.strato_webmail.webmail_url,
                headless=config.strato_webmail.headless,
                browser=config.strato_webmail.browser,
                timeout=config.strato_webmail.timeout,
            ),
            logger
        )
        
        if client.test_connection():
            logger.info("✅ Strato Webmail: OK")
        else:
            logger.error("❌ Strato Webmail: FEHLGESCHLAGEN")
            success = False
    else:
        logger.warning("⚠️  Strato-Zugangsdaten nicht konfiguriert")
        if strato_only:
            success = False
    
    return success


def run_sync(config: SyncConfig, logger, apply: bool = False) -> int:
    """Führt die Synchronisierung durch."""
    from sync_selenium import SeleniumMailSynchronizer
    
    if not config.strato_webmail:
        logger.error("Keine Strato-Zugangsdaten konfiguriert!")
        logger.info("Bitte STRATO_EMAIL und STRATO_PASSWORD in .env setzen")
        return 1
    
    config.dry_run = not apply
    
    synchronizer = SeleniumMailSynchronizer(config, logger)
    result = synchronizer.sync()
    
    if result.success:
        if result.dry_run and result.diff.has_changes:
            logger.info("Trockenlauf abgeschlossen. Nutze --apply für echte Änderungen.")
        return 0
    else:
        logger.error(f"Synchronisierung fehlgeschlagen: {result.error_message}")
        return 1


def run_export(config: SyncConfig, logger, csv_format: bool = False, output: Path = None) -> int:
    """Exportiert E-Mail-Adressen."""
    from export import EmailExporter
    
    exporter = EmailExporter(config, logger)
    
    try:
        if csv_format:
            exporter.export_members_csv(output)
        else:
            exporter.export_emails_txt(output)
        return 0
    except Exception as e:
        logger.error(f"Export fehlgeschlagen: {e}")
        return 1


def run_compare(config: SyncConfig, logger, strato_file: Path) -> int:
    """Vergleicht mit manueller Datei."""
    from export import EmailExporter
    
    if not strato_file.exists():
        logger.error(f"Datei nicht gefunden: {strato_file}")
        return 1
    
    exporter = EmailExporter(config, logger)
    exporter.compare_with_file(strato_file)
    return 0


def main() -> int:
    """Hauptfunktion."""
    args = parse_args()
    
    # Konfiguration laden
    try:
        from dotenv import load_dotenv
        if args.env:
            load_dotenv(args.env)
        else:
            load_dotenv()
        
        config = load_config()
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}", file=sys.stderr)
        return 1
    
    # Headless-Modus konfigurieren
    if hasattr(args, 'no_headless') and args.no_headless:
        config.strato_webmail.headless = False
    
    # Log-Level anpassen
    log_level = "DEBUG" if args.debug else config.log_level
    logger = setup_logging(log_level)
    
    # Modus wählen
    if args.test:
        # EasyVerein und Strato testen
        success = test_connections(config, logger, strato_only=False)
        return 0 if success else 1
    
    if args.test_strato:
        # Nur Strato-Verbindungstest
        success = test_connections(config, logger, strato_only=True)
        return 0 if success else 1
    
    if args.sync:
        # Vollständige Synchronisierung
        apply = hasattr(args, 'apply') and args.apply
        return run_sync(config, logger, apply=apply)
    
    if args.compare:
        # Mit manueller Strato-Datei vergleichen
        return run_compare(config, logger, args.compare)
    
    if args.export:
        # E-Mails exportieren
        csv_format = hasattr(args, 'csv') and args.csv
        output = args.output if hasattr(args, 'output') else None
        return run_export(config, logger, csv_format=csv_format, output=output)
    
    # Wenn keine Option angegeben, Hilfe zeigen
    print("EasyVerein ↔ Strato Mail-Synchronisierung")
    print("=" * 45)
    print()
    print("Verfügbare Befehle:")
    print("  --sync             E-Mails synchronisieren (Trockenlauf)")
    print("  --sync --apply     E-Mails synchronisieren (echte Änderungen)")
    print("  --test             EasyVerein-Verbindung testen")
    print("  --test-strato      Strato Webmail-Login testen")
    print("  --export           E-Mails exportieren (TXT)")
    print("  --export --csv     E-Mails mit Details exportieren (CSV)")
    print("  --compare DATEI    Mit manueller Strato-Liste vergleichen")
    print("  --no-headless      Browser-Fenster anzeigen")
    print("  --debug            Debug-Ausgabe aktivieren")
    print("  --help             Ausführliche Hilfe")
    print()
    print("Starte mit: python main.py --sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
