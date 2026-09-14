#!/usr/bin/env python3
"""Create only the owner-requested empty shared ranking definitions."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')

import django

django.setup()

from backend.core.models import Ranking


PLACEHOLDERS = [
    {
        'slug': 'classical-education-guide',
        'title': 'Classical education · Guide',
        'description': 'Empty research guide for Greek and Latin texts across poetry, prose, philosophy, history, rhetoric and drama. Sources, criteria and entries will be added later.',
        'domain': 'literature', 'target_size': 200,
        'scope': {'forms': ['book', 'collection', 'essay', 'poem', 'play'], 'traditions': ['Greek', 'Latin'], 'guide_scope': 'Greek and Latin texts across poetry, prose, philosophy, history, rhetoric and drama'},
    },
    {
        'slug': 'books-addictive-all-time',
        'title': 'Most addictive books · All time',
        'description': 'Empty research template for books readers describe as impossible to put down. Sources, criteria and entries will be added later.',
        'domain': 'all', 'target_size': 100,
        'scope': {'forms': ['book'], 'theme': 'compulsive_reading', 'ranking_question': 'Books readers report being unable to put down.'},
    },
    {
        'slug': 'books-funniest-all-time',
        'title': 'Funniest books · All time',
        'description': 'Empty research template for books of exceptional comic force across traditions and genres. Sources, criteria and entries will be added later.',
        'domain': 'all', 'target_size': 100,
        'scope': {'forms': ['book'], 'theme': 'humour', 'ranking_question': 'Books of exceptional comic force across traditions and genres.'},
    },
    {
        'slug': 'books-mainstream-loved-all-time',
        'title': 'Most mainstream-loved books · All time',
        'description': 'Empty research template for books with unusually broad, enduring mainstream reader affection. Sources, criteria and entries will be added later.',
        'domain': 'all', 'target_size': 100,
        'scope': {'forms': ['book'], 'theme': 'mainstream_love', 'ranking_question': 'Books with unusually broad, enduring mainstream reader affection.'},
    },
]


def main():
    created = []
    for values in PLACEHOLDERS:
        existing = Ranking.objects.filter(slug=values['slug']).first()
        if existing:
            print(f"Preserved existing {existing.slug} (no changes).")
            continue
        ranking = Ranking(
            **values, item_type='work', presentation='ranked', origin='curated',
            is_public=True, status='awaiting_research', criteria=[],
        )
        ranking.full_clean()
        ranking.save()
        created.append(ranking.slug)
    print(f"Created {len(created)} empty placeholders: {', '.join(created) or 'none'}.")


if __name__ == '__main__':
    main()
