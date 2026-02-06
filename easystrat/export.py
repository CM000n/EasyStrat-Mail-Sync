#!/usr/bin/env python3
"""
Export-Modul für EasyVerein E-Mail-Adressen.

Erstellt Exportdateien zum manuellen Abgleich mit Strato-Weiterleitungen.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

from config import SyncConfig
from easyverein_client import EasyVereinClient, MemberInfo


class EmailExporter:
    """
    Exportiert E-Mail-Adressen aus EasyVerein in verschiedene Formate.
    """
    
    def __init__(self, config: SyncConfig, logger: Optional[logging.Logger] = None):
        """
        Initialisiert den Exporter.
        
        Args:
            config: Konfiguration
            logger: Optionaler Logger
        """
        self.config = config
        self.logger = logger or logging.getLogger('mail_sync.export')
        self.ev_client = EasyVereinClient(config.easyverein, self.logger)
    
    def export_emails_txt(self, output_path: Optional[Path] = None) -> Path:
        """
        Exportiert E-Mail-Adressen in eine einfache Textdatei.
        
        Eine E-Mail pro Zeile - ideal zum Kopieren in Strato.
        
        Args:
            output_path: Optionaler Ausgabepfad
            
        Returns:
            Pfad zur erstellten Datei
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"emails_{timestamp}.txt")
        
        self.logger.info("Rufe E-Mail-Adressen aus EasyVerein ab...")
        emails = self.ev_client.get_active_member_emails()
        
        # Sortiert schreiben
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# EasyVerein E-Mail-Export vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
            f.write(f"# Anzahl aktiver Mitglieder: {len(emails)}\n")
            f.write("#\n")
            f.write("# Diese E-Mail-Adressen sollten in Strato als Weiterleitung eingetragen sein:\n")
            f.write("#\n\n")
            
            for email in sorted(emails):
                f.write(f"{email}\n")
        
        self.logger.info(f"✅ {len(emails)} E-Mail-Adressen exportiert nach: {output_path}")
        return output_path
    
    def export_members_csv(self, output_path: Optional[Path] = None) -> Path:
        """
        Exportiert Mitglieder mit Details in eine CSV-Datei.
        
        Args:
            output_path: Optionaler Ausgabepfad
            
        Returns:
            Pfad zur erstellten Datei
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"mitglieder_{timestamp}.csv")
        
        self.logger.info("Rufe Mitgliederdetails aus EasyVerein ab...")
        members = self.ev_client.get_members_details()
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['Mitgliedsnummer', 'Vorname', 'Nachname', 'E-Mail'])
            
            for m in sorted(members, key=lambda x: x.email):
                writer.writerow([
                    m.membership_number or '',
                    m.first_name or '',
                    m.last_name or '',
                    m.email
                ])
        
        self.logger.info(f"✅ {len(members)} Mitglieder exportiert nach: {output_path}")
        return output_path
    
    def compare_with_file(self, strato_file: Path) -> dict:
        """
        Vergleicht EasyVerein-E-Mails mit einer Datei von Strato-Weiterleitungen.
        
        Die Strato-Datei sollte eine E-Mail pro Zeile enthalten.
        
        Args:
            strato_file: Pfad zur Datei mit Strato-E-Mails
            
        Returns:
            Dict mit Vergleichsergebnis
        """
        self.logger.info("Vergleiche EasyVerein mit Strato-Datei...")
        
        # EasyVerein E-Mails holen
        ev_emails = self.ev_client.get_active_member_emails()
        
        # Strato-Datei einlesen
        strato_emails: Set[str] = set()
        with open(strato_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip().lower()
                # Kommentare und leere Zeilen überspringen
                if line and not line.startswith('#') and '@' in line:
                    strato_emails.add(line)
        
        # Vergleich
        to_add = ev_emails - strato_emails
        to_remove = strato_emails - ev_emails
        unchanged = ev_emails & strato_emails
        
        result = {
            'easyverein_count': len(ev_emails),
            'strato_count': len(strato_emails),
            'to_add': sorted(to_add),
            'to_remove': sorted(to_remove),
            'unchanged': sorted(unchanged),
        }
        
        # Report ausgeben
        self._print_comparison_report(result)
        
        return result
    
    def _print_comparison_report(self, result: dict):
        """Gibt den Vergleichsreport aus."""
        print("\n" + "=" * 60)
        print("VERGLEICHSREPORT: EasyVerein ↔ Strato")
        print("=" * 60)
        
        print(f"\nEasyVerein (Source of Truth): {result['easyverein_count']} E-Mails")
        print(f"Strato-Datei:                 {result['strato_count']} E-Mails")
        print(f"Übereinstimmend:              {len(result['unchanged'])} E-Mails")
        
        if result['to_add']:
            print(f"\n🟢 IN STRATO HINZUZUFÜGEN ({len(result['to_add'])}):")
            print("   (Diese E-Mails sind in EasyVerein aber NICHT in Strato)")
            for email in result['to_add']:
                print(f"   + {email}")
        
        if result['to_remove']:
            print(f"\n🔴 AUS STRATO ZU ENTFERNEN ({len(result['to_remove'])}):")
            print("   (Diese E-Mails sind in Strato aber NICHT mehr in EasyVerein)")
            for email in result['to_remove']:
                print(f"   - {email}")
        
        if not result['to_add'] and not result['to_remove']:
            print("\n✨ Perfekt synchron! Keine Änderungen nötig.")
        
        print("\n" + "=" * 60 + "\n")


def main():
    """Standalone-Export ausführen."""
    import argparse
    from config import load_config, setup_logging
    
    parser = argparse.ArgumentParser(description="EasyVerein E-Mail-Export")
    parser.add_argument('--csv', action='store_true', help='Als CSV mit Details exportieren')
    parser.add_argument('--compare', type=Path, help='Mit Strato-Datei vergleichen')
    parser.add_argument('--output', '-o', type=Path, help='Ausgabedatei')
    parser.add_argument('--debug', action='store_true', help='Debug-Ausgaben')
    
    args = parser.parse_args()
    
    config = load_config()
    logger = setup_logging('DEBUG' if args.debug else config.log_level)
    
    exporter = EmailExporter(config, logger)
    
    if args.compare:
        exporter.compare_with_file(args.compare)
    elif args.csv:
        exporter.export_members_csv(args.output)
    else:
        exporter.export_emails_txt(args.output)


if __name__ == "__main__":
    main()
