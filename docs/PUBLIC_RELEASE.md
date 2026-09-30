# Public-release preparation

The local app continues to use `data/db.sqlite3`. The deployment files are prepared, but no hosting account, domain, SMTP service, PostgreSQL server, or public deployment has been provisioned. The production stack has not been run here: Docker/PostgreSQL binaries are unavailable.

## Prepared features

- `compose.production.yaml`: PostgreSQL 17, Gunicorn, Caddy, persistent database/certificate volumes, and the existing `media/` tree mounted persistently. Caddy serves media files directly; Django continues to accept permissioned image uploads. Uploaded file keys and attribution remain unchanged. This is hosted filesystem storage, not an object-storage integration.
- `deploy/Caddyfile`: automatic HTTPS for the selected domain, proxying to a non-public application port, and access logs.
- `/accounts/register/`: configurable registration with password validation, inactive accounts until email activation, and no staff privilege. Registration is disabled until `PUBLIC_REGISTRATION=1` and SMTP is configured.
- `/accounts/password-reset/`: Django's expiring password reset flow and generic recovery response. The login form links to both account pages. The existing owner must have a correct email set in Django admin to use email recovery; local terminal recovery remains available.
- Database-backed limits on login, registration and recovery requests. They use the socket peer locally; in the supplied private proxy topology Caddy overwrites `X-Real-IP`, and the app trusts that header only when `TRUST_HTTPS_PROXY=1`. Do not expose the application port directly or enable this trust behind an unconfigured proxy. Add edge limits before a wider launch.
- `/health/live/` and `/health/ready/`: application liveness and database/frontend readiness. Configure an external monitor to alert on non-200 responses; connecting an alert destination is still required. Application and proxy logs go to stdout. Do not log request bodies or private export contents.
- HTTPS redirects, secure session/CSRF cookies, same-origin referrers, configurable HSTS, production secret requirement, and trusted-proxy handling enabled only by configuration.

Deployment settings follow the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/). Recovery uses [Django authentication views](https://docs.djangoproject.com/en/5.2/topics/auth/default/#using-the-views).

## Transfer and launch procedure

1. Choose a host with Docker, a domain, SMTP sender, and off-host backup storage. Point DNS at the host. Provision `.env.production` from `deploy/production.env.example` with actual secrets and the domain. This private file is ignored by Git. Use distinct random application/database secrets; do not use example values.
2. Enter a maintenance window for final transfer: stop local web writes and all research/import processes, then run `manage.py backup_local`. Keep the resulting database/media pair off-host as well as locally. Earlier live backups may precede concurrent additions.
3. Export from that frozen SQLite backup, never a database still receiving research writes:

   ```bash
   SQLITE_PATH=/absolute/path/to/backup.sqlite3 .venv/bin/python manage.py transfer_data export data/transfer-final
   ```

   The new directory contains private account hashes, notes, history, revisions and catalog data. It is created with private permissions. Keep it out of Git and transfer securely with the paired media archive. The export preserves application IDs and uses natural references for auth permissions. Sessions and admin activity logs are not transferred; sign in again after cutover.

4. On the destination, start only the database and initialize the schema:

   ```bash
   docker compose --env-file .env.production -f compose.production.yaml up -d db
   docker compose --env-file .env.production -f compose.production.yaml run --rm app python manage.py migrate
   ```

5. Mount the securely transferred bundle and import before opening the web service:

   ```bash
   docker compose --env-file .env.production -f compose.production.yaml run --rm -v /absolute/private/transfer-final:/transfer:ro app python manage.py transfer_data import /transfer
   ```

   Import refuses a nonempty application database, runs atomically, and compares IDs, concrete fields, relationships and counts before committing. The PostgreSQL execution and cross-engine constraints still require a destination rehearsal. Never disable shared deletion guards or clear the destination to force an import.

6. Restore the paired media archive to the destination's `media/` directory. Give the application container's user write access and Caddy read access. Check every referenced cover/portrait and file checksums. Start the full stack only after data and media reconciliation:

   ```bash
   docker compose --env-file .env.production -f compose.production.yaml up -d
   docker compose --env-file .env.production -f compose.production.yaml exec app python manage.py check --deploy
   ```

7. Verify HTTPS, login with the preserved owner account, media loading, registration activation, expired links, password recovery, health alarms and private access boundaries. Browser verification belongs to the owner unless automated testing is explicitly requested. Keep registration closed until actual email delivery works.
8. Take scheduled `pg_dump` backups plus synchronized media archives, copy them off-host, and rehearse a PostgreSQL restore into a separate database. Retain the frozen SQLite snapshot for rollback. Never allow both installations to accept writes during cutover.

Routine maintenance: run `clearsessions`; remove expired `AuthRateLimit` rows (only this operational table), rotate logs, monitor disk/database capacity, and review failed mail delivery. Choose retention and alert recipients before public launch. The local SQLite backup command does not back up PostgreSQL.

## Completed local restoration drill

`manage.py restore_drill BACKUP_STEM` restores into a new private temporary directory. It checks database integrity, foreign keys, all eight deletion guards, every referenced cover/portrait, and SHA-256 equivalence for restored media bytes. It never restores over the live application. Keep `report.json` with the backup's audit records; the temporary restored directory contains private data and should be handled accordingly.

On 13 September 2026 the final-schema drill succeeded for `manual-20260913T191316041795Z`, verifying 875 media files, one preserved owner and one library item. Its report is in `/private/var/folders/0s/rytptdq55bz5n5yq2sqcd61m0000gn/T/marginalia-restore-fspjpkib/report.json`. This validates that snapshot's SQLite/media recovery, not a PostgreSQL restore or public deployment. A private portable export of the snapshot is at `data/transfer-20260913-library-v2-final/`; it includes the matching migration manifest and must be refreshed at actual cutover because research is still adding records.

The production settings check currently reports W005/W021: HSTS include-subdomains and preload remain disabled until the chosen domain's subdomain policy is known. HTTPS redirect, secure cookies and one-hour HSTS are enabled in production. Do not blindly enable preload for an undecided domain.

Local reliability was extended on 29 September with incremental SQLite/media snapshots, a daily macOS schedule, configurable verified copies and staff Operations; see [the implementation record](TECHNICAL_IMPROVEMENTS_2026_09_29.md). No external destination is configured yet. These changes do not establish a PostgreSQL restore rehearsal or a public deployment. `restore_drill` now also accepts version 2 media manifests and shared objects; that new path has saved regressions but no fresh rehearsal in this iteration.
