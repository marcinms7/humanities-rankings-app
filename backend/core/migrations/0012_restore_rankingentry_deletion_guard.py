from django.db import migrations


def restore_guard(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        schema_editor.execute(
            "CREATE TRIGGER IF NOT EXISTS protect_core_rankingentry_deletion "
            "BEFORE DELETE ON core_rankingentry "
            "WHEN EXISTS (SELECT 1 FROM core_ranking WHERE id = OLD.ranking_id AND origin <> 'personal') "
            "BEGIN SELECT RAISE(ABORT, 'Shared records must be archived, not deleted'); END"
        )
    elif schema_editor.connection.vendor != 'postgresql':
        raise RuntimeError('Deletion guards require SQLite or PostgreSQL.')


class Migration(migrations.Migration):
    dependencies = [('core', '0011_rankingentry_groupings')]

    operations = [migrations.RunPython(restore_guard, migrations.RunPython.noop)]
