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

`scripts/run_local.sh` and setup save one daily SQLite backup before migrations when a local database already exists. No automatic pruning is enabled. Create an additional snapshot at any time:

```bash
.venv/bin/python manage.py backup_local
```

The command uses SQLite's online backup API and archives `media/` into `data/backups/`, with restrictive file permissions. A `.complete` marker identifies a completed database/media pair. The database snapshot is consistent; avoid concurrent image changes if you need an exactly matching media snapshot. These backups share the same disk: copy them elsewhere for disk-loss protection. `data/`, `media/` and credentials are gitignored and must remain private. Research JSON files do not contain all catalog/private data and are not a database backup.

To restore: stop the server, save a fresh copy of the current database/media, restore the selected `.sqlite3` as `data/db.sqlite3` and its paired media archive, then start the app. Do not restore over a live database. For PostgreSQL use `pg_dump` or managed backups plus media backups; a deliberate data migration is needed when moving from SQLite. Restore rehearsals remain a public-launch task.

## Forgotten local password

Django already stores salted password hashes. There is no retrievable original password and no plaintext password file. With terminal access to this checkout and its database, set a new password:

```bash
bash scripts/reset_password.sh YOUR_USERNAME
```

Omit the username to be prompted. The script invokes Django's interactive `changepassword` command and asks for the new password twice without echoing it or placing it in shell history. It changes only that account's password; saved lists, library, plans and preferences remain. Existing sessions may require signing in again. No password was changed as part of implementing this script.

Use the same database environment as the running app. `SQLITE_PATH` can select a different local file; exported `POSTGRES_*` variables select PostgreSQL. Plain commands do not automatically load `.env`. Forgotten usernames can be inspected locally with `manage.py shell`; do not print password hashes or other private data to a chat. Public email-based recovery and public registration remain separate deployment work. Password hashing is already implemented and must not be postponed or replaced with plaintext storage.
