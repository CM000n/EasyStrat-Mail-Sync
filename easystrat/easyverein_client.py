"""
EasyVerein Client für den Abruf von Mitglieder-E-Mail-Adressen.

Nutzt die python-easyverein Bibliothek für den API-Zugriff.
"""

import logging
from typing import Set, Optional
from dataclasses import dataclass

from easyverein import EasyvereinAPI

from config import EasyVereinConfig


@dataclass
class MemberInfo:
    """Informationen zu einem Mitglied."""
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    membership_number: Optional[str] = None
    is_active: bool = True


class EasyVereinClient:
    """
    Client für den Zugriff auf die EasyVerein API.
    
    Ruft aktive Mitglieder und deren E-Mail-Adressen ab.
    """
    
    def __init__(self, config: EasyVereinConfig, logger: Optional[logging.Logger] = None):
        """
        Initialisiert den EasyVerein Client.
        
        Args:
            config: EasyVerein-Konfiguration mit API-Key
            logger: Optionaler Logger
        """
        self.config = config
        self.logger = logger or logging.getLogger('mail_sync.easyverein')
        self._client: Optional[EasyvereinAPI] = None
    
    def _get_client(self) -> EasyvereinAPI:
        """Lazy initialization des API-Clients."""
        if self._client is None:
            self._client = EasyvereinAPI(
                api_key=self.config.api_key,
                api_version=self.config.api_version,
            )
        return self._client
    
    def _get_members_by_group(self, group_id: int, query: str) -> list:
        """
        Ruft Mitglieder einer bestimmten Gruppe ab.
        
        Nutzt die python-easyverein Library um für jedes Mitglied zu prüfen,
        ob es der Gruppe angehört. Implementiert Throttling um Rate Limiting zu umgehen.
        
        Args:
            group_id: ID der Mitgliedergruppe
            query: GraphQL-ähnliche Query für die Felder
            
        Returns:
            Liste von Member-Objekten, die zur Gruppe gehören
        """
        import time
        
        client = self._get_client()
        
        # Alle Mitglieder holen
        self.logger.debug("Lade alle Mitglieder...")
        all_members = client.member.get_all(query=query)
        self.logger.debug(f"{len(all_members)} Mitglieder geladen")
        
        # Filtern nach Gruppenzugehörigkeit mit Rate-Limiting-Schutz
        self.logger.info(f"Prüfe Gruppenzugehörigkeit für {len(all_members)} Mitglieder (kann dauern)...")
        filtered_members = []
        
        for i, member in enumerate(all_members):
            if (i + 1) % 20 == 0:
                self.logger.info(f"Fortschritt: {i+1}/{len(all_members)} Mitglieder geprüft...")
            
            # Prüfe ob Mitglied in der Gruppe ist
            max_retries = 3
            for retry in range(max_retries):
                try:
                    membership = client.member.member_group(member).get_group_membership(group_id)
                    if membership is not None:
                        filtered_members.append(member)
                    break
                except Exception as e:
                    if "429" in str(e) or "too many" in str(e).lower():
                        # Rate Limiting - warte und versuche nochmal
                        wait_time = 10 * (retry + 1)  # Exponential backoff
                        self.logger.warning(f"Rate Limit erreicht, warte {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        self.logger.debug(f"Fehler bei Mitglied {member.membershipNumber}: {e}")
                        break
            
            # Kleine Pause zwischen Anfragen um Rate Limiting zu vermeiden
            if i < len(all_members) - 1:
                time.sleep(0.3)  # 300ms Pause
        
        self.logger.info(f"Gefunden: {len(filtered_members)} Mitglieder in Gruppe {group_id}")
        return filtered_members
    
    def get_active_member_emails(self) -> Set[str]:
        """
        Ruft alle E-Mail-Adressen aktiver Mitglieder ab.
        
        Wenn eine group_id konfiguriert ist, werden nur Mitglieder dieser Gruppe abgerufen.
        
        Ein Mitglied gilt als aktiv, wenn:
        - Es nicht gelöscht ist (nicht im Papierkorb)
        - resignationDate ist None (keine Kündigung)
        
        Returns:
            Set mit E-Mail-Adressen aller aktiven Mitglieder
        """
        group_info = ""
        if self.config.group_id:
            group_info = f" der Gruppe '{self.config.group_name}' (ID: {self.config.group_id})"
        self.logger.info(f"Rufe aktive Mitglieder{group_info} von EasyVerein ab...")
        
        client = self._get_client()
        emails: Set[str] = set()
        members_processed = 0
        members_skipped = 0
        
        try:
            # Query für benötigte Felder
            query = "{id,membershipNumber,resignationDate,contactDetails{firstName,familyName,privateEmail,companyEmail}}"
            
            if self.config.group_id:
                # Gefilterte Abfrage nach Gruppe via direkten API-Call
                all_members = self._get_members_by_group(self.config.group_id, query)
            else:
                # Alle Mitglieder abrufen
                all_members = client.member.get_all(query=query)
            
            self.logger.debug(f"Insgesamt {len(all_members)} Mitglieder gefunden")
            
            for member in all_members:
                # Prüfen ob das Mitglied aktiv ist (keine Kündigung)
                if member.resignationDate is not None:
                    self.logger.debug(
                        f"Mitglied {member.membershipNumber} übersprungen (gekündigt)"
                    )
                    members_skipped += 1
                    continue
                
                # E-Mail-Adresse extrahieren
                email = self._extract_email(member)
                
                if email:
                    # E-Mail-Adresse normalisieren (kleinschreiben, trimmen)
                    normalized_email = email.lower().strip()
                    emails.add(normalized_email)
                    members_processed += 1
                    
                    self.logger.debug(
                        f"Mitglied {member.membershipNumber}: {normalized_email}"
                    )
                else:
                    self.logger.warning(
                        f"Mitglied {member.membershipNumber} hat keine E-Mail-Adresse"
                    )
                    members_skipped += 1
            
            self.logger.info(
                f"Mitglieder verarbeitet: {members_processed}, "
                f"übersprungen: {members_skipped}, "
                f"eindeutige E-Mails: {len(emails)}"
            )
            
            return emails
            
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Mitglieder: {e}")
            raise
    
    def _extract_email(self, member) -> Optional[str]:
        """
        Extrahiert die E-Mail-Adresse aus den Mitgliederdaten.
        
        Priorität:
        1. privateEmail aus contactDetails
        2. companyEmail aus contactDetails (Fallback)
        
        Args:
            member: Mitgliederobjekt von der API
            
        Returns:
            E-Mail-Adresse oder None
        """
        if member.contactDetails is None:
            return None
        
        contact = member.contactDetails
        
        # Bevorzugt privateEmail verwenden
        if hasattr(contact, 'privateEmail') and contact.privateEmail:
            return contact.privateEmail
        
        # Fallback auf companyEmail
        if hasattr(contact, 'companyEmail') and contact.companyEmail:
            return contact.companyEmail
        
        return None
    
    def get_members_details(self) -> list[MemberInfo]:
        """
        Ruft detaillierte Informationen aller aktiven Mitglieder ab.
        
        Returns:
            Liste mit MemberInfo-Objekten
        """
        self.logger.info("Rufe Mitgliederdetails von EasyVerein ab...")
        
        client = self._get_client()
        members: list[MemberInfo] = []
        
        try:
            all_members = client.member.get_all(
                query="{id,membershipNumber,resignationDate,contactDetails{firstName,familyName,privateEmail,companyEmail}}"
            )
            
            for member in all_members:
                # Nur aktive Mitglieder
                if member.resignationDate is not None:
                    continue
                
                email = self._extract_email(member)
                if not email:
                    continue
                
                contact = member.contactDetails
                members.append(MemberInfo(
                    id=member.id,
                    email=email.lower().strip(),
                    first_name=contact.firstName if contact and hasattr(contact, 'firstName') else None,
                    last_name=contact.familyName if contact and hasattr(contact, 'familyName') else None,
                    membership_number=member.membershipNumber,
                    is_active=True,
                ))
            
            self.logger.info(f"{len(members)} aktive Mitglieder mit E-Mail gefunden")
            return members
            
        except Exception as e:
            self.logger.error(f"Fehler beim Abrufen der Mitgliederdetails: {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Testet die Verbindung zur EasyVerein API.
        
        Returns:
            True wenn Verbindung erfolgreich, sonst False
        """
        try:
            client = self._get_client()
            # Einfacher Test: Eine Seite Mitglieder abrufen
            members, count = client.member.get(limit=1)
            self.logger.info(f"EasyVerein-Verbindung OK. {count} Mitglieder insgesamt.")
            return True
        except Exception as e:
            self.logger.error(f"EasyVerein-Verbindung fehlgeschlagen: {e}")
            return False
