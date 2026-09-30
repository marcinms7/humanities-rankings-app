"""Private suggestions: real saved signals, reversible feedback and edition honesty."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (Edition, LibraryItem, Person, Ranking, RankingEntry, RankingPreference,
                     ReadingAttempt, RecommendationFeedback, SavedDiscoveryFilter, Tag, Work)


class RecommendationBoundaries(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('suggestion-reader')
        cls.other = get_user_model().objects.create_user('other-suggestion-reader')
        cls.old_author = Person.objects.create(name='Previously explored author')
        cls.new_author = Person.objects.create(name='Newly explored author')
        cls.short_author = Person.objects.create(name='Short book author')
        cls.genre = Tag.objects.create(name='Recommendation fixture genre', kind='genre')
        cls.topic = Tag.objects.create(name='Memory', kind='topic')
        cls.read = cls.book('Already finished', cls.old_author, 400)
        cls.familiar = cls.book('A familiar unread book', cls.old_author, 410)
        cls.new = cls.book('B unfamiliar long book', cls.new_author, 510)
        cls.short = cls.book('C short book', cls.short_author, 120)
        cls.alternative = cls.book('D substitute book', cls.new_author, 350)
        cls.unknown = cls.book('E book with unknown length', cls.short_author, None)
        cls.new.tags.add(cls.genre, cls.topic)
        cls.alternative.tags.add(cls.topic)
        LibraryItem.objects.create(user=cls.user, work=cls.read, status='finished')
        cls.ranking = Ranking.objects.create(title='Bookmarked source', slug='recommendation-source', origin='external', is_public=True)
        cls.entry = RankingEntry.objects.create(ranking=cls.ranking, work=cls.new, position=9, source_rank=3)

    @classmethod
    def book(cls, title, author, pages):
        work = Work.objects.create(title=title)
        work.authors.add(author)
        edition = Edition.objects.create(work=work, pages=pages, pages_basis='manually_recorded' if pages else 'unknown')
        work.default_edition = edition
        work.save()
        return work

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def bundle(self, params=None):
        response = self.client.get('/api/recommendations/', params or {})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def candidates(self, bundle):
        return [work for slot in bundle['slots'] for work in ([slot['selected']] if slot['selected'] else []) + slot['alternatives']]

    def set_preferences(self, **values):
        data = {'expected_revision': 0, 'fields': [], 'genres': [], 'topics': [], 'short_pages': 250, 'saved_filter': None, **values}
        return self.client.patch('/api/recommendations/preferences/', data, format='json')

    def signal(self, work, action, revision=0, **extra):
        return self.client.post('/api/recommendations/feedback/', {'work': work.pk, 'action': action, 'expected_revision': revision, **extra}, format='json')

    def test_endpoints_require_an_authenticated_reader(self):
        self.client.force_authenticate(None)
        for suffix in ['', 'preferences/', 'feedback/']:
            self.assertIn(self.client.get('/api/recommendations/' + suffix).status_code, [401, 403])

    def test_bundle_has_distinct_history_aware_slots_and_backend_commitment(self):
        bundle = self.bundle()
        slots = {slot['key']: slot for slot in bundle['slots']}
        selected = [slot['selected'] for slot in slots.values() if slot['selected']]
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({work['id'] for work in selected}), 3)
        self.assertEqual(slots['familiar']['selected']['id'], self.familiar.pk)
        self.assertEqual(slots['short']['selected']['id'], self.short.pk)
        self.assertNotIn(self.read.pk, [work['id'] for work in self.candidates(bundle)])
        self.assertEqual(bundle['commitment']['known_pages'], sum(work['pages'] or 0 for work in selected))
        self.assertEqual(bundle['commitment']['known_estimated_hours'], round(sum(work['estimate']['estimated_hours'] or 0 for work in selected), 2))
        self.assertTrue(all(not work['estimate']['calibrated'] for work in selected))

    def test_frozen_unknown_pages_do_not_become_short_after_catalog_enrichment(self):
        LibraryItem.objects.create(user=self.user, work=self.unknown)
        self.unknown.default_edition.pages = 90
        self.unknown.default_edition.save()
        bundle = self.bundle()
        unknown = next(work for work in self.candidates(bundle) if work['id'] == self.unknown.pk)
        self.assertIsNone(unknown['pages'])
        self.assertIsNone(unknown['estimate']['estimated_hours'])
        short = next(slot for slot in bundle['slots'] if slot['key'] == 'short')
        self.assertNotIn(self.unknown.pk, [work['id'] for work in [short['selected'], *short['alternatives']] if work])

    def test_frozen_selected_edition_drives_short_slot_and_time(self):
        selected = Edition.objects.create(work=self.new, pages=180, pages_basis='isbn_matched')
        LibraryItem.objects.create(user=self.user, work=self.new, edition=selected)
        result = self.bundle({'short': self.new.pk})
        work = next(slot['selected'] for slot in result['slots'] if slot['key'] == 'short')
        self.assertEqual((work['pages'], work['page_basis']), (180, 'isbn_matched'))
        self.assertIn('saved', work['edition_basis'])
        self.assertEqual(work['estimate']['page_count_basis'], 'isbn_matched')

    def test_bookmark_explanations_do_not_compare_scores_or_change_source_positions(self):
        RankingPreference.objects.create(user=self.user, ranking=self.ranking, bookmarked=True)
        original = (self.entry.position, self.entry.source_rank, self.entry.assessments)
        row = next(work for work in self.candidates(self.bundle()) if work['id'] == self.new.pk)
        self.assertTrue(any('Bookmarked source' in reason for reason in row['reasons']))
        self.assertEqual(row['lists'][0]['source_rank'], 3)
        self.assertNotIn('score', row)
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.position, self.entry.source_rank, self.entry.assessments), original)

    def test_other_reader_bookmarks_and_feedback_never_affect_suggestions(self):
        RankingPreference.objects.create(user=self.other, ranking=self.ranking, bookmarked=True)
        RecommendationFeedback.objects.create(user=self.other, work=self.new, action='not_interested')
        row = next(work for work in self.candidates(self.bundle()) if work['id'] == self.new.pk)
        self.assertFalse(row['lists'])
        self.assertEqual(row['feedback_revision'], 0)
        self.assertEqual(self.client.get('/api/recommendations/feedback/').data['count'], 0)

    def test_collection_bookmarks_do_not_acquire_merit_ranking_context(self):
        self.ranking.presentation = 'reading_sequence'
        self.ranking.save()
        RankingPreference.objects.create(user=self.user, ranking=self.ranking, bookmarked=True)
        row = next(work for work in self.candidates(self.bundle()) if work['id'] == self.new.pk)
        self.assertEqual(row['lists'], [])

    def test_recorded_progress_and_archived_completions_are_excluded(self):
        LibraryItem.objects.create(user=self.user, work=self.new, status='reading')
        ReadingAttempt.objects.create(user=self.user, work=self.alternative, status='finished')
        ids = {work['id'] for work in self.candidates(self.bundle())}
        self.assertNotIn(self.new.pk, ids)
        self.assertNotIn(self.alternative.pk, ids)

    def test_multi_author_work_with_any_explored_author_is_not_new_author(self):
        self.new.authors.add(self.old_author)
        slot = next(slot for slot in self.bundle()['slots'] if slot['key'] == 'new_author')
        self.assertNotIn(self.new.pk, [work['id'] for work in [slot['selected'], *slot['alternatives']] if work])
        unknown_author = Person.objects.create(name='Unknown authors')
        self.read.authors.add(unknown_author)
        self.short.authors.set([unknown_author])
        self.unknown.authors.set([unknown_author])
        bundle = self.bundle()
        slot = next(slot for slot in bundle['slots'] if slot['key'] == 'new_author')
        self.assertNotIn(self.short.pk, [work['id'] for work in [slot['selected'], *slot['alternatives']] if work])
        familiar = next(slot for slot in bundle['slots'] if slot['key'] == 'familiar')
        self.assertNotIn(self.short.pk, [work['id'] for work in [familiar['selected'], *familiar['alternatives']] if work])

    def test_interest_reasons_and_owned_filter_remain_explicit_and_scoped(self):
        saved = SavedDiscoveryFilter.objects.create(user=self.user, name='Long books', filters={'search': 'long'})
        result = self.set_preferences(genres=[self.genre.name], topics=['Memory'], saved_filter=saved.pk)
        self.assertEqual(result.status_code, 200, result.data)
        bundle = self.bundle()
        rows = self.candidates(bundle)
        self.assertEqual({work['id'] for work in rows}, {self.new.pk})
        self.assertTrue(any('Memory' in reason for reason in rows[0]['reasons']))
        self.assertTrue(any('Long books' in reason for reason in rows[0]['reasons']))
        other = SavedDiscoveryFilter.objects.create(user=self.other, name='Private filter', filters={})
        self.assertEqual(self.set_preferences(expected_revision=1, saved_filter=other.pk).status_code, 400)

    def test_deleted_filter_requires_explicit_review_and_preserves_original_reference(self):
        saved = SavedDiscoveryFilter.objects.create(user=self.user, name='Restricted selection', filters={'field': 'philosophy'})
        saved_id = saved.pk
        self.assertEqual(self.set_preferences(saved_filter=saved_id).status_code, 200)
        saved.delete()
        bundle = self.bundle()
        self.assertTrue(bundle['needs_preferences_review'])
        self.assertEqual(bundle['slots'], [])
        self.assertEqual(RecommendationFeedback.objects.get(user=self.user, work=None).details['saved_filter_id'], saved_id)
        self.assertEqual(self.set_preferences(expected_revision=1, saved_filter=None).status_code, 200)
        self.assertFalse(self.bundle()['needs_preferences_review'])

    def test_not_interested_and_later_are_reversible_and_later_expires(self):
        result = self.signal(self.new, 'not_interested')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertNotIn(self.new.pk, [work['id'] for work in self.candidates(self.bundle())])
        result = self.signal(self.new, 'neutral', revision=1)
        self.assertEqual(result.data['revision'], 2)
        self.assertIn(self.new.pk, [work['id'] for work in self.candidates(self.bundle())])
        result = self.signal(self.new, 'later', revision=2, days=30)
        self.assertEqual(result.data['deferred_until'], (timezone.localdate() + timedelta(days=30)).isoformat())
        self.assertNotIn(self.new.pk, [work['id'] for work in self.candidates(self.bundle())])
        RecommendationFeedback.objects.filter(user=self.user, work=self.new).update(deferred_until=timezone.localdate())
        self.assertIn(self.new.pk, [work['id'] for work in self.candidates(self.bundle())])
        self.assertFalse(self.client.get('/api/recommendations/feedback/').data['results'][0]['active'])

    def test_clear_keeps_revision_tombstone_and_stale_changes_fail(self):
        self.assertEqual(self.signal(self.new, 'more_like').status_code, 200)
        self.assertEqual(self.signal(self.new, 'neutral', revision=1).status_code, 200)
        self.assertEqual(self.signal(self.new, 'later', revision=0).status_code, 409)
        self.assertEqual(RecommendationFeedback.objects.get(user=self.user, work=self.new).action, 'neutral')
        self.assertEqual(self.set_preferences(topics=['Memory']).status_code, 200)
        self.assertEqual(self.set_preferences(topics=['Other']).status_code, 409)
        self.assertEqual(self.client.get('/api/recommendations/preferences/').data['topics'], ['Memory'])

    def test_more_like_explains_concrete_catalog_connections_without_assessments(self):
        self.assertEqual(self.signal(self.new, 'more_like').status_code, 200)
        row = next(work for work in self.candidates(self.bundle()) if work['id'] == self.alternative.pk)
        self.assertTrue(any('B unfamiliar long book' in reason and ('author' in reason or 'tag' in reason) for reason in row['reasons']))
        self.assertEqual(self.client.get('/api/recommendations/feedback/').data['results'][0]['action'], 'more_like')

    def test_substitutions_preserve_other_slots_and_reject_duplicates_and_hidden_choices(self):
        bundle = self.bundle()
        slot = next(slot for slot in bundle['slots'] if slot['key'] == 'new_author')
        alternative = slot['alternatives'][0]
        picks = {row['key']: row['selected']['id'] for row in bundle['slots'] if row['selected']}
        picks['new_author'] = alternative['id']
        changed = self.bundle(picks)
        self.assertEqual({row['key']: row['selected']['id'] for row in changed['slots'] if row['selected']}, picks)
        picks['familiar'] = picks['new_author']
        self.assertEqual(self.client.get('/api/recommendations/', picks).status_code, 400)
        self.signal(self.alternative, 'not_interested')
        self.assertEqual(self.client.get('/api/recommendations/', {'new_author': self.alternative.pk}).status_code, 400)

    def test_invalid_preferences_and_foreign_feedback_are_rejected(self):
        for values in [{'fields': ['invented']}, {'short_pages': 0}, {'topics': ['term'] * 9}, {'genres': ['Made up genre']}, {'owner': self.other.pk}]:
            self.assertEqual(self.set_preferences(**values).status_code, 400)
        for values in [{'days': 0}, {'days': 366}, {'owner': self.other.pk}]:
            self.assertEqual(self.signal(self.new, 'later', **values).status_code, 400)
        self.assertEqual(self.signal(self.new, 'invented').status_code, 400)

    def test_malformed_nested_saved_filters_return_validation_errors(self):
        for filters in [[], 'invalid', {'unsupported': 'value'}]:
            result = self.client.post('/api/saved-filters/', {'name': 'Invalid fixture', 'filters': filters}, format='json')
            self.assertEqual(result.status_code, 400, result.data)
        for payload in [[], 'invalid', {'unsupported': True}]:
            result = self.client.patch('/api/recommendations/preferences/', payload, format='json')
            self.assertEqual(result.status_code, 400, result.data)

    def test_cold_start_and_empty_scope_are_honest_and_responses_are_private(self):
        self.client.force_authenticate(self.other)
        response = self.client.get('/api/recommendations/')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertFalse(response.data['personalized'])
        self.assertTrue(any('no matching personal signal' in reason for work in self.candidates(response.data) for reason in work['reasons']))
        saved = SavedDiscoveryFilter.objects.create(user=self.other, name='No match', filters={'search': 'Unmatched fixture term'})
        self.assertEqual(self.set_preferences(saved_filter=saved.pk).status_code, 200)
        result = self.bundle()
        self.assertEqual(result['commitment']['books'], 0)
        self.assertTrue(all(slot['selected'] is None for slot in result['slots']))
