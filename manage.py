#!/usr/bin/env python3
"""Local administrator commands; no public registration or administrative routes."""
import argparse
import csv
import json
import os
from pathlib import Path
import sqlite3

from wedding.store import connect, details, initialize, invitation, revoke, validate_details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("WEDDING_DATA_DIR", "/var/lib/weronikarafal-data")))
    commands = parser.add_subparsers(dest="command", required=True)
    invite = commands.add_parser("invite", help="Add an invitation; prints its code once.")
    invite.add_argument("name")
    invite.add_argument("--companion", action="store_true")
    commands.add_parser("list", help="List invitation IDs and response statuses, never codes.")
    for command in ("revoke", "rotate"):
        sub = commands.add_parser(command)
        sub.add_argument("guest_id")
    for command in ("set-details", "export-rsvp", "backup"):
        sub = commands.add_parser(command)
        sub.add_argument("file", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    database = args.data_dir / "guests.sqlite3"
    initialize(database)
    with connect(database) as db:
        if args.command == "invite":
            guest_id, code = invitation(db, args.name, args.companion)
            print("Invitation ID:", guest_id)
            print("Private code (share only with this guest):", code)
        elif args.command == "list":
            for row in db.execute("""SELECT guests.id, guests.name, guests.active, rsvps.attendance
                FROM guests LEFT JOIN rsvps ON guests.id=rsvps.guest_id ORDER BY guests.name"""):
                print(row["id"], row["name"], "active" if row["active"] else "revoked", row["attendance"] or "pending", sep="\t")
        elif args.command in {"revoke", "rotate"}:
            guest = db.execute("SELECT * FROM guests WHERE id=?", (args.guest_id,)).fetchone()
            if not guest:
                parser.error("Unknown invitation ID.")
            if args.command == "revoke":
                revoke(db, args.guest_id)
                print("Invitation revoked; all its sessions were invalidated.")
            else:
                _, code = invitation(db, guest["name"], guest["allows_companion"], args.guest_id)
                print("New private code (old code and sessions invalidated):", code)
        elif args.command == "set-details":
            data = validate_details(json.loads(args.file.read_text()))
            temporary = args.data_dir / "details.json.next"
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
            temporary.chmod(0o600)
            temporary.replace(args.data_dir / "details.json")
            print("Details updated. Ceremony is public; all other details require login.")
        elif args.command == "export-rsvp":
            rows = db.execute("""SELECT guests.name, rsvps.attendance, rsvps.companion_name,
                rsvps.diet, rsvps.lodging, rsvps.notes, rsvps.updated_at FROM guests
                LEFT JOIN rsvps ON guests.id=rsvps.guest_id WHERE guests.active=1 ORDER BY guests.name""")
            def cell(value):
                # Avoid spreadsheet formula execution when opening untrusted names or notes.
                text = "" if value is None else str(value)
                return "'"+text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text
            with args.file.open("x", newline="") as output:
                args.file.chmod(0o600)
                writer = csv.writer(output)
                writer.writerow([column[0] for column in rows.description])
                writer.writerows([[cell(value) for value in row] for row in rows])
            print("Private export written:", args.file)
        elif args.command == "backup":
            # SQLite backup includes committed WAL data; never copy a live SQLite file alone.
            with args.file.open("xb"):
                pass
            args.file.chmod(0o600)
            with sqlite3.connect(args.file) as backup:
                db.backup(backup)
            print("Private SQLite backup written:", args.file)


if __name__ == "__main__":
    main()
