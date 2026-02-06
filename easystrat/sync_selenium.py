"""
Synchronisierungsmodul mit Selenium-Unterstützung für Strato Webmail.

Führt den Abgleich zwischen EasyVerein (Single Point of Truth) und
den Strato-Weiterleitungen durch, mit Selenium-basiertem Zugriff auf Strato.
"""

import logging
from dataclasses import dataclass
from typing import Set, Optional
from datetime import datetime

from config import SyncConfig, StratoWebmailConfig
from easyverein_client import EasyVereinClient
from strato_selenium import StratoSeleniumClient, StratoWebmailConfig as SeleniumConfig


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


class SeleniumMailSynchronizer:
    """
    Synchronisierer mit Selenium-basiertem Strato-Zugriff.
    
    Orchestriert den Abgleich zwischen EasyVerein und Strato Webmail.
    """
    
    def __init__(self, config: SyncConfig, logger: Optional[logging.Logger] = None):
        """
        Initialisiert den Synchronisierer.
        
        Args:
            config: Gesamtkonfiguration
            logger: Optionaler Logger
        """
        self.config = config
        self.logger = logger or logging.getLogger('mail_sync')
        
        self.ev_client = EasyVereinClient(config.easyverein, self.logger)
        
        # Strato Selenium Client
        if config.strato_webmail:
            self.strato_client = StratoSeleniumClient(
                SeleniumConfig(
                    email=config.strato_webmail.email,
                    password=config.strato_webmail.password,
                    webmail_url=config.strato_webmail.webmail_url,
                    headless=config.strato_webmail.headless,
                    browser=config.strato_webmail.browser,
                    timeout=config.strato_webmail.timeout,
                ),
                self.logger
            )
        else:
            self.strato_client = None
    
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
        if self.strato_client:
            strato_emails = self.strato_client.get_forwarding_addresses()
        else:
            self.logger.warning("Kein Strato-Client konfiguriert")
            strato_emails = set()
        
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
        self.logger.info("EasyVerein-Strato E-Mail-Synchronisierung (Selenium)")
        self.logger.info("=" * 60)
        
        if self.config.dry_run:
            self.logger.warning("TROCKENLAUF - Keine Änderungen werden vorgenommen!")
        
        if not self.strato_client:
            self.logger.error("Keine Strato-Zugangsdaten konfiguriert!")
            return SyncResult(
                success=False,
                diff=self._empty_diff(),
                dry_run=self.config.dry_run,
                error_message="Strato-Konfiguration fehlt"
            )
        
        try:
            # Verbindungen testen
            self.logger.info("Teste Verbindungen...")
            
            if not self.ev_client.test_connection():
                return SyncResult(
                    success=False,
                    diff=self._empty_diff(),
                    dry_run=self.config.dry_run,
                    error_message="EasyVerein-Verbindung fehlgeschlagen"
                )
            
            if not self.strato_client.connect():
                return SyncResult(
                    success=False,
                    diff=self._empty_diff(),
                    dry_run=self.config.dry_run,
                    error_message="Strato Webmail-Verbindung fehlgeschlagen"
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
            
            if self.config.dry_run:
                self.logger.info("Trockenlauf - Änderungen würden durchgeführt werden")
                return SyncResult(
                    success=True,
                    diff=diff,
                    dry_run=True,
                )
            
            # Tatsächliche Änderungen durchführen
            self.logger.info("Führe Änderungen durch...")
            
            # Öffne die Regel im Bearbeitungsmodus
            if not self.strato_client.open_rule_for_editing():
                return SyncResult(
                    success=False,
                    diff=diff,
                    dry_run=False,
                    error_message="Konnte Filterregel nicht zur Bearbeitung öffnen"
                )
            
            errors = []
            added = 0
            removed = 0
            
            # Zuerst entfernen
            for email in diff.to_remove:
                if self.strato_client.remove_forwarding_address(email):
                    removed += 1
                    self.logger.info(f"✅ Entfernt: {email}")
                else:
                    errors.append(f"Konnte nicht entfernen: {email}")
            
            # Dann hinzufügen
            for email in diff.to_add:
                if self.strato_client.add_forwarding_address(email):
                    added += 1
                    self.logger.info(f"✅ Hinzugefügt: {email}")
                else:
                    errors.append(f"Konnte nicht hinzufügen: {email}")
            
            # Speichern
            if added > 0 or removed > 0:
                if self.strato_client.save_changes():
                    self.logger.info("✅ Änderungen gespeichert")
                else:
                    errors.append("Konnte Änderungen nicht speichern")
            
            # Zusammenfassung
            self.logger.info(f"Synchronisierung abgeschlossen: {added} hinzugefügt, {removed} entfernt")
            
            if errors:
                for error in errors:
                    self.logger.warning(error)
                return SyncResult(
                    success=False,
                    diff=diff,
                    dry_run=False,
                    error_message="; ".join(errors[:5])  # Nur erste 5 Fehler
                )
            
            return SyncResult(
                success=True,
                diff=diff,
                dry_run=self.config.dry_run,
            )
            
        except Exception as e:
            self.logger.exception(f"Unerwarteter Fehler: {e}")
            return SyncResult(
                success=False,
                diff=self._empty_diff(),
                dry_run=self.config.dry_run,
                error_message=str(e)
            )
        finally:
            # Verbindung trennen
            if self.strato_client:
                self.strato_client.disconnect()
    
    def _print_diff_report(self, diff: SyncDiff):
        """Gibt einen detaillierten Report der Änderungen aus."""
        print("\n" + "=" * 60)
        print("SYNCHRONISIERUNGS-REPORT")
        print("=" * 60)
        
        print(f"\nEasyVerein (Source of Truth): {len(diff.easyverein_emails)} aktive Mitglieder")
        print(f"Strato (aktuell):             {len(diff.strato_emails)} Weiterleitungen")
        
        if diff.to_add:
            print(f"\n🟢 IN STRATO HINZUZUFÜGEN ({len(diff.to_add)}):")
            for email in sorted(diff.to_add):
                print(f"   + {email}")
        
        if diff.to_remove:
            print(f"\n🔴 AUS STRATO ZU ENTFERNEN ({len(diff.to_remove)}):")
            for email in sorted(diff.to_remove):
                print(f"   - {email}")
        
        if not diff.has_changes:
            print("\n✨ Perfekt synchron! Keine Änderungen nötig.")
        
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


def test_strato_connection(config: SyncConfig, logger: logging.Logger) -> bool:
    """
    Testet die Strato Webmail Verbindung.
    
    Args:
        config: Konfiguration
        logger: Logger
        
    Returns:
        True wenn erfolgreich
    """
    if not config.strato_webmail:
        logger.error("Keine Strato-Zugangsdaten konfiguriert!")
        logger.info("Bitte STRATO_EMAIL und STRATO_PASSWORD in .env setzen")
        return False
    
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
    
    return client.test_connection()
