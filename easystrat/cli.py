#!/usr/bin/env python3
"""
EasyVerein-Strato E-Mail-Synchronisierung CLI

Synchronisiert E-Mail-Adressen aktiver Mitglieder aus EasyVerein
mit den Weiterleitungen im Strato Webmail.

EasyVerein ist der Single Point of Truth.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from .config import load_config, setup_logging, SyncConfig


@click.group(invoke_without_command=True)
@click.option("--debug", is_flag=True, help="Debug-Ausgaben aktivieren")
@click.option(
    "--env",
    type=click.Path(exists=True, path_type=Path),
    help="Pfad zur .env Datei",
)
@click.pass_context
def cli(ctx: click.Context, debug: bool, env: Optional[Path]) -> None:
    """
    EasyVerein ↔ Strato Mail-Synchronisierung.

    Exportiert E-Mail-Adressen aktiver Mitglieder aus EasyVerein und
    synchronisiert sie mit Strato E-Mail-Weiterleitungen.

    \b
    Beispiele:
      easystrat export              # E-Mails exportieren (TXT)
      easystrat export --csv        # E-Mails mit Details (CSV)
      easystrat compare strato.txt  # Mit Datei vergleichen
      easystrat sync                # Synchronisieren (Trockenlauf)
      easystrat sync --apply        # Synchronisieren (echt)
      easystrat test                # Verbindungen testen
    """
    ctx.ensure_object(dict)

    # .env laden
    from dotenv import load_dotenv

    if env:
        load_dotenv(env)
    else:
        load_dotenv()

    # Konfiguration laden
    try:
        config = load_config()
    except Exception as e:
        click.secho(f"Fehler beim Laden der Konfiguration: {e}", fg="red", err=True)
        ctx.exit(1)

    # Log-Level setzen
    log_level = "DEBUG" if debug else config.log_level
    logger = setup_logging(log_level)

    ctx.obj["config"] = config
    ctx.obj["logger"] = logger
    ctx.obj["debug"] = debug

    # Wenn kein Subcommand, Hilfe anzeigen
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--csv", "csv_format", is_flag=True, help="Export als CSV mit Mitgliederdetails")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Ausgabedatei für Export",
)
@click.pass_context
def export(ctx: click.Context, csv_format: bool, output: Optional[Path]) -> None:
    """Exportiert E-Mail-Adressen aus EasyVerein."""
    from .export import EmailExporter

    config: SyncConfig = ctx.obj["config"]
    logger = ctx.obj["logger"]

    exporter = EmailExporter(config, logger)

    try:
        if csv_format:
            exporter.export_members_csv(output)
        else:
            exporter.export_emails_txt(output)
    except Exception as e:
        logger.error(f"Export fehlgeschlagen: {e}")
        ctx.exit(1)


@cli.command()
@click.argument("strato_file", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def compare(ctx: click.Context, strato_file: Path) -> None:
    """Vergleicht EasyVerein E-Mails mit einer Strato-Datei."""
    from .export import EmailExporter

    config: SyncConfig = ctx.obj["config"]
    logger = ctx.obj["logger"]

    exporter = EmailExporter(config, logger)
    exporter.compare_with_file(strato_file)


@cli.command()
@click.option("--apply", is_flag=True, help="Änderungen tatsächlich durchführen")
@click.option("--no-headless", is_flag=True, help="Browser sichtbar anzeigen (für Debugging)")
@click.pass_context
def sync(ctx: click.Context, apply: bool, no_headless: bool) -> None:
    """
    Synchronisiert EasyVerein mit Strato.

    Standardmäßig wird ein Trockenlauf durchgeführt (keine Änderungen).
    Mit --apply werden die Änderungen tatsächlich durchgeführt.
    """
    from .sync_selenium import SeleniumMailSynchronizer

    config: SyncConfig = ctx.obj["config"]
    logger = ctx.obj["logger"]

    if not config.strato_webmail:
        logger.error("Keine Strato-Zugangsdaten konfiguriert!")
        logger.info("Bitte STRATO_EMAIL und STRATO_PASSWORD in .env setzen")
        ctx.exit(1)

    if no_headless:
        config.strato_webmail.headless = False

    config.dry_run = not apply

    synchronizer = SeleniumMailSynchronizer(config, logger)
    result = synchronizer.sync()

    if result.success:
        if result.dry_run and result.diff.has_changes:
            logger.info("Trockenlauf abgeschlossen. Nutze --apply für echte Änderungen.")
    else:
        logger.error(f"Synchronisierung fehlgeschlagen: {result.error_message}")
        ctx.exit(1)


@cli.command()
@click.option("--strato-only", is_flag=True, help="Nur Strato-Verbindung testen")
@click.option("--no-headless", is_flag=True, help="Browser sichtbar anzeigen (für Debugging)")
@click.pass_context
def test(ctx: click.Context, strato_only: bool, no_headless: bool) -> None:
    """Testet die Verbindungen zu EasyVerein und/oder Strato."""
    from .easyverein_client import EasyVereinClient

    config: SyncConfig = ctx.obj["config"]
    logger = ctx.obj["logger"]

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
        if no_headless:
            config.strato_webmail.headless = False

        logger.info("Teste Strato Webmail-Verbindung...")
        from .strato_selenium import StratoSeleniumClient, StratoWebmailConfig as SeleniumConfig

        client = StratoSeleniumClient(
            SeleniumConfig(
                email=config.strato_webmail.email,
                password=config.strato_webmail.password,
                webmail_url=config.strato_webmail.webmail_url,
                headless=config.strato_webmail.headless,
                browser=config.strato_webmail.browser,
                timeout=config.strato_webmail.timeout,
            ),
            logger,
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

    if not success:
        ctx.exit(1)


def main() -> int:
    """Entry point für direkten Aufruf."""
    try:
        cli(obj={})
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
