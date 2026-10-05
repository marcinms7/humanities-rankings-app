"""Read-only, bounded bibliography exports from recorded catalog metadata.

Edition publication dates are not currently recorded. A work's original date
must therefore never populate an edition's RIS PY or BibTeX year field.
"""
import unicodedata

from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .bulk_books import PositiveID
from .models import LibraryItem, Work


EDITION_SOURCES = ['library_snapshot', 'library_edition', 'catalog_default', 'none']
EDITION_FIELDS = ('publisher', 'translator', 'language', 'isbn')
EXPORT_NOTES = [
    'Plain references use the recorded names and metadata; they are not formatted to a particular citation style.',
    'Edition publication years are not recorded. Original work dates appear only as contextual notes, never as edition dates.',
    'Author names are retained as recorded; name parts and author order have not been editorially verified. BibTeX uses literal names.',
    'Check the missing details in your reference manager before using these references in finished writing.',
]


class BibliographyCommand(serializers.Serializer):
    work_ids = serializers.ListField(child=PositiveID(), min_length=1, max_length=200)
    prefer_library_editions = serializers.BooleanField(default=True)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise ValidationError({'non_field_errors': ['Use only selected books and the edition preference.']})
        return super().to_internal_value(data)

    def validate_work_ids(self, value):
        return list(dict.fromkeys(value))


class BibliographyReferenceSerializer(serializers.Serializer):
    work_id = serializers.IntegerField()
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    original_year = serializers.IntegerField(allow_null=True)
    edition_id = serializers.IntegerField(allow_null=True)
    edition_source = serializers.ChoiceField(choices=EDITION_SOURCES)
    publisher = serializers.CharField(allow_blank=True)
    translator = serializers.CharField(allow_blank=True)
    language = serializers.CharField(allow_blank=True)
    isbn = serializers.CharField(allow_blank=True)
    reference = serializers.CharField()
    missing_fields = serializers.ListField(child=serializers.CharField())
    notices = serializers.ListField(child=serializers.CharField())


class BibliographyExportSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    references = BibliographyReferenceSerializer(many=True)
    plain_text = serializers.CharField()
    ris = serializers.CharField()
    bibtex = serializers.CharField()
    notes = serializers.ListField(child=serializers.CharField())


def plain(value):
    """Keep Unicode names, but never allow controls/newlines to create RIS tags."""
    if not isinstance(value, str):
        return ''
    normalized = unicodedata.normalize('NFC', value)
    return ' '.join(''.join(
        ' ' if char.isspace() or unicodedata.category(char).startswith('C') else char
        for char in normalized
    ).split())


def tex(value):
    replacements = {
        # BibTeX counts braces even after a backslash. Named text macros keep
        # arbitrary/unbalanced catalog braces from terminating a field or entry.
        '\\': r'\textbackslash{}', '{': r'\textbraceleft{}', '}': r'\textbraceright{}', '%': r'\%',
        '&': r'\&', '$': r'\$', '#': r'\#', '_': r'\_',
        '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
    }
    return ''.join(replacements.get(char, char) for char in plain(value))


def original_date(year):
    return f'{abs(year)} BCE' if year < 0 else str(year)


def edition_metadata(work, item):
    notices = []
    basis = item.reading_basis if item and isinstance(item.reading_basis, dict) else {}
    # Frozen metadata is the edition actually used for saved reading, even if
    # a later catalog correction changed the current default's bibliographic fields.
    if basis:
        edition_id = basis.get('edition_id')
        edition_id = edition_id if type(edition_id) is int and edition_id > 0 else None
        notices.append('Uses the edition details saved with your reading record.')
        if not edition_id and not any(plain(basis.get(field)) for field in EDITION_FIELDS):
            notices.append('No edition was recorded when this reading was saved; the current catalog default has not been substituted.')
        return {
            'edition_id': edition_id, 'edition_source': 'library_snapshot',
            **{field: plain(basis.get(field)) for field in EDITION_FIELDS},
        }, notices
    if item and item.edition and item.edition.work_id == work.pk:
        edition, source = item.edition, 'library_edition'
        if edition.is_archived:
            notices.append('Your saved edition is archived in the catalog; its recorded details are retained.')
    elif work.default_edition and not work.default_edition.is_archived and work.default_edition.work_id == work.pk:
        edition, source = work.default_edition, 'catalog_default'
        notices.append('Uses the catalog default edition; verify it matches the edition you intend to cite.')
    else:
        edition, source = None, 'none'
        notices.append('No usable edition is recorded; this is a work-level reference.')
    return {
        'edition_id': edition.pk if edition else None, 'edition_source': source,
        **{field: plain(getattr(edition, field, '')) for field in EDITION_FIELDS},
    }, notices


def reference_record(work, item):
    edition, notices = edition_metadata(work, item)
    authors = [name for person in work.authors.all() if (name := plain(person.name))]
    year = work.original_year if work.original_year and -10000 <= work.original_year <= 3000 else None
    record = dict(work_id=work.pk, title=plain(work.title), authors=authors, form=work.form,
                  original_year=year, **edition)
    if work.form not in {'book', 'collection'}:
        notices.append(f'Catalog form: {plain(work.form).replace("_", " ")}. Exported as a general reference; standalone book publication is not assumed.')
    missing = []
    if not authors:
        missing.append('author')
    if not edition['edition_id']:
        missing.append('edition')
    if not edition['publisher']:
        missing.append('publisher')
    missing.append('edition publication year')
    if not edition['isbn']:
        missing.append('ISBN')
    fragments = ['; '.join(authors) if authors else '[Author not recorded]', f'{record["title"]} (n.d.)']
    if edition['translator']:
        fragments.append(f'Translator: {edition["translator"]}')
    if edition['publisher']:
        fragments.append(edition['publisher'])
    if edition['isbn']:
        fragments.append(f'ISBN {edition["isbn"]}')
    if year:
        fragments.append(f'Original work: {original_date(year)}')
    record.update(reference='. '.join(fragments) + '.', missing_fields=missing, notices=notices)
    return record


def reference_notes(record):
    notes = []
    if record['original_year']:
        notes.append(f'Original work date: {original_date(record["original_year"])}; edition date unknown.')
    if record['translator']:
        # The catalog field is a single free-text attribution, not a structured
        # person list. Do not fabricate editor roles or split it into names.
        notes.append(f'Translator as recorded: {record["translator"]}')
    notes.extend(record['notices'])
    notes.append('Not recorded: ' + ', '.join(record['missing_fields']) + '.')
    return notes


def ris_record(record):
    kind = 'BOOK' if record['form'] in {'book', 'collection'} else 'GEN'
    fields = [('TY', kind), ('TI', record['title'])]
    fields.extend(('AU', name) for name in record['authors'])
    for tag, name in [('PB', 'publisher'), ('SN', 'isbn'), ('LA', 'language')]:
        if record[name]:
            fields.append((tag, record[name]))
    fields.extend(('N1', note) for note in reference_notes(record))
    return '\r\n'.join(f'{tag}  - {plain(value)}' for tag, value in fields) + '\r\nER  -\r\n'


def bibtex_record(record):
    fields = [('title', '{' + tex(record['title']) + '}')]
    if record['authors']:
        fields.append(('author', ' and '.join('{' + tex(name) + '}' for name in record['authors'])))
    for name in ('publisher', 'isbn', 'language'):
        if record[name]:
            fields.append((name, tex(record[name])))
    fields.append(('note', tex(' '.join(reference_notes(record)))))
    body = ',\n'.join(f'  {name} = {{{value}}}' for name, value in fields)
    # Numeric catalog identities produce stable, collision-free, ASCII-only keys.
    kind = 'book' if record['form'] in {'book', 'collection'} else 'misc'
    return f'@{kind}{{marginalia{record["work_id"]},\n{body}\n}}\n'


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def bibliography_export(request):
    command = BibliographyCommand(data=request.data)
    command.is_valid(raise_exception=True)
    ids = command.validated_data['work_ids']
    works = {work.pk: work for work in Work.objects.filter(pk__in=ids, is_archived=False)
             .select_related('default_edition').prefetch_related('authors')}
    if len(works) != len(ids):
        raise ValidationError({'work_ids': 'Every selected book must still be active in the catalog. Refresh your selection.'})
    library = {}
    if command.validated_data['prefer_library_editions']:
        library = {item.work_id: item for item in LibraryItem.objects.filter(user=request.user, work_id__in=ids)
                   .only('work_id', 'edition_id', 'reading_basis').select_related('edition')}
    records = [reference_record(works[pk], library.get(pk)) for pk in ids]
    result = {
        'count': len(records), 'references': records,
        'plain_text': '\n\n'.join(record['reference'] + '\n[Not recorded: ' +
                                  ', '.join(record['missing_fields']) + '.]' for record in records) + '\n',
        'ris': '\r\n'.join(ris_record(record) for record in records),
        'bibtex': '\n'.join(bibtex_record(record) for record in records),
        'notes': EXPORT_NOTES,
    }
    return Response(BibliographyExportSerializer(result).data, headers={'Cache-Control': 'private, no-store'})
