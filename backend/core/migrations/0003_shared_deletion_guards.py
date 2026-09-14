from django.db import migrations
from django.db.models import F


GUARDS = {
    'core_person': None,
    'core_work': None,
    'core_edition': None,
    'core_tag': None,
    'core_researchsource': None,
    'core_ranking': "OLD.origin <> 'personal'",
    'core_rankingentry': "EXISTS (SELECT 1 FROM core_ranking WHERE id = OLD.ranking_id AND origin <> 'personal')",
    'core_rankingrevision': "EXISTS (SELECT 1 FROM core_ranking WHERE id = OLD.ranking_id AND origin <> 'personal')",
}


def preserve_pace(apps, schema_editor):
    # Preserve the old calendar-day budget when making weekly targets the default.
    apps.get_model('core', 'User').objects.using(schema_editor.connection.alias).update(
        pages_per_week=F('pages_per_day') * 7, pages_per_month=F('pages_per_day') * 30)


def install_guards(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    for table, condition in GUARDS.items():
        name = f'protect_{table}_deletion'
        if vendor == 'sqlite':
            when = f' WHEN {condition}' if condition else ''
            schema_editor.execute(f"CREATE TRIGGER {name} BEFORE DELETE ON {table}{when} BEGIN SELECT RAISE(ABORT, 'Shared records must be archived, not deleted'); END")
        elif vendor == 'postgresql':
            body = "RAISE EXCEPTION 'Shared records must be archived, not deleted';"
            if condition:
                body = f'IF {condition} THEN {body} END IF;'
            schema_editor.execute(f'CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {body} RETURN OLD; END; $$')
            schema_editor.execute(f'CREATE TRIGGER {name} BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {name}()')
        else:
            raise RuntimeError('Deletion guards require SQLite or PostgreSQL.')


def remove_guards(apps, schema_editor):
    for table in GUARDS:
        name = f'protect_{table}_deletion'
        if schema_editor.connection.vendor == 'sqlite':
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {name}')
        elif schema_editor.connection.vendor == 'postgresql':
            schema_editor.execute(f'DROP TRIGGER IF EXISTS {name} ON {table}')
            schema_editor.execute(f'DROP FUNCTION IF EXISTS {name}()')


class Migration(migrations.Migration):
    dependencies = [('core', '0002_flexible_reading_and_archives')]
    operations = [migrations.RunPython(preserve_pace, migrations.RunPython.noop),
                  migrations.RunPython(install_guards, remove_guards)]
