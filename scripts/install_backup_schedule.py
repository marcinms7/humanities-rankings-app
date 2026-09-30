#!/usr/bin/env python3
"""Render a macOS daily backup LaunchAgent; install only with --install."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'org.marginalia.daily-backup'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Install the reviewed LaunchAgent and load its daily schedule.')
    parser.add_argument('--hour', type=int, default=3)
    parser.add_argument('--minute', type=int, default=15)
    parser.add_argument('--copy-destination', help='Existing mounted/external directory for verified copies; never guessed.')
    args = parser.parse_args()
    if not 0 <= args.hour <= 23 or not 0 <= args.minute <= 59:
        parser.error('Choose a valid local hour and minute.')
    runtime = subprocess.run([str(ROOT / '.venv/bin/python'), '-c',
        "import json,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings'); from django.conf import settings; print(json.dumps({'engine':settings.DATABASES['default']['ENGINE'],'database':str(settings.DATABASES['default']['NAME']),'media':str(settings.MEDIA_ROOT)}))"],
        cwd=ROOT, check=True, capture_output=True, text=True)
    configured = json.loads(runtime.stdout)
    if configured['engine'] != 'django.db.backends.sqlite3':
        parser.error('This schedule is for the local SQLite installation; configure PostgreSQL backups separately.')
    directory = ROOT / 'data/operations'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    def configured_path(value):
        path = Path(value).expanduser()
        return str((path if path.is_absolute() else ROOT / path).resolve())
    environment = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'SQLITE_PATH': configured_path(configured['database']),
                   'MEDIA_ROOT': configured_path(configured['media']),
                   'DJANGO_SETTINGS_MODULE': os.getenv('DJANGO_SETTINGS_MODULE', 'backend.config.settings')}
    destination = args.copy_destination or os.getenv('MARGINALIA_BACKUP_COPY_DIR')
    if destination:
        destination = str(Path(destination).expanduser().resolve())
        if not Path(destination).is_dir():
            parser.error('Mount or create the selected copy destination before configuring the schedule.')
        environment['MARGINALIA_BACKUP_COPY_DIR'] = destination
    payload = {'Label': LABEL, 'ProgramArguments': [str(ROOT / '.venv/bin/python'), str(ROOT / 'manage.py'), 'backup_local', '--daily'],
               'WorkingDirectory': str(ROOT), 'EnvironmentVariables': environment,
               'StartCalendarInterval': {'Hour': args.hour, 'Minute': args.minute}, 'RunAtLoad': False,
               'StandardOutPath': str(directory / 'scheduled-backup.log'), 'StandardErrorPath': str(directory / 'scheduled-backup-errors.log')}
    candidate = directory / f'{LABEL}.plist'
    candidate.write_bytes(plistlib.dumps(payload)); candidate.chmod(0o600)
    print(f'Reviewable schedule saved: {candidate}')
    if not args.install:
        print('Not installed. Review the plist, then rerun with --install to enable daily backups independently of app startup.')
        return
    if sys.platform != 'darwin':
        parser.error('This installer supports macOS LaunchAgents. Use a daily system scheduler with manage.py backup_local --daily on other platforms.')
    installed = Path.home() / 'Library/LaunchAgents' / candidate.name
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.write_bytes(candidate.read_bytes()); installed.chmod(0o600)
    domain = f'gui/{os.getuid()}'
    subprocess.run(['launchctl', 'bootout', f'{domain}/{LABEL}'], check=False, capture_output=True)
    subprocess.run(['launchctl', 'bootstrap', domain, str(installed)], check=True)
    print(f'Daily schedule installed for {args.hour:02}:{args.minute:02} local time. It runs while the account is logged in and catches missed calendar runs after sleep.')


if __name__ == '__main__':
    main()
