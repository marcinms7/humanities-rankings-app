"""Import reviewed bibliographic records without changing existing catalog data."""
import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backend.core.models import Edition, Person, Work
from backend.core.management.receipts import save_import_receipt


class Command(BaseCommand):
    help = 'Import a reviewed catalog research batch; preserve existing records and private data.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['path'])
        try:
            raw = path.read_bytes()
            batch = json.loads(raw)
            records = batch['works']
            if batch.get('schema_version') != 1 or not isinstance(records, list) or not records:
                raise ValueError('Expected schema_version 1 and a nonempty works list.')
            keys = set()
            for record in records:
                if record['key'] in keys:
                    raise ValueError('Duplicate work key in batch.')
                keys.add(record['key'])
                if not record['title'].strip() or not record['authors'] or not all(isinstance(a, str) and a.strip() for a in record['authors']):
                    raise ValueError('Every work needs a title and verified author names.')
                if not record['work_source_url'].startswith('https://') or not record['evidence_ids']:
                    raise ValueError('Every work needs provenance and consulted evidence IDs.')
                e = record.get('edition')
                if e is None and batch.get('allow_pending_editions') and record.get('english_availability_note'):
                    continue
                if e['language'] != 'English' or not e['source_url'].startswith('https://'):
                    raise ValueError('Provide a verified English edition with source URL.')
                if e['completeness_status'] not in {'standard_book_edition_publisher_record', 'standard_novel_edition_publisher_record', 'complete_novel_distinguished_in_critical_review', 'complete_work_verified', 'explicitly_unabridged'}:
                    raise ValueError('Edition completeness requires an explicit reviewed status.')
                isbn = e.get('isbn', '').replace('-', '')
                if isbn and (len(isbn) != 13 or not isbn.isdigit() or sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn)) % 10):
                    raise ValueError('Invalid ISBN-13 check digit.')
                if e.get('pages') is not None and (type(e['pages']) is not int or e['pages'] <= 0):
                    raise ValueError('Pages must be a positive physical page count or null.')
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(str(error)) from error

        def existing_work(record):
            found = []
            names = {name.casefold() for name in record['authors']}
            for work in Work.objects.filter(title__iexact=record['title']).prefetch_related('authors'):
                if {p.name.casefold() for p in work.authors.all()} == names:
                    found.append(work)
            if len(found) > 1 or (found and found[0].is_archived):
                raise CommandError(f"Resolve ambiguous/archived work manually: {record['title']}")
            return found[0] if found else None

        # Resolve conflicts before making any write. ISBN identifies an edition,
        # not a license to silently replace another work's identity or metadata.
        for record in records:
            for name in record['authors']:
                matches = Person.objects.filter(name__iexact=name)
                if matches.count() > 1 or matches.filter(is_archived=True).exists():
                    raise CommandError(f'Resolve ambiguous/archived person manually: {name}')
            work = existing_work(record)
            e = record.get('edition')
            if e is None:
                continue
            matches = Edition.objects.filter(isbn=e['isbn']) if e.get('isbn') else Edition.objects.filter(source_url=e['source_url'])
            if matches.count() > 1 or matches.filter(is_archived=True).exists():
                raise CommandError(f"Resolve ambiguous/archived edition manually: {record['title']}")
            if matches.exists() and (not work or matches.first().work_id != work.pk):
                raise CommandError(f"Edition belongs to another work: {record['title']}")
        if options['dry_run']:
            self.stdout.write(f'Validated {len(records)} reviewed work records; no writes performed.')
            return

        results = []
        with transaction.atomic():
            for record in records:
                work = existing_work(record)
                created_work = work is None
                if work is None:
                    people = []
                    for name in record['authors']:
                        person = Person.objects.filter(name__iexact=name).first()
                        if person is None:
                            person = Person(name=name, source_url=record['work_source_url'])
                            person.full_clean()
                            person.save()
                        people.append(person)
                    work = Work(**{k: record[k] for k in ['title', 'form', 'field', 'original_year', 'original_language', 'countries', 'description']})
                    work.full_clean()
                    work.save()
                    work.authors.set(people)
                e = record.get('edition')
                if e is None:
                    results.append({'key': record['key'], 'work_id': work.pk, 'edition_id': None, 'created_work': created_work, 'created_edition': False, 'metadata_status': 'edition_and_media_pending'})
                    continue
                lookup = {'isbn': e['isbn']} if e.get('isbn') else {'source_url': e['source_url']}
                edition = Edition.objects.filter(**lookup).first()
                created_edition = edition is None
                if edition is None:
                    edition = Edition(work=work, abridged=False, **{k: e[k] for k in ['language', 'translator', 'publisher', 'isbn', 'pages', 'translation_notes', 'source_url']})
                    edition.full_clean()
                    edition.save()
                if created_work:
                    work.default_edition = edition
                    work.full_clean()
                    work.save(update_fields=['default_edition', 'updated_at'])
                results.append({'key': record['key'], 'work_id': work.pk, 'edition_id': edition.pk, 'created_work': created_work, 'created_edition': created_edition})

        # The immutable reviewed batch is the provenance record. The receipt is
        # outside the private-data tables and never stores account information.
        digest = hashlib.sha256(raw).hexdigest()
        receipt = save_import_receipt(path, {'input_sha256': digest, 'input_path': str(path), 'records': results})
        self.stdout.write(f"Imported {sum(r['created_work'] for r in results)} works and {sum(r['created_edition'] for r in results)} editions; all existing records preserved. Receipt: {receipt}")
