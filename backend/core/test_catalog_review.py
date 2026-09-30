"""Catalog review boundaries for a future authorized isolated test-suite run."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import CatalogReviewDecision, Edition, LibraryItem, Person, PlanItem, Ranking, RankingEntry, Work


class CatalogReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user('catalog-review-staff', is_staff=True)
        cls.reader = get_user_model().objects.create_user('catalog-review-reader')
        cls.author = Person.objects.create(name='Review fixture author')
        cls.work = Work.objects.create(title='Review fixture work')
        cls.work.authors.add(cls.author)
        cls.default = Edition.objects.create(work=cls.work, pages=300)
        cls.work.default_edition = cls.default
        cls.work.save()
        cls.candidate = Edition.objects.create(work=cls.work, pages=320, isbn='9781234567897',
            publisher='Fixture publisher', is_archived=True,
            translation_notes='Archived bibliographic candidate; confirmation is required.',
            pages_basis='isbn_matched', source_url='https://example.org/original-candidate')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def row(self, key):
        response = self.client.get('/api/catalog-review/?status=all')
        self.assertEqual(response.status_code, 200, response.data)
        return next(row for row in response.data['results'] if row['key'] == key)

    @staticmethod
    def selected(row):
        return {key: row[key] for key in ('key', 'fingerprint', 'review_version')}

    def test_every_review_endpoint_requires_staff(self):
        for user in (self.reader, None):
            self.client.force_authenticate(user)
            for method, path in [('get', ''), ('get', 'history/'), ('post', 'batch/'), ('post', 'edition/')]:
                response = getattr(self.client, method)(f'/api/catalog-review/{path}', {}, format='json')
                self.assertEqual(response.status_code, 403)
        self.assertEqual(CatalogReviewDecision.objects.count(), 0)

    def test_batch_is_atomic_and_metadata_and_review_changes_reject_stale_selections(self):
        cover = self.row(f'work:{self.work.pk}:missing_cover')
        portrait = self.row(f'person:{self.author.pk}:missing_portrait')
        self.author.name = 'Updated attribution'
        self.author.save()
        response = self.client.post('/api/catalog-review/batch/', {'action': 'needs_research',
            'note': 'Find a licensed image.', 'items': [self.selected(cover), self.selected(portrait)]}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(CatalogReviewDecision.objects.count(), 0)
        row = self.row(f'work:{self.work.pk}:missing_cover')
        payload = {'action': 'prioritize', 'note': 'Frequently read work.', 'items': [self.selected(row)]}
        self.assertEqual(self.client.post('/api/catalog-review/batch/', payload, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/catalog-review/batch/', payload, format='json').status_code, 409)
        self.assertEqual(CatalogReviewDecision.objects.count(), 1)

    def test_deferred_issue_reopens_when_its_metadata_changes(self):
        row = self.row(f'work:{self.work.pk}:missing_cover')
        response = self.client.post('/api/catalog-review/batch/', {'action': 'defer', 'note': 'Await credited image.',
            'deferred_until': (timezone.localdate() + timedelta(days=7)).isoformat(), 'items': [self.selected(row)]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.row(row['key'])['status'], 'deferred')
        self.default.publisher = 'New provider metadata'
        self.default.save()
        self.assertEqual(self.row(row['key'])['status'], 'active')
        self.assertEqual(CatalogReviewDecision.objects.count(), 1)

    def test_images_cannot_be_marked_verified_with_identity_action(self):
        row = self.row(f'work:{self.work.pk}:missing_cover')
        response = self.client.post('/api/catalog-review/batch/', {'action': 'identity_checked',
            'note': 'This source supports the saved identity.', 'evidence_url': 'https://example.org/source',
            'identity_confirmed': True, 'items': [self.selected(row)]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CatalogReviewDecision.objects.count(), 0)

    def test_usage_priority_excludes_private_list_contents_and_never_returns_private_notes(self):
        hidden = Ranking.objects.create(title='PRIVATE TITLE', slug='review-private', origin='personal', owner=self.reader)
        RankingEntry.objects.create(ranking=hidden, work=self.work, rationale='PRIVATE RATIONALE')
        LibraryItem.objects.create(user=self.reader, work=self.work, notes='PRIVATE NOTES')
        row = self.row(f'work:{self.work.pk}:missing_cover')
        self.assertEqual(row['library_saves'], 1)
        self.assertEqual(row['list_appearances'], 0)
        self.assertEqual(row['evidence'], [])
        self.assertNotIn('PRIVATE', str(row))

    def test_edition_approval_requires_concrete_confirmation_and_preserves_private_basis(self):
        item = LibraryItem.objects.create(user=self.reader, work=self.work, current_page=80)
        plan = PlanItem.objects.create(user=self.reader, work=self.work, month=timezone.localdate().replace(day=1), pages=100, locked=True)
        before = (item.reading_basis.copy(), plan.reading_basis.copy())
        row = self.row(f'edition:{self.candidate.pk}:staged_edition')
        payload = {'items': [self.selected(row)], 'note': 'Publisher catalog confirms full work, this ISBN and physical pagination.',
            'evidence_url': 'https://example.org/publisher', 'identity_confirmed': True,
            'scope_confirmed': True, 'pagination_confirmed': True,
            'confirmed_metadata': {'isbn': self.candidate.isbn, 'publisher': self.candidate.publisher,
                                   'pages': 321, 'language': 'English', 'abridged': False}}
        self.assertEqual(self.client.post('/api/catalog-review/edition/', payload, format='json').status_code, 400)
        self.candidate.refresh_from_db()
        self.assertTrue(self.candidate.is_archived)
        payload['confirmed_metadata']['pages'] = 320
        response = self.client.post('/api/catalog-review/edition/', payload, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.candidate.refresh_from_db(); self.work.refresh_from_db(); item.refresh_from_db(); plan.refresh_from_db()
        self.assertFalse(self.candidate.is_archived)
        self.assertEqual(self.candidate.source_url, 'https://example.org/original-candidate')
        self.assertIn('Archived bibliographic candidate', self.candidate.translation_notes)
        self.assertEqual(self.candidate.pages_source_url, payload['evidence_url'])
        self.assertEqual(self.work.default_edition_id, self.default.pk)
        self.assertEqual((item.current_page, plan.pages, plan.locked), (80, 100, True))
        self.assertEqual((item.reading_basis, plan.reading_basis), before)
        self.assertEqual(CatalogReviewDecision.objects.get().action, 'approve_edition')
