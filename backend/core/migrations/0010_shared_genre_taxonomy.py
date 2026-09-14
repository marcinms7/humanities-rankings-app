from django.db import migrations, models


GENRES = [
    'Action', 'Adventure', 'Arts & Artists', 'Autobiographical', "Boys' Love", "Children's", 'Comedy', 'Coming of Age',
    'Crime', 'Cyberpunk', 'Dark Fantasy', 'Drama', 'Dystopian', 'Ecchi', 'Erotica', 'Fantasy', 'Food',
    'Family', 'Gekiga', "Girls' Love", 'Gothic', 'Historical Fiction', 'Horror', 'Isekai', 'Literary Fiction',
    'Magical Girl', 'Magical Realism', 'Martial Arts', 'Mecha', 'Music', 'Mystery', 'Myth & Folklore',
    'Performing Arts', 'Post-Apocalyptic', 'Psychological', 'Romance', 'Satire', 'School Life', 'Science Fiction',
    'Slice of Life', 'Sports', 'Superhero', 'Supernatural', 'Surrealism', 'Thriller', 'War', 'Western', 'Workplace',
]


def seed_genres(apps, schema_editor):
    Tag = apps.get_model('core', 'Tag')
    for name in GENRES:
        Tag.objects.get_or_create(name=name, defaults={'kind': 'genre'})


class Migration(migrations.Migration):
    dependencies = [('core', '0009_rankingentry_rank_entry_work_live_pos')]

    operations = [
        migrations.AddIndex(
            model_name='tag',
            index=models.Index(fields=['kind', 'name'], name='tag_kind_name_idx'),
        ),
        migrations.RunPython(seed_genres, migrations.RunPython.noop),
    ]
