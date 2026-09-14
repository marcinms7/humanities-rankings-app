import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backend.core.models import Ranking


def definitions():
    common = {'origin': 'curated', 'presentation': 'ranked', 'item_type': 'work',
              'is_public': True, 'target_size': 200, 'status': 'awaiting_research'}
    rows = [
        ('books-all-time', 'Books · All time', 'all', {'forms': ['book'], 'subjects': 'all'}),
        ('literature-all-time', 'Literary fiction · All time', 'literature', {'forms': ['book'], 'literary_fiction_only': True}),
        ('nonfiction-all-time', 'Nonfiction · All time', 'nonfiction', {'forms': ['book']}),
        ('philosophy-books-all-time', 'Philosophy books · All time', 'philosophy', {'forms': ['book']}),
        ('philosophers-all-time', 'Philosophers · All time', 'philosophy', {'people_roles': ['philosopher']}),
        ('other-works-all-time', 'Most important literary works · All time', 'literature', {'forms': ['book', 'collection', 'essay', 'short_story', 'poem', 'play'], 'cross_form': True, 'ranking_purpose': 'historical_literary_importance', 'allow_unresolved_attribution': True}),
        ('poetry-all-time', 'Poetry · All time', 'poetry', {'forms': ['poem', 'collection', 'book'], 'poetry_only': True}),
    ]
    rows.append(('history-books-all-time', 'History books · All time', 'history',
                 {'forms': ['book'], 'subject': 'history', 'research_priority': 'queued_later'}))
    for slug, title, focus in [
        ('medieval', 'Medieval history', 'The medieval period across regions; avoid treating European period boundaries as universal.'),
        ('london', 'History of London', 'London across periods: urban, social, cultural, political and economic history.'),
        ('ancient-rome', 'Ancient Rome', 'Roman Republic and Empire, including social history, archaeology and institutions.'),
        ('ancient-greece', 'Ancient Greece', 'Greek societies and the Hellenistic world.'),
        ('world', 'World history', 'Comparative and connected histories across regions.'),
        ('social', 'Social history', 'Everyday life, communities, class, gender and social change.'),
    ]:
        rows.append((f'history-books-{slug}', f'{title} · Books', 'history',
                     {'forms': ['book'], 'subject': 'history', 'topic': slug,
                      'parent_ranking': 'history-books-all-time', 'research_priority': 'queued_later', 'focus': focus}))
    for form, label in [('short_story', 'Short stories'), ('essay', 'Essays'), ('poem', 'Poems'), ('play', 'Plays')]:
        rows.append((f'{form.replace("_", "-")}-all-time', f'{label} · All time', 'literature', {'forms': [form]}))
    manga_forms = ['book', 'collection']
    rows.append(('manga-all-time', 'Manga · All time', 'manga',
                 {'forms': manga_forms, 'field': 'manga',
                  'entry_scope': 'series_or_standalone_work_to_be_confirmed'}))
    rows.append(('comics-graphic-novels-all-time', 'Comics and graphic novels · All time', 'literature',
                 {'forms': ['book', 'collection'],
                  'media': ['comics', 'graphic_novels', 'manga', 'manhwa', 'manhua', 'comic_strips', 'wordless_novels'],
                  'manga_category_index_preserved': True,
                  'manga_categories_are': 'publication demographics/context, not genres or quality levels'}))
    rows.extend([
        ('classical-education-guide', 'Classical education · Guide', 'literature',
         {'forms': ['book', 'collection', 'essay', 'poem', 'play'], 'traditions': ['Greek', 'Latin'],
          'guide_scope': 'Greek and Latin texts across poetry, prose, philosophy, history, rhetoric and drama'}),
        ('books-addictive-all-time', 'Most addictive books · All time', 'all',
         {'forms': ['book'], 'theme': 'compulsive_reading', 'ranking_question': 'Books readers report being unable to put down.'}),
        ('books-funniest-all-time', 'Funniest books · All time', 'all',
         {'forms': ['book'], 'theme': 'humour', 'ranking_question': 'Books of exceptional comic force across traditions and genres.'}),
        ('books-mainstream-loved-all-time', 'Most mainstream-loved books · All time', 'all',
         {'forms': ['book'], 'theme': 'mainstream_love', 'ranking_question': 'Books with unusually broad, enduring mainstream reader affection.'}),
    ])
    for slug, label in [
        ('shonen', 'Shōnen'),
        ('shojo', 'Shōjo'),
        ('seinen', 'Seinen'),
        ('josei', 'Josei'),
    ]:
        rows.append((f'manga-{slug}-all-time', f'{label} manga · All time', 'manga',
                     {'forms': manga_forms, 'field': 'manga', 'manga_demographic': slug,
                      'category_kind': 'publishing_demographic', 'parent_ranking': 'manga-all-time'}))
    for slug, label in [('england', 'England'), ('ireland', 'Ireland'), ('scotland', 'Scotland'), ('china', 'China'), ('united-states', 'United States'), ('france', 'France'), ('japan', 'Japan'), ('poland', 'Poland')]:
        rows.append((f'books-{slug}', f'Books · {label}', 'literature',
                     {'forms': ['book'], 'country': label, 'association': 'documented_literary_cultural', 'english_edition_required': True}))
    for century in range(1, 22):
        suffix = 'th' if 10 <= century % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(century % 10, 'th')
        rows.append((f'books-century-{century}', f'Books · {century}{suffix} century', 'all',
                     {'forms': ['book'], 'year_from': (century - 1) * 100 + 1, 'year_to': century * 100,
                      'date_basis': 'original_composition_or_publication'}))
    for slug, label in [('epistemology', 'Epistemology'), ('metaphysics', 'Metaphysics'), ('ethics', 'Ethics'),
                        ('political-philosophy', 'Political philosophy'), ('aesthetics', 'Aesthetics'),
                        ('philosophy-of-mind', 'Philosophy of mind'), ('philosophy-of-language', 'Philosophy of language'),
                        ('philosophy-of-science', 'Philosophy of science'), ('philosophy-of-mathematics', 'Philosophy of mathematics')]:
        mixed_form_topic = slug in {'philosophy-of-language', 'philosophy-of-mathematics'}
        rows.append((f'books-{slug}', f'{label} · {"Works" if mixed_form_topic else "Books"}', 'philosophy',
                     {'forms': ['book', 'essay'] if mixed_form_topic else ['book'], 'topic': slug}))
    rows.append(('books-every-country', 'Top 3 books by country', 'literature',
                 {'group_by': 'country', 'items_per_country': 3, 'coverage_status': 'not_started',
                  'display_format': 'country_grouped', 'english_edition_required': False}))
    for slug, title, domain, scope in rows:
        item_type = 'person' if 'people_roles' in scope else 'work'
        target_size = 624 if slug == 'books-every-country' else 250 if slug in {'books-all-time', 'literature-all-time', 'nonfiction-all-time', 'philosophy-books-all-time', 'philosophers-all-time', 'history-books-all-time', 'manga-all-time', 'comics-graphic-novels-all-time'} else 200 if slug == 'classical-education-guide' else 100 if slug in {'books-addictive-all-time', 'books-funniest-all-time', 'books-mainstream-loved-all-time'} or scope.get('parent_ranking') == 'manga-all-time' else 10 if scope.get('topic') == 'philosophy-of-mathematics' else 50 if slug in {'books-ireland', 'books-scotland'} else 100 if 'topic' in scope else 200
        description = ('Three editorial selections for each country, grouped and numbered locally rather than as one global order.'
                       if slug == 'books-every-country' else
                       'Research template. Criteria and entries are not yet assessed. Each research target requires at least 50 distinct, relevant, diverse consulted sources.')
        yield {'slug': slug, **common, 'title': title, 'domain': domain, 'scope': scope,
               'item_type': item_type, 'target_size': target_size,
               'presentation': 'unranked' if slug == 'books-every-country' else 'ranked',
               'description': description}


class Command(BaseCommand):
    help = 'Create empty ranking definitions and external collection templates without changing existing records.'

    def add_arguments(self, parser):
        parser.add_argument('--external-file', type=Path, default=settings.BASE_DIR / 'templates/external_collections.json')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            external = json.loads(options['external_file'].read_text())['collections']
        except (OSError, ValueError, KeyError) as error:
            raise CommandError(f'Cannot read external collection templates: {error}') from error
        rows = list(definitions())
        for collection in external:
            if collection.get('entries'):
                raise CommandError('Bootstrap accepts empty collection templates only.')
            rows.append({'slug': collection['id'], 'title': collection['title'], 'origin': 'external',
                         'presentation': collection['presentation'], 'domain': 'collections', 'is_public': True,
                         'source_url': collection['source_url'], 'publisher': collection['publisher'],
                         'status': collection['status'], 'description': collection.get('notes', ''),
                         'scope': {'external_metadata': {key: value for key, value in collection.items() if key != 'entries'}}})
        added = 0
        for values in rows:
            slug = values.pop('slug')
            if Ranking.objects.filter(slug=slug).exists():
                continue
            ranking = Ranking(slug=slug, **values)
            ranking.full_clean()
            ranking.save()
            added += 1
        self.stdout.write(self.style.SUCCESS(f'Created {added} empty definitions; existing definitions preserved. No works, people or ranked entries seeded.'))
