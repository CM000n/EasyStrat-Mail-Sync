"""
Synchronisierungsmodul für EasyVerein-Strato E-Mail-Adressen.

Führt den Abgleich zwischen EasyVerein (Single Point of Truth) und
den Strato-Weiterleitungen durch.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Set

from .config import SyncConfig
from .easyverein_client import EasyVereinClient
from .strato_sieve import StratoSieveClient


@dataclass
class SyncDiff:
    """Ergebnis des Vergleichs zwischen EasyVerein und Strato."""

    # E-Mails in EasyVerein (Source of Truth)
    easyverein_emails: Set[str]

    # E-Mails aktuell in Strato
    strato_emails: Set[str]

    # Neu hinzuzufügen (in EasyVerein aber nicht in Strato)
    to_add: Set[str]

    # Zu entfernen (in Strato aber nicht in EasyVerein)
    to_remove: Set[str]

    # Keine Änderung nötig (in beiden)
    unchanged: Set[str]

    @property
    def has_changes(self) -> bool:
        """Prüft ob Änderungen erforderlich sind."""
        return len(self.to_add) > 0 or len(self.to_remove) > 0

    @property
    def summary(self) -> str:
        """Gibt eine Zusammenfassung der Änderungen zurück."""
        return (
            f"EasyVerein: {len(self.easyverein_emails)} E-Mails | "
            f"Strato: {len(self.strato_emails)} E-Mails | "
            f"Hinzufügen: {len(self.to_add)} | "
            f"Entfernen: {len(self.to_remove)} | "
            f"Unverändert: {len(self.unchanged)}"
        )


@dataclass
class SyncResult:
    """Ergebnis der Synchronisierung."""

    success: bool
    diff: SyncDiff
    dry_run: bool
    error_message: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class MailSynchronizer:
    """
    Hauptklasse für die E-Mail-Synchronisierung.

    Orchestriert den Abgleich zwischen EasyVerein und Strato.
    """

    def __init__(self, config: SyncConfig, logger: Optional[logging.Logger] = None):
        """
        Initialisiert den Synchronisierer.

        Args:
            config: Gesamtkonfiguration
            logger: Optionaler Logger
        """
        self.config = config
        self.logger = logger or logging.getLogger("mail_sync")

        self.ev_client = EasyVereinClient(config.easyverein, self.logger)
        self.strato_client = StratoSieveClient(config.strato, self.logger)

    def compare(self) -> SyncDiff:
        """
        Vergleicht die E-Mail-Adressen zwischen EasyVerein und Strato.

        Returns:
            SyncDiff mit den Unterschieden
        """
        self.logger.info("Starte Vergleich...")

        # E-Mails aus EasyVerein holen
        ev_emails = self.ev_client.get_active_member_emails()

        # E-Mails aus Strato holen
        strato_emails = self.strato_client.get_current_forwards()

        # Differenzen berechnen
        to_add = ev_emails - strato_emails
        to_remove = strato_emails - ev_emails
        unchanged = ev_emails & strato_emails

        diff = SyncDiff(
            easyverein_emails=ev_emails,
            strato_emails=strato_emails,
            to_add=to_add,
            to_remove=to_remove,
            unchanged=unchanged,
        )

        self.logger.info(diff.summary)

        return diff

    def sync(self) -> SyncResult:
        """
        Führt die Synchronisierung durch.

        Bei dry_run=True werden keine Änderungen vorgenommen.

        Returns:
            SyncResult mit dem Ergebnis
        """
        self.logger.info("=" * 60)
        self.logger.info("EasyVerein-Strato E-Mail-Synchronisierung")
        self.logger.info("=" * 60)

        if self.config.dry_run:
            self.logger.warning("TROCKENLAUF - Keine Änderungen werden vorgenommen!")

        try:
            # Verbindungen testen
            self.logger.info("Teste Verbindungen...")

            if not self.ev_client.test_connection():
                return SyncResult(
                    success=False,
                    diff=self._empty_diff(),
                    dry_run=self.config.dry_run,
                    error_message="EasyVerein-Verbindung fehlgeschlagen",
                )

            if not self.strato_client.test_connection():
                return SyncResult(
                    success=False,
                    diff=self._empty_diff(),
                    dry_run=self.config.dry_run,
                    error_message="Strato-Verbindung fehlgeschlagen",
                )

            # Vergleich durchführen
            diff = self.compare()

            # Report ausgeben
            self._print_diff_report(diff)

            # Synchronisierung durchführen wenn nötig
            if not diff.has_changes:
                self.logger.info("Keine Änderungen erforderlich - bereits synchron!")
                return SyncResult(
                    success=True,
                    diff=diff,
                    dry_run=self.config.dry_run,
                )

            # Update durchführen
            success = self.strato_client.update_forwards(
                emails=diff.easyverein_emails, dry_run=self.config.dry_run
            )

            if success:
                if self.config.dry_run:
                    self.logger.info("Trockenlauf erfolgreich abgeschlossen")
                else:
                    self.logger.info("Synchronisierung erfolgreich abgeschlossen!")
            else:
                self.logger.error("Synchronisierung fehlgeschlagen!")

            return SyncResult(
                success=success,
                diff=diff,
                dry_run=self.config.dry_run,
            )

        except Exception as e:
            self.logger.exception(f"Unerwarteter Fehler: {e}")
            return SyncResult(
                success=False,
                diff=self._empty_diff(),
                dry_run=self.config.dry_run,
                error_message=str(e),
            )
        finally:
            # Verbindung trennen
            self.strato_client.disconnect()

    def _print_diff_report(self, diff: SyncDiff):
        """Gibt einen detaillierten Report der Änderungen aus."""
        print("\n" + "=" * 60)
        print("SYNCHRONISIERUNGS-REPORT")
        print("=" * 60)

        print(f"\nEasyVerein (Source of Truth): {len(diff.easyverein_emails)} active Mitglieder")
        print(f"Strato (aktuell):             {len(diff.strato_emails)} Weiterleitungen")

        if diff.to_add:
            print(f"\n✅ HINZUZUFÜGEN ({len(diff.to_add)}):")
            for email in sorted(diff.to_add):
                print(f"   + {email}")

        if diff.to_remove:
            print(f"\n❌ ZU ENTFERNEN ({len(diff.to_remove)}):")
            for email in sorted(diff.to_remove):
                print(f"   - {email}")

        if not diff.has_changes:
            print("\n✨ Keine Änderungen erforderlich - bereits synchron!")

        print("\n" + "=" * 60 + "\n")

    def _empty_diff(self) -> SyncDiff:
        """Erstellt ein leeres SyncDiff-Objekt."""
        return SyncDiff(
            easyverein_emails=set(),
            strato_emails=set(),
            to_add=set(),
            to_remove=set(),
            unchanged=set(),
        )

    def report_only(self) -> SyncDiff:
        """
        Führt nur einen Vergleich durch ohne Änderungen vorzunehmen.

        Returns:
            SyncDiff mit den Unterschieden
        """
        self.logger.info("Report-Modus - nur Vergleich, keine Änderungen")

        try:
            diff = self.compare()
            self._print_diff_report(diff)
            return diff
        finally:
            self.strato_client.disconnect()
