"""Read-only retention proposal. Manual snapshots and original media are retained."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from backend.core.local_backups import read_json


def retention_proposal(directory, daily_days=14, weekly_weeks=8, monthly_months=12, now=None):
    directory = Path(directory)
    now = now or datetime.now(timezone.utc)
    snapshots = []
    for marker in directory.glob('*.complete'):
        metadata = read_json(marker)
        try:
            stamp = datetime.fromisoformat(metadata.get('created_at', ''))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        except ValueError:
            stamp = datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc)
        stem = marker.with_suffix('')
        manifest = read_json(stem.with_suffix('.media.json'))
        # Separate configured database paths never share a retention bucket.
        group = manifest.get('database_fingerprint') or ('legacy-' + stem.name[15:] if stem.name.startswith('daily-') and len(stem.name) > 14 else 'legacy-default')
        snapshots.append({'name': stem.name, 'created_at': stamp.isoformat(), '_time': stamp, '_group': group,
                          'snapshot_bytes': sum(path.stat().st_size for path in [stem.with_suffix(suffix) for suffix in ('.sqlite3', '.media.json', '.media.tar.gz', '.complete')] if path.exists())})
    snapshots.sort(key=lambda row: row['_time'], reverse=True)
    kept, proposed, groups, weeks, months = [], [], set(), set(), set()
    for row in snapshots:
        moment, group = row['_time'], row['_group']
        reason = None
        if not row['name'].startswith('daily-'):
            reason = 'Manual or non-daily snapshot: protected'
        elif group not in groups:
            reason = 'Newest completed snapshot for this database'
        elif moment >= now - timedelta(days=daily_days):
            reason = 'Recent daily snapshot'
        week = (group, moment.isocalendar()[:2])
        month = (group, moment.year, moment.month)
        if not reason and moment >= now - timedelta(weeks=weekly_weeks) and week not in weeks:
            reason = 'Weekly recovery point'
        if not reason and (now.year - moment.year) * 12 + now.month - moment.month < monthly_months and month not in months:
            reason = 'Monthly recovery point'
        groups.add(group)
        if reason:
            weeks.add(week); months.add(month)
        public = {key: value for key, value in row.items() if not key.startswith('_')}
        (kept if reason else proposed).append({**public, 'reason': reason or 'Outside proposed daily/weekly/monthly windows'})
    return {'dry_run': True, 'deleted': 0, 'policy': {'daily_days': daily_days, 'weekly_weeks': weekly_weeks, 'monthly_months': monthly_months},
            'keep': kept, 'proposed_removal': proposed, 'snapshot_bytes_proposed': sum(row['snapshot_bytes'] for row in proposed),
            'shared_objects': 'Retained in full. Removing a manifest never authorizes removal of shared media objects.',
            'manual_snapshots': 'Always protected. No command here performs deletion.'}


class Command(BaseCommand):
    help = 'Print a dry-run backup retention proposal. Never deletes snapshots, objects or original media.'

    def add_arguments(self, parser):
        parser.add_argument('--daily-days', type=int, default=14)
        parser.add_argument('--weekly-weeks', type=int, default=8)
        parser.add_argument('--monthly-months', type=int, default=12)

    def handle(self, *args, **options):
        values = {key: options[key] for key in ('daily_days', 'weekly_weeks', 'monthly_months')}
        if any(value < 1 or value > 1000 for value in values.values()):
            raise CommandError('Retention windows must be between 1 and 1000.')
        self.stdout.write(json.dumps(retention_proposal(settings.BASE_DIR / 'data/backups', **values), indent=2))
