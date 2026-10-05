"""Bounded, read-only navigation search across visible application content.

Catalog identities reuse the shared search index. Private notes, study answers,
library fields and other readers' lists are never queried or indexed here.
"""
from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Person, ResearchSource, Work
from .reading_insights import shared_lists
from .search import fold, search_catalog, tokens


GROUP_LIMIT = 5


class AppSearchItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    href = serializers.CharField()


class AppSearchGroupSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    items = AppSearchItemSerializer(many=True)
    has_more = serializers.BooleanField()
    more_href = serializers.CharField(allow_null=True)


class AppSearchResponseSerializer(serializers.Serializer):
    query = serializers.CharField(allow_blank=True)
    groups = AppSearchGroupSerializer(many=True)


def link(route, **params):
    return '#/' + route + ('?' + urlencode(params) if params else '')


def item(identity, title, subtitle, href):
    return dict(id=str(identity), title=title, subtitle=subtitle, href=href)


def add_group(groups, key, label, rows, more_href=None):
    # Callers fetch one extra row to establish continuation without COUNTs.
    if rows:
        groups.append(dict(key=key, label=label, items=rows[:GROUP_LIMIT],
                           has_more=len(rows) > GROUP_LIMIT, more_href=more_href))


STUDY_SECTIONS = (
    ('today', 'Today’s study', '', 'Classical education and today’s study activities'),
    ('desk', 'Reading desk', 'desk', 'Close reading of Greek and Latin passages'),
    ('translation', 'Translation lab', 'translation', 'Classical language and translation exercises'),
    ('reception', 'Reception trails', 'reception', 'Classical reception in later literature and art'),
    ('glossary', 'Context & glossary', 'glossary', 'Ancient-world concepts and vocabulary'),
    ('rankings', 'Classical rankings', 'rankings', 'Rankings for classical education'),
    ('plan', 'My classical plan', 'plan', 'Plan classical reading and study'),
    ('listening', 'Listening guide', 'listening', 'Philosophy podcasts and lecture pairings'),
    ('courses', 'Courses & materials', 'courses', 'Greek, Latin and classical studies courses'),
    ('recall', 'Recall & review', 'recall', 'Review classical knowledge with recall prompts'),
    ('atlas', 'Historical atlas', 'atlas', 'Ancient places and historical context'),
    ('essay', 'Essay workshop', 'essay', 'Classical essay writing and argument'),
)


@lru_cache(maxsize=4)
def _study_documents(stamps):
    """Only static editorial titles/context; no private study profiles are read."""
    rows = [item('section:' + key, title, description,
                 link('classical-education', **({'tab': tab} if tab else {})))
            for key, title, tab, description in STUDY_SECTIONS]
    for path, _modified, _size in stamps:
        data = json.loads(Path(path).read_text())
        if Path(path).name == 'classical_education.json':
            for module in data.get('modules', []):
                rows.append(item('module:' + module['id'], module['title'],
                                 ' · '.join(filter(None, ['Study module', module.get('author'), module.get('subtitle')])),
                                 link('classical-education', module=module['id'])))
        else:
            for entry in data.get('glossary', []):
                rows.append(item('glossary:' + entry['id'], entry['title'], 'Classical glossary',
                                 link('classical-education', tab='glossary', term=entry['id'])))
    return rows


def study_matches(query):
    folder = Path(__file__).parent / 'content'
    paths = [folder / name for name in ('classical_education.json', 'classical_companion.json', 'classical_reading_desk.json')]
    stamps = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
    words = tokens(query)
    matches = [row for row in _study_documents(stamps)
               if all(word in fold(row['title'] + ' ' + row['subtitle']) for word in words)]
    phrase = fold(query)
    return sorted(matches, key=lambda row: (fold(row['title']) != phrase,
                  not fold(row['title']).startswith(phrase), fold(row['title']), row['id']))[:GROUP_LIMIT + 1]


@api_view(['GET'])
@permission_classes([AllowAny])
def app_search(request):
    from .views import ranking_queryset

    query = request.query_params.get('q', '').strip()[:300]
    groups = []
    if tokens(query):
        books = search_catalog(Work.objects.filter(is_archived=False), query).only('id', 'title').prefetch_related(
            Prefetch('authors', queryset=Person.objects.filter(is_archived=False).only('id', 'name')))
        add_group(groups, 'books', 'Books', [item(book.pk, book.title,
                  ' · '.join(person.name for person in book.authors.all()) or 'Author not recorded',
                  link(f'books/{book.pk}')) for book in books[:GROUP_LIMIT + 1]], link('catalog', q=query))

        authors = search_catalog(Person.objects.filter(is_archived=False), query, kind='person').only('id', 'name')
        add_group(groups, 'authors', 'Authors & thinkers',
                  [item(person.pk, person.name, 'Author / thinker', link(f'authors/{person.pk}'))
                   for person in authors[:GROUP_LIMIT + 1]], link('authors', q=query))

        visible = ranking_queryset(request.user)
        matching = visible.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(publisher__icontains=query))
        ranking_groups = [
            ('researched', 'Researched rankings', 'rankings', matching.filter(origin='curated').exclude(slug='classical-education-guide')),
            ('published', 'Published rankings', 'published-rankings', matching.filter(origin='external', presentation='ranked')),
            ('collections', 'Reading collections', 'collections', matching.filter(origin='external').exclude(presentation='ranked')),
        ]
        if request.user.is_authenticated:
            ranking_groups.append(('personal', 'Your personal lists', 'my-lists', matching.filter(origin='personal', owner=request.user)))
        for key, label, route, queryset in ranking_groups:
            rows = queryset.values('id', 'title', 'publisher')[:GROUP_LIMIT + 1]
            add_group(groups, key, label,
                      [item(row['id'], row['title'], row['publisher'] or label,
                            link(f"rankings/{row['id']}", group=route)) for row in rows],
                      link(route, rsearch=query))

        if request.user.is_authenticated:
            sources = ResearchSource.objects.filter(is_archived=False, ranking__in=shared_lists(request.user)).filter(
                Q(title__icontains=query) | Q(publisher__icontains=query) | Q(source_id__icontains=query) | Q(url__icontains=query)
            ).order_by('title', 'ranking__title', 'pk').values('id', 'title', 'url', 'ranking_id', 'ranking__title')[:GROUP_LIMIT + 1]
            add_group(groups, 'sources', 'Research sources',
                      [item(row['id'], row['title'], row['ranking__title'],
                            link('sources', ranking=row['ranking_id'], url=row['url'])) for row in sources],
                      link('sources', search=query))
            # Match syllabus permissions exactly. Staff alone is not permission.
            owner = get_user_model().objects.order_by('pk').values_list('pk', flat=True).first()
            if request.user.pk == owner:
                add_group(groups, 'study', 'Classical study', study_matches(query))

    response = Response(dict(query=query, groups=groups))
    response['Cache-Control'] = 'private, no-store'
    return response
