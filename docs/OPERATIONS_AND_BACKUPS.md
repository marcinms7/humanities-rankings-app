# Operations, backups and portable exports

Implemented 29 September 2026. These are local reliability tools; the prepared PostgreSQL/hosted stack still requires its own rehearsal. Existing databases, original media, archive flags and deletion guards remain authoritative.

## Incremental local backups

Run `.venv/bin/python manage.py backup_local`, or add `--daily` to reuse that UTC day's completed snapshot. The command preserves the existing SQLite/media pairs and their names. New snapshots contain:

- `<name>.sqlite3`: SQLite's consistent online database snapshot, with all application tables and guards.
- `<name>.media.json`: a version 2 manifest mapping original relative media paths to SHA-256 objects and recording the database checksum.
- `<name>.complete`: the manifest checksum and completion time, written last through atomic replacement.
- `media-objects/<first-two-hash-characters>/<sha256>`: immutable, deduplicated media bytes shared by snapshots.

Original media files and old `.media.tar.gz` archives are not moved, converted or deleted. The first new backup copies each distinct media object once. Later backups reuse unchanged files using size, inode, device, mtime and ctime signatures; changed files are hashed and copied through restricted temporary files. Restoring or copying a snapshot verifies object checksums. Reused local objects are not rehashed on every backup; periodic restore drills detect corruption. Preserve the object store together with its manifests and databases.

The backup checks every image reference in its copied database against the saved media manifest. If a referenced file is missing or a media file keeps changing during copying, no completion marker is published. Live enrichment can continue: extra images created after the database snapshot may also be included, and mutable files are retried. Symlinks/special files are rejected rather than following data outside the media root. Partial attempts and previously completed snapshots remain available for diagnosis; no cleanup silently removes them.

`manage.py restore_drill NAME` restores into a fresh private temporary directory. It accepts both new object manifests and legacy tar archives, validates new checksums, and performs the existing integrity/foreign-key/deletion-guard/media checks. It never overwrites the live database. Restore production data only with the app stopped and a fresh snapshot of the current state.

## Daily schedule and additional copies

The app launcher still requests a daily backup. A macOS LaunchAgent can independently run the same command at 03:15 local time while the account is logged in, including after the computer wakes from sleep:

```bash
.venv/bin/python scripts/install_backup_schedule.py
# Review data/operations/org.marginalia.daily-backup.plist, then install:
.venv/bin/python scripts/install_backup_schedule.py --install
```

Use `--hour H --minute M` to choose another time. The installer preserves the resolved SQLite database, media root and Django settings module. It records a copy destination only when one was explicitly supplied. Installing writes `~/Library/LaunchAgents/org.marginalia.daily-backup.plist` and loads that job; rendering the candidate alone does not schedule anything or run a backup. This is a per-user logged-in schedule, not a machine-wide daemon. On other operating systems, schedule `.venv/bin/python manage.py backup_local --daily` from the project directory using the system scheduler and the same database/media environment. PostgreSQL needs `pg_dump`/managed snapshots plus media backups instead.

Set an existing mounted external/remote destination explicitly:

```bash
MARGINALIA_BACKUP_COPY_DIR=/path/to/mounted/backup-directory .venv/bin/python manage.py backup_local
.venv/bin/python scripts/install_backup_schedule.py --copy-destination /path/to/mounted/backup-directory --install
```

The directory must already exist, so an absent mount is not silently replaced with a new local folder. Copies use temporary files, checksum verification and a completion marker written last. Objects already copied are reused after checksum comparison. A copy failure leaves the completed local snapshot intact, records `copy_failed` in `data/backups/backup-status.json`, and returns an error. Retrying `--daily` retries the copy of the already completed snapshot. No destination has been selected by the software. The operations screen flags a destination detected on the same filesystem; network mounts may require independent verification that they provide the intended separate-device protection. Files are copied as private plaintext backups; use an encrypted destination if required. No passwords or remote-account credentials are stored in scheduler configuration.

## Retention and storage

`.venv/bin/python manage.py backup_retention` produces a JSON **dry run** retaining all manual/non-daily snapshots, the newest completed snapshot per recognized database, and proposed daily/weekly/monthly recovery points. Defaults are 14 days, 8 weeks and 12 months; options are `--daily-days`, `--weekly-weeks`, `--monthly-months`. The command never deletes anything. Shared objects remain fully retained even when an old manifest would fall outside the proposal. Removing individual objects can break multiple snapshots, so ordinary manual pruning should not touch that store. Original media are never retention targets.

## Staff operations and request timing

The staff-only `#/operations` screen and `GET /api/operations/` show latest completed backup age, last backup/copy result, schedule-file presence, free disk space, worker status, provider cooldowns, queue state counts and recent request timing. Storage scans are cached for 60 seconds. Presence of a scheduler file does not prove a successful scheduled run; backup age and the last attempt are shown separately. Raw filesystem paths, request bodies, query strings, SQL text, credentials and account notes are omitted.

`OperationalTelemetryMiddleware` keeps at most 300 API/health request samples in each application process. It records a generated request ID, the resolved route pattern, method/status, preparation time, query count/SQL execution time and response size when known. Streaming download transfer time is excluded. Only the slowest 30 route summaries and 15 recent slow/failed samples are returned. Slow/error logs are capped at 10 per minute per process. `X-Request-ID` is returned for correlation; `Server-Timing` is supplied only to staff or when Django DEBUG is enabled. Set `MARGINALIA_TELEMETRY=0` to disable capture. Samples reset on restart and are not global across Gunicorn workers; no private telemetry database is created.

Future worker starts write status and provider cooldown files through atomic replacement. The supervisors publish heartbeats while waiting for child workers. Existing running processes are deliberately not restarted by this software update, so they may show no heartbeat until their next start. An unreadable saved cooldown keeps requests paused rather than bypassing the provider limit. The app displays process presence as a separate hint; a saved PID alone is not proof of healthy progress. These views do not start, stop or duplicate workers.

## Private export memory

Both JSON and ZIP downloads now use restricted temporary files, closed and removed with the response. Rows and personal-list revisions are written incrementally; ZIP members copy from disk in bounded chunks. One database snapshot covers all exported sections. Catalog reference ID sets are retained, and queries for referenced metadata use bounded batches. The compatibility study-state document is reconstructed per profile using `load_state`; the largest reconstructed profile or individual revision remains an explicit memory bound. Normalized `study_records` are also exported individually, preserving every stored value and revision number.

The file names and export version 2 shape remain compatible, with the additional `study_records` section. JSON downloads are now streaming file responses. `build_private_export` remains a materializing compatibility helper for programmatic callers; the download endpoint uses the streaming writer. These exports remain portable reading-data archives, not an automatic application restore package.

## Verification boundary

The owner subsequently authorized isolated regression suites and recovery verification as part of technical item 7. The [selected follow-up receipt](SELECTED_IMPROVEMENTS_2026_09_29.md) records passing checks and an isolated restore verifying 6,884 media files, integrity, foreign keys and eight deletion guards. The existing LaunchAgent completed with exit code 0 when triggered through the scheduler; a natural 03:15 execution was not observed. No browser automation or off-device copy was performed. The external destination remains unconfigured; PostgreSQL/hosted recovery remains separate work.
