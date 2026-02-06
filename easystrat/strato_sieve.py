"""
Strato ManageSieve Client für die Verwaltung von E-Mail-Weiterleitungen.

Verwendet das Sieve-Protokoll um Filterregeln zu verwalten, die E-Mails
an mehrere Adressen weiterleiten.
"""

import logging
import re
from typing import Set, Optional, Tuple

from sievelib.managesieve import Client as ManageSieveClient
from sievelib.factory import FiltersSet
from sievelib import parser

from .config import StratoConfig


class SieveScriptBuilder:
    """
    Baut Sieve-Scripts für E-Mail-Weiterleitungen.
    
    Ein typisches Weiterleitungs-Script sieht so aus:
    
    require ["copy", "redirect"];
    
    # Weiterleitung an alle Mitglieder
    redirect :copy "email1@example.com";
    redirect :copy "email2@example.com";
    ...
    """
    
    @staticmethod
    def build_redirect_script(emails: Set[str], keep_local: bool = True) -> str:
        """
        Erstellt ein Sieve-Script für Weiterleitungen.
        
        Args:
            emails: Set mit E-Mail-Adressen für die Weiterleitung
            keep_local: Wenn True, wird eine Kopie lokal behalten (:copy)
            
        Returns:
            Sieve-Script als String
        """
        lines = [
            '# EasyVerein-Strato Mail Sync',
            '# Automatisch generiertes Weiterleitungs-Script',
            '# NICHT MANUELL BEARBEITEN!',
            '#',
            f'# Anzahl Weiterleitungen: {len(emails)}',
            '#',
            '',
        ]
        
        # Erforderliche Extensions
        if keep_local:
            lines.append('require ["copy", "redirect"];')
        else:
            lines.append('require ["redirect"];')
        
        lines.append('')
        lines.append('# Weiterleitungen an alle Mitglieder')
        
        # Sortierte E-Mails für konsistente Ausgabe
        for email in sorted(emails):
            if keep_local:
                lines.append(f'redirect :copy "{email}";')
            else:
                lines.append(f'redirect "{email}";')
        
        return '\n'.join(lines)
    
    @staticmethod
    def parse_redirect_addresses(script_content: str) -> Set[str]:
        """
        Extrahiert E-Mail-Adressen aus einem Sieve-Script.
        
        Args:
            script_content: Inhalt des Sieve-Scripts
            
        Returns:
            Set mit extrahierten E-Mail-Adressen
        """
        emails: Set[str] = set()
        
        # Regex für redirect-Befehle (mit oder ohne :copy)
        # Matches: redirect "email@example.com";
        # Matches: redirect :copy "email@example.com";
        pattern = r'redirect\s+(?::copy\s+)?"([^"]+)"'
        
        matches = re.findall(pattern, script_content, re.IGNORECASE)
        
        for match in matches:
            email = match.lower().strip()
            if '@' in email:  # Einfache Validierung
                emails.add(email)
        
        return emails


class StratoSieveClient:
    """
    Client für die Verwaltung von Sieve-Scripts bei Strato.
    
    Verwendet das ManageSieve-Protokoll (RFC 5804) um Filterregeln
    zu verwalten.
    """
    
    def __init__(self, config: StratoConfig, logger: Optional[logging.Logger] = None):
        """
        Initialisiert den Strato Sieve Client.
        
        Args:
            config: Strato-Konfiguration mit Zugangsdaten
            logger: Optionaler Logger
        """
        self.config = config
        self.logger = logger or logging.getLogger('mail_sync.strato')
        self._client: Optional[ManageSieveClient] = None
        self._connected = False
    
    def connect(self) -> bool:
        """
        Verbindet sich mit dem ManageSieve-Server.
        
        Returns:
            True bei erfolgreicher Verbindung
        """
        if self._connected:
            return True
        
        self.logger.info(f"Verbinde mit {self.config.host}:{self.config.port}...")
        
        try:
            self._client = ManageSieveClient(self.config.host, self.config.port)
            
            # TLS aktivieren (Strato erfordert das)
            if not self._client.connect(
                self.config.email,
                self.config.password,
                starttls=True,
                authmech="PLAIN"
            ):
                self.logger.error("Authentifizierung fehlgeschlagen")
                return False
            
            self._connected = True
            self.logger.info("ManageSieve-Verbindung hergestellt")
            return True
            
        except Exception as e:
            self.logger.error(f"Verbindungsfehler: {e}")
            return False
    
    def disconnect(self):
        """Trennt die Verbindung zum Server."""
        if self._client and self._connected:
            try:
                self._client.logout()
            except Exception:
                pass
            self._connected = False
            self.logger.debug("Verbindung getrennt")
    
    def list_scripts(self) -> list[Tuple[str, bool]]:
        """
        Listet alle vorhandenen Sieve-Scripts auf.
        
        Returns:
            Liste von Tupeln (Script-Name, ist_aktiv)
        """
        if not self._ensure_connected():
            return []
        
        try:
            scripts = self._client.listscripts()
            self.logger.debug(f"Gefundene Scripts: {scripts}")
            return scripts
        except Exception as e:
            self.logger.error(f"Fehler beim Auflisten der Scripts: {e}")
            return []
    
    def get_script(self, name: Optional[str] = None) -> Optional[str]:
        """
        Ruft den Inhalt eines Sieve-Scripts ab.
        
        Args:
            name: Name des Scripts (oder None für das konfigurierte)
            
        Returns:
            Script-Inhalt oder None bei Fehler
        """
        if not self._ensure_connected():
            return None
        
        script_name = name or self.config.sieve_script_name
        
        try:
            content = self._client.getscript(script_name)
            if content:
                self.logger.debug(f"Script '{script_name}' geladen ({len(content)} Bytes)")
                return content
            else:
                self.logger.info(f"Script '{script_name}' nicht gefunden")
                return None
        except Exception as e:
            self.logger.warning(f"Script '{script_name}' konnte nicht geladen werden: {e}")
            return None
    
    def get_current_forwards(self) -> Set[str]:
        """
        Ruft die aktuell konfigurierten Weiterleitungsadressen ab.
        
        Returns:
            Set mit aktuell konfigurierten E-Mail-Adressen
        """
        script_content = self.get_script()
        
        if script_content is None:
            self.logger.info("Kein bestehendes Weiterleitungs-Script gefunden")
            return set()
        
        emails = SieveScriptBuilder.parse_redirect_addresses(script_content)
        self.logger.info(f"{len(emails)} bestehende Weiterleitungen gefunden")
        
        return emails
    
    def update_forwards(self, emails: Set[str], dry_run: bool = True) -> bool:
        """
        Aktualisiert die Weiterleitungen im Sieve-Script.
        
        Args:
            emails: Neue Liste der Weiterleitungsadressen
            dry_run: Wenn True, wird das Script nur generiert aber nicht hochgeladen
            
        Returns:
            True bei Erfolg
        """
        # Neues Script generieren
        script_content = SieveScriptBuilder.build_redirect_script(emails)
        
        self.logger.debug(f"Generiertes Script:\n{script_content}")
        
        if dry_run:
            self.logger.info("DRY-RUN: Script wurde nicht hochgeladen")
            print("\n--- Generiertes Sieve-Script ---")
            print(script_content)
            print("--- Ende Script ---\n")
            return True
        
        if not self._ensure_connected():
            return False
        
        try:
            # Script hochladen
            script_name = self.config.sieve_script_name
            
            self._client.putscript(script_name, script_content)
            self.logger.info(f"Script '{script_name}' hochgeladen")
            
            # Script aktivieren
            self._client.setactive(script_name)
            self.logger.info(f"Script '{script_name}' aktiviert")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Fehler beim Aktualisieren des Scripts: {e}")
            return False
    
    def delete_script(self, name: Optional[str] = None) -> bool:
        """
        Löscht ein Sieve-Script.
        
        Args:
            name: Name des Scripts (oder None für das konfigurierte)
            
        Returns:
            True bei Erfolg
        """
        if not self._ensure_connected():
            return False
        
        script_name = name or self.config.sieve_script_name
        
        try:
            # Erst deaktivieren falls aktiv
            self._client.setactive("")
            # Dann löschen
            self._client.deletescript(script_name)
            self.logger.info(f"Script '{script_name}' gelöscht")
            return True
        except Exception as e:
            self.logger.error(f"Fehler beim Löschen des Scripts: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Testet die Verbindung zum ManageSieve-Server.
        
        Returns:
            True wenn Verbindung erfolgreich
        """
        if self.connect():
            scripts = self.list_scripts()
            self.logger.info(f"Strato-Verbindung OK. {len(scripts)} Script(s) vorhanden.")
            return True
        return False
    
    def _ensure_connected(self) -> bool:
        """Stellt sicher, dass eine Verbindung besteht."""
        if not self._connected:
            return self.connect()
        return True
    
    def __enter__(self):
        """Context Manager Support."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Support."""
        self.disconnect()
        return False
