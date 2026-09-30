"""Freeze current assumptions on upgrades; never claim historical verification."""
from django.db import migrations
from django.utils import timezone


def freeze(apps, schema_editor):
    alias = schema_editor.connection.alias
    Library = apps.get_model('core', 'LibraryItem')
    Attempt = apps.get_model('core', 'ReadingAttempt')
    Plan = apps.get_model('core', 'PlanItem')
    fields = ('pages', 'word_count', 'pages_basis', 'pages_source_url', 'isbn', 'language', 'translator', 'publisher', 'abridged')

    def basis(edition):
        return {'edition_id': edition.pk if edition else None,
                **{field: getattr(edition, field, None) for field in fields},
                'origin': 'current_metadata_at_upgrade_not_historical_verification',
                'captured_at': timezone.now().isoformat()}

    for model in (Library, Attempt):
        for row in model.objects.using(alias).filter(reading_basis={}).select_related('edition', 'work__default_edition').iterator():
            edition = row.edition or (row.work.default_edition if model is Library else None)
            model.objects.using(alias).filter(pk=row.pk).update(reading_basis=basis(edition))
    for row in Plan.objects.using(alias).filter(reading_basis={}).select_related('work__default_edition').iterator():
        library = Library.objects.using(alias).filter(user_id=row.user_id, work_id=row.work_id).first()
        saved = dict(library.reading_basis) if library else basis(row.work.default_edition)
        # Frozen v1 planning factors; physical allocation is deliberately untouched.
        multiplier = row.work.reading_effort_override
        if multiplier is None:
            multiplier = {'leisure': 1.0, 'classic_literature': 1.5, 'demanding_literature': 2.0, 'philosophy': 2.5}[row.work.reading_load]
        if saved.get('pages') and saved.get('word_count'):
            multiplier *= saved['word_count'] / saved['pages'] / 300
        saved.update(effort_multiplier=multiplier, allocated_at=timezone.now().isoformat())
        Plan.objects.using(alias).filter(pk=row.pk).update(reading_basis=saved)


class Migration(migrations.Migration):
    dependencies = [('core', '0014_reading_basis_and_metadata_provenance')]
    operations = [migrations.RunPython(freeze, migrations.RunPython.noop)]
