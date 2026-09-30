"""Conservative alternate providers; durable independent queues, no private writes."""
from __future__ import annotations
import argparse
import io
import json
import os
import re
import html
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.enrichment_queue import Queue, exclusive, rotate
from research.operational_state import atomic_state, read_state
from research.enrich_catalog_covers_public import same_title, same_author
from PIL import Image

RUN = ROOT / 'research/_runs/media-completion'
LAST = 0.0
HEADERS = {'User-Agent': 'Marginalia/1.0 (humanities catalogue metadata lookup)'}


def fetch(url, image=False):
    global LAST
    time.sleep(max(0, 1.2 - (time.monotonic() - LAST)))
    LAST = time.monotonic()
    with urlopen(Request(url, headers=HEADERS), timeout=25) as response:
        blob = response.read(10 * 1024 * 1024 + 1)
    if len(blob) > 10 * 1024 * 1024:
        raise ValueError('Response exceeds 10 MB')
    return blob if image else json.loads(blob)


def validate_image(blob):
    with Image.open(io.BytesIO(blob)) as picture:
        if min(picture.size) < 80 or max(picture.size) / min(picture.size) > 5:
            raise ValueError('Image is too small or has an unsuitable aspect ratio')
        extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}.get(picture.format)
        if not extension:
            raise ValueError('Unsupported image format')
        picture.verify()
    return extension


def google_cover(item):
    if not item['authors']:
        return None
    params = {'q': f'intitle:"{item["title"]}" inauthor:"{item["authors"][0]}"', 'maxResults': 40, 'printType': 'books'}
    if os.environ.get('GOOGLE_BOOKS_API_KEY'):
        params['key'] = os.environ['GOOGLE_BOOKS_API_KEY']
    data = fetch('https://www.googleapis.com/books/v1/volumes?' + urlencode(params))
    if 'error' in data:
        raise ValueError('Google Books API error')
    for volume in data.get('items', []):
        info = volume.get('volumeInfo', {})
        if not same_title(item['title'], info.get('title', ''))[0] or not same_author(item['authors'], info.get('authors', [])):
            continue
        images = info.get('imageLinks', {})
        url = next((images[k] for k in ('extraLarge', 'large', 'medium', 'small', 'thumbnail') if images.get(k)), None)
        if not url:
            continue
        url = url.replace('http://', 'https://', 1)
        return {'source': 'https://books.google.com/books?id=' + quote(volume['id']),
                'image_url': url, 'blob': fetch(url, image=True),
                'credit': 'Google Books cover; rights remain with the publisher / cover artist.',
                'matched_title': info['title'], 'matched_authors': info.get('authors', [])}
    return None


def wikipedia_cover(item):
    if not item['authors']:
        return None
    titles = '|'.join([item['title'], item['title'] + ' (novel)', item['title'] + ' (book)'])
    params = {'action': 'query', 'format': 'json', 'formatversion': 2, 'titles': titles,
              'redirects': 1, 'prop': 'revisions|info|pageprops', 'rvprop': 'content',
              'rvslots': 'main', 'inprop': 'url', 'maxlag': 5}
    data = fetch('https://en.wikipedia.org/w/api.php?' + urlencode(params))
    if 'error' in data:
        raise ValueError('Wikipedia API error')
    for page in data.get('query', {}).get('pages', []):
        title = re.sub(r' \((?:novel|book)\)$', '', page.get('title', ''))
        if not same_title(item['title'], title)[0] or 'disambiguation' in page.get('pageprops', {}):
            continue
        revisions = page.get('revisions', [])
        if not revisions:
            continue
        content = revisions[0].get('slots', {}).get('main', {}).get('content', '')
        if not re.search(r'\{\{Infobox book\b', content, re.I):
            continue
        # Restrict fields to the book infobox prefix, not another image elsewhere.
        infobox = re.split(r'\{\{Infobox book\b', content, flags=re.I)[1].split('\n}}', 1)[0]
        def field(key):
            match = re.search(r'^\s*\|\s*' + key + r'\s*=([^\n]*)', infobox, re.M | re.I)
            return match.group(1).strip() if match else ''
        author = field('author')
        author = re.sub(r'\[\[(?:[^]|]*\|)?([^]]+)\]\]', r'\1', author)
        author = html.unescape(re.sub(r'<[^>]+>', ' ', author)).strip()
        if not same_author(item['authors'], [author]):
            continue
        caption = field('caption')
        if not re.search(r'\bcover\b|\bfirst edition\b', caption, re.I):
            continue
        filename = re.sub(r'^(?:File|Image):', '', field('image'), flags=re.I)
        if not re.fullmatch(r'[^{}\[\]|<>]+\.(?:jpg|jpeg|png|webp|gif)', filename, re.I):
            continue
        info = fetch('https://en.wikipedia.org/w/api.php?' + urlencode({
            'action': 'query', 'format': 'json', 'formatversion': 2, 'titles': 'File:' + filename,
            'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 500, 'maxlag': 5}))
        if 'error' in info:
            raise ValueError('Wikipedia image API error')
        for filepage in info.get('query', {}).get('pages', []):
            for image in filepage.get('imageinfo', []):
                metadata = image.get('extmetadata', {})
                licence = metadata.get('LicenseShortName', {}).get('value', '')
                if not licence or not image.get('descriptionurl'):
                    continue
                url = image.get('thumburl') or image.get('url')
                if not url:
                    continue
                artist = html.unescape(re.sub('<[^>]+>', ' ', metadata.get('Artist', {}).get('value', ''))).strip()
                return {'source': image['descriptionurl'], 'article': page.get('fullurl'),
                        'image_url': url, 'blob': fetch(url, image=True), 'matched_title': title,
                        'matched_author': author, 'caption': caption, 'metadata': metadata,
                        'credit': f'Wikipedia book cover. {artist[:100]} · {licence[:60]}.'}
    return None


def openlibrary_portrait(item):
    if not item['authors']:
        return None  # A matching name alone is not enough.
    data = fetch('https://openlibrary.org/search/authors.json?' + urlencode({'q': item['title'], 'limit': 20}))
    matches = []
    for author in data.get('docs', []):
        if not same_author([item['title']], [author.get('name', '')]):
            continue
        key = author.get('key', '').split('/')[-1]
        if not key.startswith('OL') or not key.endswith('A'):
            continue
        # Confirm a credited catalog work on the author record, not a name-only photo.
        works = [author.get('top_work', '')]
        matched = [title for title in item['authors'] if any(same_title(title, found)[0] for found in works)]
        if not matched:
            entries = fetch(f'https://openlibrary.org/authors/{key}/works.json?limit=100').get('entries', [])
            matched = [title for title in item['authors'] if any(same_title(title, entry.get('title', ''))[0] for entry in entries)]
        if not matched:
            continue
        record = fetch(f'https://openlibrary.org/authors/{key}.json')
        photos = [photo for photo in record.get('photos', []) if isinstance(photo, int) and photo > 0]
        if photos:
            matches.append((key, photos[0], matched))
    if len(matches) != 1:
        return None  # Keep ambiguous identities for review.
    key, photo, works = matches[0]
    url = f'https://covers.openlibrary.org/a/id/{photo}-L.jpg?default=false'
    return {'source': f'https://openlibrary.org/authors/{key}', 'image_url': url,
            'blob': fetch(url, image=True), 'matched_works': works,
            'credit': 'Portrait / historical depiction via Open Library. Original photographer and reuse licence require review.'}


def save_match(kind, item, match):
    from django.core.files.base import ContentFile
    from django.db import transaction
    from backend.core.models import Work, Edition, Person
    extension = validate_image(match['blob'])
    with transaction.atomic():
        if kind.endswith('-covers'):
            work = Work.objects.select_for_update().get(pk=item['id'])
            if work.is_archived or work.title != item['title'] or sorted(work.authors.values_list('name', flat=True)) != sorted(item['authors']):
                return 'identity_review_changed_during_lookup'
            edition = work.default_edition
            if edition and edition.cover:
                return 'preserved_existing'
            if edition and edition.is_archived:
                return 'identity_review_archived_edition'
            if edition is None:
                edition = Edition.objects.create(work=work, language='Not verified', translation_notes='Representative work cover; exact edition and language require verification.')
                work.default_edition = edition
                work.save(update_fields=['default_edition', 'updated_at'])
            edition.cover.save(f'{kind}-{item["id"]}.{extension}', ContentFile(match['blob']), save=False)
            edition.cover_source_url = match['source']
            edition.cover_basis = 'representative_work'
            edition.image_attribution = (match['credit'] + ' ' + match['source'])[:500]
            edition.save(update_fields=['cover', 'cover_source_url', 'cover_basis', 'image_attribution', 'updated_at'])
        else:
            person = Person.objects.select_for_update().get(pk=item['id'])
            current_works = sorted(person.works.filter(is_archived=False).values_list('title', flat=True))
            if person.is_archived or person.name != item['title'] or current_works != sorted(item['authors']):
                return 'identity_review_changed_during_lookup'
            if person.portrait:
                return 'preserved_existing'
            person.portrait.save(f'openlibrary-{item["id"]}.{extension}', ContentFile(match['blob']), save=False)
            person.image_attribution = (match['credit'] + ' ' + match['source'])[:500]
            person.save(update_fields=['portrait', 'image_attribution', 'updated_at'])
    return 'covered'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['google-covers', 'wikipedia-covers', 'openlibrary-portraits'])
    parser.add_argument('--limit', type=int, default=25)
    args = parser.parse_args()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
    import django
    django.setup()
    from backend.core.models import Work, Person
    RUN.mkdir(parents=True, exist_ok=True)
    stats_path = RUN / f'{args.provider}-stats.json'
    cooldown = RUN / f'{args.provider}-cooldown.json'
    stats = {'processed': 0, 'covered': 0, 'provider_errors': 0}
    if cooldown.exists() and read_state(cooldown, cooldown=True).get('until', 0) > time.time():
        stats['retry_after'] = read_state(cooldown, cooldown=True)['until']
        atomic_state(stats_path, stats)
        return
    ledger = RUN / f'{args.provider}.jsonl'
    queue = Queue(args.provider, ledger)
    rotate(ledger)
    if args.provider.endswith('-covers'):
        records = Work.objects.filter(is_archived=False).select_related('default_edition').prefetch_related('authors').order_by('pk')
        items = [{'id': w.pk, 'title': w.title, 'authors': [p.name for p in w.authors.all()]} for w in records if not w.default_edition or not w.default_edition.cover]
        lookup = google_cover if args.provider == 'google-covers' else wikipedia_cover
    else:
        records = Person.objects.filter(is_archived=False, portrait='').prefetch_related('works').order_by('pk')
        items = [{'id': p.pk, 'title': p.name, 'authors': [w.title for w in p.works.all() if not w.is_archived]} for p in records]
        lookup = openlibrary_portrait
    items = [item for item in items if queue.due(item, 'strict-title-author-or-name-work-v1')]
    items.sort(key=queue.priority)
    if args.limit:
        items = items[:args.limit]
    with ledger.open('a') as audit:
        for item in items:
            result = {'work_id': item['id'], 'title': item['title'], 'provider': args.provider}
            try:
                match = lookup(item)
                result['status'] = save_match(args.provider, item, match) if match else 'no_safe_match'
                if match:
                    result.update({key: value for key, value in match.items() if key != 'blob'})
                stats['covered'] += result['status'] == 'covered'
            except HTTPError as error:
                # Never log URLs containing API keys.
                result.update(status='provider_error', error=f'HTTP {error.code}')
                if error.code in (403, 429, 503):
                    from email.utils import parsedate_to_datetime
                    raw = error.headers.get('Retry-After', '900')
                    try:
                        delay = float(raw)
                    except ValueError:
                        try:
                            delay = parsedate_to_datetime(raw).timestamp() - time.time()
                        except (ValueError, TypeError):
                            delay = 900
                    until = time.time() + max(900, delay)
                    atomic_state(cooldown, {'until': until, 'reason': f'HTTP {error.code}'})
                    stats['retry_after'] = until
            except Exception as error:
                result.update(status='provider_error', error=type(error).__name__)
            queue.finish(item, result, audit)
            stats['processed'] += 1
            stats['provider_errors'] = queue.batch_errors
            print(json.dumps({k: result[k] for k in ('work_id', 'title', 'status', 'provider')}, ensure_ascii=False), flush=True)
            atomic_state(stats_path, {**stats, **queue.summary()})
            if stats.get('retry_after') or queue.batch_errors >= 3:
                break
    stats.update(queue.summary())
    queue.close()
    atomic_state(stats_path, stats)


if __name__ == '__main__':
    with exclusive('media-alternatives'):
        main()
