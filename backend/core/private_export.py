"""Consistent private exports, streamed into restricted temporary files."""
from contextlib import contextmanager
import io
import json
import shutil
import tempfile
import zipfile

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import F, Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (CatalogReviewDecision, ClassicalStudyProfile, Edition, LibraryItem, Person,
                     PlanCarryover, PlanItem, Ranking, RankingPreference, ReadingAdjustment,
                     ReadingAttempt, ReadingGoal, SavedDiscoveryFilter, StudyRecord, User, Work, RecommendationFeedback, ReadingCalendar)
from .serializers import UserSerializer
from .study_store import load_state


@contextmanager
def _text_stream(binary):
    text = io.TextIOWrapper(binary, encoding='utf-8', newline='\n')
    try:
        yield text
        text.flush()
    finally:
        text.detach()


def _reference_ids(value, field_names, list_fields=()):
    result = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in field_names and type(child) is int and child > 0:
                result.add(child)
            elif key in list_fields and isinstance(child, list):
                result.update(item for item in child if type(item) is int and item > 0)
            result.update(_reference_ids(child, field_names, list_fields))
    elif isinstance(value, list):
        for child in value:
            result.update(_reference_ids(child, field_names, list_fields))
    return result


def _chunks(values, size=400):
    values = sorted(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def write_private_export(user, stream, study_stream=None, notes_stream=None):
    """Write one transaction snapshot, buffering only individual records and IDs.

    The compatibility study-state document is reconstructed once per profile;
    its largest profile and any single stored revision remain memory bounds.
    Normalized study records also have their own incremental export section.
    """
    work_ids, edition_ids, person_ids, ranking_ids, counts = set(), set(), set(), set(), {}
    exported_at = timezone.now().isoformat()
    def collect(value):
        work_ids.update(_reference_ids(value, {'work', 'work_id'}, {'related'}))
        edition_ids.update(_reference_ids(value, {'edition', 'edition_id'}))
        person_ids.update(_reference_ids(value, {'person', 'person_id'}))
    def dump(value):
        json.dump(value, stream, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(',', ':'))
    def array(rows, section=None, process=None):
        stream.write('[')
        count = 0
        for row in rows:
            if process:
                row = process(row)
            collect(row)
            if count:
                stream.write(',')
            dump(row); count += 1
        stream.write(']')
        if section:
            counts[section] = count
    def field(name, value):
        stream.write(','); dump(name); stream.write(':'); dump(value)
    def rows(model):
        return model.objects.filter(user=user).order_by('pk').values().iterator(chunk_size=250)
    already_atomic = connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor == 'postgresql' and not already_atomic:
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        account = User.objects.get(pk=user.pk)
        stream.write('{"export_version":2')
        field('exported_at', exported_at)
        field('profile', {**UserSerializer(account).data, 'email': account.email, 'first_name': account.first_name,
                          'last_name': account.last_name, 'date_joined': account.date_joined, 'last_login': account.last_login})
        if notes_stream:
            notes_stream.write('# Reading notes\n')
        sections = [('library', LibraryItem), ('reading_history', ReadingAttempt), ('reading_goals', ReadingGoal),
                    ('edition_adjustments', ReadingAdjustment), ('plan', PlanItem), ('plan_carryovers', PlanCarryover),
                    ('preferences', RankingPreference), ('saved_discovery_filters', SavedDiscoveryFilter), ('study_records', StudyRecord), ('recommendation_feedback', RecommendationFeedback), ('reading_calendar', ReadingCalendar)]
        for name, model in sections:
            stream.write(','); dump(name); stream.write(':')
            if name in {'library', 'reading_history'} and notes_stream:
                notes_stream.write('\n## ' + ('Current library' if name == 'library' else 'Previous attempts') + '\n')
                def note(row):
                    title = row.pop('_export_title')
                    notes_stream.write(f"\n### {title}\n\nStatus: {row['status']}; started: {row['started_on'] or 'unknown'}; finished: {row['finished_on'] or 'unknown'}\n\n{row['notes'] or '(No notes recorded)'}\n")
                    return row
                array(model.objects.filter(user=user).order_by('pk').annotate(_export_title=F('work__title')).values().iterator(chunk_size=250), name, note)
            elif name == 'preferences':
                def preference(row):
                    ranking_ids.add(row['ranking_id']); return row
                array(rows(model), name, preference)
            else:
                array(rows(model), name)
        stream.write(',"study_profiles":[')
        if study_stream:
            study_stream.write('[')
        profile_count = 0
        for profile in ClassicalStudyProfile.objects.filter(user=user).order_by('pk').iterator(chunk_size=1):
            row = {field.attname: getattr(profile, field.attname) for field in profile._meta.concrete_fields}
            row['state'] = load_state(profile)
            collect(row)
            if profile_count:
                stream.write(',')
                if study_stream:
                    study_stream.write(',')
            dump(row)
            if study_stream:
                json.dump(row, study_stream, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(',', ':'))
            profile_count += 1
        stream.write(']'); counts['study_profiles'] = profile_count
        if study_stream:
            study_stream.write(']')
        stream.write(',"catalog_review_decisions":')
        array(CatalogReviewDecision.objects.filter(actor=user).order_by('pk').values().iterator(chunk_size=100), 'catalog_review_decisions')
        stream.write(',"lists":[')
        list_count = 0
        for ranking in Ranking.objects.filter(owner=user, origin='personal').order_by('pk').iterator(chunk_size=100):
            if list_count:
                stream.write(',')
            record = {field.attname: getattr(ranking, field.attname) for field in ranking._meta.concrete_fields if field.name != 'share_token'}
            collect(record)
            stream.write('{')
            for index, (key, value) in enumerate(record.items()):
                if index:
                    stream.write(',')
                dump(key); stream.write(':'); dump(value)
            stream.write(',"entries":')
            array(ranking.entries.order_by('position', 'pk').values().iterator(chunk_size=250))
            stream.write(',"revisions":')
            array(ranking.revisions.order_by('number').values().iterator(chunk_size=50))
            stream.write('}'); list_count += 1
        stream.write(']'); counts['lists'] = list_count
        for batch in _chunks(edition_ids):
            work_ids.update(Edition.objects.filter(pk__in=batch).values_list('work_id', flat=True))
        stream.write(',"references":{"works":[')
        pending, visited, work_count = set(work_ids), set(), 0
        while pending:
            parents = set()
            for batch in _chunks(pending):
                for work in Work.objects.filter(pk__in=batch).prefetch_related('authors', 'tags').order_by('pk').iterator(chunk_size=100):
                    row = {field.attname: getattr(work, field.attname) for field in work._meta.concrete_fields}
                    row['author_ids'] = [person.pk for person in work.authors.all()]
                    row['tags'] = [{'id': tag.pk, 'name': tag.name, 'kind': tag.kind, 'is_archived': tag.is_archived} for tag in work.tags.all()]
                    person_ids.update(row['author_ids'])
                    if work.default_edition_id:
                        edition_ids.add(work.default_edition_id)
                    if work.contained_in_id:
                        parents.add(work.contained_in_id)
                    if work_count:
                        stream.write(',')
                    dump(row); work_count += 1
            visited.update(pending); pending = parents - visited
        stream.write('],"editions":')
        array(row for batch in _chunks(edition_ids) for row in Edition.objects.filter(pk__in=batch).order_by('pk').values().iterator(chunk_size=250))
        stream.write(',"people":')
        array(row for batch in _chunks(person_ids) for row in Person.objects.filter(pk__in=batch).order_by('pk').values().iterator(chunk_size=250))
        stream.write(',"bookmarked_rankings":')
        array(row for batch in _chunks(ranking_ids) for row in Ranking.objects.filter(Q(owner__isnull=True) | Q(owner=user), pk__in=batch).order_by('pk').values(
            'id', 'slug', 'title', 'origin', 'presentation', 'revision', 'source_url', 'is_archived').iterator(chunk_size=250))
        stream.write('}')
        field('manifest', {'application': 'Marginalia', 'format': 'private-reading-data-v2', 'sections': counts,
            'study_contents': 'Complete compatibility study state plus individually stored study records, including notes, essays and their retained histories.',
            'image_references': 'Stored relative media paths, credits and source URLs; image bytes are excluded.',
            'excluded': ['Passwords, sessions, authentication secrets and temporary mutation replay receipts', 'Other users’ private data',
                         'Shared catalog/research beyond referenced metadata', 'Image bytes and database backups', 'Active sharing tokens'],
            'restore': 'Portable data export; automatic re-import is not implemented. Use database/media backups for full application recovery.'})
        stream.write('}')
    return exported_at


def build_private_export(user):
    """Compatibility helper for programmatic callers; downloads use the writer."""
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as stream:
        write_private_export(user, stream)
        stream.seek(0)
        return json.load(stream)


def export_response(request):
    output_format = request.query_params.get('download', 'json')
    if output_format not in {'json', 'zip'}:
        raise ValidationError('Choose json or zip export format.')
    result = tempfile.TemporaryFile(mode='w+b')
    try:
        if output_format == 'json':
            with _text_stream(result) as text:
                write_private_export(request.user, text)
        else:
            with tempfile.TemporaryFile(mode='w+b') as private, tempfile.TemporaryFile(mode='w+b') as study, tempfile.TemporaryFile(mode='w+b') as notes:
                with _text_stream(private) as data_text, _text_stream(study) as study_text, _text_stream(notes) as notes_text:
                    exported_at = write_private_export(request.user, data_text, study_text, notes_text)
                with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    for name, source in [('private-data.json', private), ('study-state.json', study), ('reading-notes.md', notes)]:
                        source.seek(0)
                        with archive.open(name, 'w', force_zip64=True) as target:
                            shutil.copyfileobj(source, target, length=1024 * 1024)
                    archive.writestr('README.md', '# Marginalia private reading export\n\n'
                        'private-data.json contains private reading, planning, personal-list, saved-filter and study records, with histories and catalog references. '
                        'study-state.json is the complete reconstructed study state. reading-notes.md collects current and previous reading notes.\n\n'
                        'Keep this archive private. Passwords, active sharing links, other readers’ data and image bytes are excluded. '
                        'This is a portable export, not an automatic restore package; retain database/media backups.\n\n'
                        f'Exported: {exported_at}\n')
        result.seek(0)
        response = FileResponse(result, as_attachment=True, filename=f'marginalia-private-data.{output_format}',
                                content_type='application/zip' if output_format == 'zip' else 'application/json; charset=utf-8')
        response['Cache-Control'] = 'private, no-store'
        return response
    except Exception:
        result.close()
        raise
