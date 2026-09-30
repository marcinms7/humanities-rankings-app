# Persistent data and recovery

The application has one authoritative database: `data/db.sqlite3` for the direct local launch, PostgreSQL for Compose/hosting. Shared works, people, editions, tags, source evidence and editorial rankings live there. Each reader's bookmarks, personal lists, notes, library, plan and settings also live there, with user ownership and authenticated query restrictions. They are not stored in a disposable browser cache or separate per-user database. Closing the browser or stopping the server does not remove them; signing in restores access. Theme is also cached locally to avoid a flash of the wrong appearance.

## Deletion safeguards

- Catalog API DELETE requests are denied, including for staff. Shared rankings and their entries cannot be deleted through the reader API.
- Admin uses archive flags for catalog records, sources, rankings and entries, with delete/bulk-delete controls disabled. Archives can be restored by clearing `is_archived`.
- Django pre-delete guards prevent ORM and cascade deletion of shared records and shared ranking revisions.
- Migration `0003_shared_deletion_guards` installs database DELETE triggers for SQLite and PostgreSQL, including direct SQL deletes. Personal rankings/entries/revisions are exempt so readers can manage their own lists. Removing a library item or monthly allocation does not remove its shared work.
- Archived catalog items/rankings are hidden from discovery; archived sources stop contributing to eligible counts. Existing references and revision history remain. Archiving a work does not erase it from a reader's saved library or past source snapshots.

These safeguards prevent ordinary accidental deletion, not a database administrator dropping tables, removing triggers, truncating PostgreSQL tables, deleting files/volumes, or losing a disk. Do not describe the database as indestructible. Future schema migrations that rebuild SQLite tables must explicitly preserve/reinstall their custom triggers; inspect `0003` before changing protected tables. Never disable guards just to make a research import easier. Archive stale records and keep stable IDs and provenance. PostgreSQL trigger definitions are supplied but have not been exercised here.

## Backups

`scripts/run_local.sh` and setup save one daily SQLite backup before migrations when a local database already exists. A separate daily macOS LaunchAgent can run independently of startup; render/install it with `scripts/install_backup_schedule.py` as described in [operations and backups](OPERATIONS_AND_BACKUPS.md). Backup writers hold an exclusive lock so simultaneous starts cannot overwrite the same snapshot. An explicitly selected alternate `SQLITE_PATH` receives a distinct daily marker. No automatic pruning is enabled. Create an additional snapshot at any time:

```bash
.venv/bin/python manage.py backup_local
```

The command uses SQLite's online backup API and stores new media snapshots as checksummed manifests referencing deduplicated `data/backups/media-objects/` files. Unchanged media are reused; original files and old tar backups remain untouched. A `.complete` marker is written only after the database, manifest and every referenced media file are present. New backups are checked against image references in the copied database; mutable media are retried if they change during copying. These backups share the same disk unless an additional destination was explicitly configured. Set `MARGINALIA_BACKUP_COPY_DIR` to an existing mounted destination for atomic checksum-verified copies; a failed copy preserves the local snapshot and records the failure. No destination is guessed. `data/`, `media/` and credentials are gitignored and must remain private. Research JSON files do not contain all catalog/private data and are not a database backup.

To rehearse a restore, use `manage.py restore_drill NAME`: it accepts both version 2 manifests/objects and older paired media tar archives, always restoring into a fresh private directory. For an actual restore, stop the server, save a fresh copy of the current database/media, restore the chosen `.sqlite3` and its matching restored media tree, then start the app. Do not restore over a live database. Preserve the entire shared object store with its manifests: removing an object can damage multiple snapshots. `manage.py backup_retention` prints a dry-run proposal and never deletes anything; manual snapshots are always protected. For PostgreSQL use `pg_dump` or managed backups plus media backups; a deliberate data migration is needed when moving from SQLite. A SQLite/media restore rehearsal succeeded on 13 September 2026 for its dated snapshot; see [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md). PostgreSQL restoration and a fresh deployment rehearsal remain public-launch tasks.

## Private portable export

Unsaved writing now has optional browser-local recovery copies, separated by account and editor. These supplement saved database records; they are not a separate authoritative library. Profile can disable recovery or clear copies for that account. Copies survive sign-out on this device, are not encrypted/synced, and are excluded from database backups and account exports until the writing is saved normally. See [draft recovery](SEARCH_DRAFTS_CALENDAR_2026_09_29.md).

Profile offers a complete private JSON export and ZIP archive (`/api/export/?download=zip`). These include reading and study records, saved history/revisions, carryover receipts, named discovery filters and catalog references, with a versioned manifest. Passwords, sessions, active sharing tokens, other readers' data and media bytes are excluded. See [export scope](APP_IMPROVEMENTS_2026_09_28.md#full-private-export). Unsaved browser drafts are not included. This portable archive does not implement automatic restoration and does not replace database/media backups.

## Forgotten local password

Django already stores salted password hashes. There is no retrievable original password and no plaintext password file. With terminal access to this checkout and its database, set a new password:

```bash
bash scripts/reset_password.sh YOUR_USERNAME
```

Omit the username to be prompted. The script invokes Django's interactive `changepassword` command and asks for the new password twice without echoing it or placing it in shell history. It changes only that account's password; saved lists, library, plans and preferences remain. Existing sessions may require signing in again. No password was changed as part of implementing this script.

Use the same database environment as the running app. `SQLITE_PATH` can select a different local file; exported `POSTGRES_*` variables select PostgreSQL. Plain commands do not automatically load `.env`. Forgotten usernames can be inspected locally with `manage.py shell`; do not print password hashes or other private data to a chat. Registration is implemented behind `PUBLIC_REGISTRATION`; SMTP delivery and hosted email recovery still require deployment configuration and verification. Password hashing is already implemented and must not be postponed or replaced with plaintext storage.
