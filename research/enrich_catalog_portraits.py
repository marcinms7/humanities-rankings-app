"""Resumable Wikimedia portraits with cached identities and credited candidates."""
from __future__ import annotations
import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.enrichment_queue import Queue, exclusive, rotate
from research.operational_state import atomic_state, read_state
from research.media_matching import norm, MATCHER_VERSION
from research.media_transport import fetch_json, CandidateStore, CandidateRejected, ProviderOutage
from research.media_wikimedia import WIKIMEDIA_IMAGE_HOSTS, WIKIMEDIA_IMAGE_POLICY
from research.enrich_media_alternatives import portrait_lookup_item, download_candidates, save_match

RUN = ROOT / 'research/_runs/2026-09-28/portraits'
LEDGER = RUN / 'outcomes.jsonl'
COOLDOWN = RUN / 'provider-cooldown.json'
PREVIOUS_POLICY = MATCHER_VERSION + ':wikimedia-human-work-confirmed-v6:' + WIKIMEDIA_IMAGE_POLICY
POLICY = MATCHER_VERSION + ':wikimedia-human-work-confirmed-v7:' + WIKIMEDIA_IMAGE_POLICY


def cached_candidates(item, store, previous):
    candidates = store.get(item)
    if candidates is None:
        # Existing positive matches satisfy the same human/work/image checks.
        # Reopen old negatives affected by extraction gaps, without rediscovery
        # of already verified images or deletion of their original checkpoints.
        verified = previous.get(item)
        if verified:
            candidates = store.put(item, verified)
    return candidates


def corroborated_works(works, text, work_aliases=None):
    from research.media_text_evidence import corroborated_works as match_evidence
    return match_evidence(works, text, work_aliases)


def metadata_envelope_valid(params, data):
    """Validate consumed JSON shapes without requiring every requested row."""
    if not isinstance(data, dict) or 'error' in data:
        return False
    if 'ids' in params:
        entities = data.get('entities')
        if not isinstance(entities, dict):
            return False
        for entity in entities.values():
            if not isinstance(entity, dict) or not isinstance(entity.get('claims', {}), dict):
                return False
            for prop in ('P31', 'P106', 'P18'):
                claims = entity.get('claims', {}).get(prop, [])
                if not isinstance(claims, list):
                    return False
                for claim in claims:
                    if not isinstance(claim, dict) or not isinstance(claim.get('mainsnak', {}), dict):
                        return False
                    if not isinstance(claim.get('mainsnak', {}).get('datavalue', {}), dict):
                        return False
        return True
    query = data.get('query')
    if not isinstance(query, dict) or not isinstance(query.get('pages'), list):
        return False
    for field in ('redirects', 'normalized'):
        rows = query.get(field, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) or
            not isinstance(row.get('from'), str) or not isinstance(row.get('to'), str) for row in rows):
            return False
    for page in query['pages']:
        if not isinstance(page, dict):
            return False
        if any(field in page and not isinstance(page[field], str) for field in ('title', 'extract')):
            return False
        if not isinstance(page.get('pageprops', {}), dict):
            return False
        if 'wikibase_item' in page.get('pageprops', {}) and not isinstance(page['pageprops']['wikibase_item'], str):
            return False
        images = page.get('imageinfo', [])
        if not isinstance(images, list):
            return False
        for image in images:
            if not isinstance(image, dict) or not isinstance(image.get('extmetadata', {}), dict):
                return False
            if any(field in image and not isinstance(image[field], str)
                   for field in ('url', 'thumburl', 'descriptionurl')):
                return False
            for field in ('Artist', 'LicenseShortName'):
                metadata = image.get('extmetadata', {}).get(field, {})
                if not isinstance(metadata, dict) or not isinstance(metadata.get('value', ''), str):
                    return False
    return True


def metadata_response_complete(params, data):
    """Incomplete successful responses remain usable but must not be cached."""
    if not metadata_envelope_valid(params, data):
        return False
    if 'ids' in params:
        entities = data.get('entities')
        return isinstance(entities, dict) and all(
            isinstance(entities.get(qid), dict) and
            ('missing' in entities[qid] or isinstance(entities[qid].get('claims'), dict))
            for qid in params['ids'].split('|'))
    query = data.get('query')
    if not isinstance(query, dict) or not isinstance(query.get('pages'), list):
        return False
    pages = [page for page in query['pages'] if isinstance(page, dict)]
    if 'pageids' in params:
        by_id = {str(page.get('pageid')): page for page in pages}
        requested = [by_id.get(identity) for identity in str(params['pageids']).split('|')]
    elif 'titles' in params:
        redirects = {norm(row['from']): norm(row['to'])
                     for row in query.get('redirects', []) + query.get('normalized', [])
                     if isinstance(row, dict) and 'from' in row and 'to' in row}
        by_title = {norm(page['title']): page for page in pages if isinstance(page.get('title'), str)}
        requested = []
        for title in params['titles'].split('|'):
            name, seen = norm(title), set()
            while name in redirects and name not in seen:
                seen.add(name)
                name = redirects[name]
            requested.append(by_title.get(name))
    else:
        return False
    props = params.get('prop', '').split('|')
    return all(page is not None and ('missing' in page or 'invalid' in page or (
        ('extracts' not in props or isinstance(page.get('extract'), str)) and
        ('imageinfo' not in props or isinstance(page.get('imageinfo'), list)))) for page in requested)


def get_json(host, params):
    data = fetch_json(host + '?' + urlencode({**params, 'format': 'json', 'formatversion': 2, 'maxlag': 5}),
                      allowed_hosts={host.split('/')[2]},
                      json_cacheable=lambda data: metadata_response_complete(params, data))
    if not isinstance(data, dict):
        raise CandidateRejected('Invalid Wikimedia metadata object')
    if 'error' in data:
        # Wikimedia may return HTTP200 with maxlag/ratelimited API errors.
        raise ProviderOutage('Wikimedia API temporarily unavailable')
    if not metadata_envelope_valid(params, data):
        raise CandidateRejected('Malformed Wikimedia metadata envelope')
    return data


class DiscoveryResult(dict):
    """Candidate mapping plus explicit checkpoints for interrupted discovery."""
    def __init__(self, items):
        super().__init__((item['id'], []) for item in items)
        self.completed = set()
        self.deferred = {}
        self.outage = None

    def interrupt(self, error):
        self.outage = error
        self.deferred = {identity: error for identity in self if identity not in self.completed}


def wikimedia_candidates(items):
    """Keep verified records when a later metadata request is interrupted.

    Dict access stays compatible with provider callers. Only ``completed`` IDs
    can become a durable negative candidate cache; ``deferred`` IDs retain their
    individual retry budgets and must be looked up again after the outage.
    """
    result = DiscoveryResult(items)
    try:
        _discover_wikimedia(items, result)
    except ProviderOutage as error:
        result.interrupt(error)
    except CandidateRejected:
        result.interrupt(ProviderOutage('Wikimedia metadata response could not be verified'))
    return result


def _discover_wikimedia(items, result):
    redirects, pages, entities, files = {}, {}, {}, {}

    def incomplete(stage):
        return ProviderOutage('Incomplete Wikimedia ' + stage + ' response')

    def find_page(name):
        name, seen = norm(name), set()
        while name in redirects and name not in seen:
            seen.add(name)
            name = redirects[name]
        return pages.get(name)

    def load_titles(names):
        names = list(dict.fromkeys(names))
        # TextExtracts serves at most twenty intros per request.
        for start in range(0, len(names), 20):
            requested = names[start:start + 20]
            data = get_json('https://en.wikipedia.org/w/api.php', {'action': 'query',
                'titles': '|'.join(requested), 'redirects': 1,
                'prop': 'extracts|pageprops|info', 'explaintext': 1, 'exintro': 1,
                'exlimit': 'max', 'inprop': 'url'}).get('query', {})
            redirects.update({norm(row['from']): norm(row['to'])
                              for row in data.get('redirects', []) + data.get('normalized', [])})
            pages.update({norm(page['title']): page for page in data.get('pages', [])
                          if isinstance(page, dict) and isinstance(page.get('title'), str)})
            # MediaWiki includes an explicit `missing` page for nonexistent
            # titles. A silently omitted page is not evidence of no match.
            if any(find_page(name) is None for name in requested):
                raise incomplete('page-title')

    def matches(item, text):
        return corroborated_works(item.get('works', item.get('authors', [])), text,
                                  item.get('work_aliases', {}))

    def claim_id(claim, identity):
        value = claim.get('mainsnak', {}).get('datavalue', {}).get('value')
        return claim.get('rank') != 'deprecated' and isinstance(value, dict) and value.get('id') == identity

    def add_images(rows):
        if not rows:
            return
        wanted = list(dict.fromkeys(filename for row in rows for filename in row['filenames']))
        pending = [filename for filename in wanted if norm(filename) not in files]

        def checkpoint():
            for row in rows:
                item, page = row['item'], row['page']
                found = []
                for filename in row['filenames']:
                    info = files.get(norm(filename), {}).get('imageinfo', [])
                    if not info:
                        continue
                    metadata = info[0]
                    ext = metadata.get('extmetadata', {})
                    licence = ext.get('LicenseShortName', {}).get('value', '')
                    url = metadata.get('thumburl') or metadata.get('url')
                    if not url or not licence:
                        continue
                    source = metadata.get('descriptionurl') or 'https://commons.wikimedia.org/wiki/File:' + quote(filename.replace(' ', '_'))
                    artist = html.unescape(re.sub('<[^>]+>', ' ', ext.get('Artist', {}).get('value', ''))).strip()
                    found.append({'source': source, 'image_url': url,
                        'allowed_image_hosts': list(WIKIMEDIA_IMAGE_HOSTS),
                        'credit': f'Portrait / historical depiction. {artist[:110]} · {licence[:65]}.',
                        'wikidata': row['qid'], 'page_url': page.get('fullurl'),
                        'matched_works': row['matched'], 'ranked_philosopher': row['philosopher'],
                        'file': filename, 'image_metadata': metadata})
                result[item['id']] = found
                # A verified positive is useful even if an alternative image
                # was omitted. Empty results require every file's response.
                if found or all(norm(name) in files and any(field in files[norm(name)]
                    for field in ('imageinfo', 'missing', 'invalid')) for name in row['filenames']):
                    result.completed.add(item['id'])

        checkpoint()
        for start in range(0, len(pending), 50):
            requested = pending[start:start + 50]
            response = get_json('https://commons.wikimedia.org/w/api.php', {'action': 'query',
                'titles': '|'.join('File:' + name for name in requested),
                'prop': 'imageinfo', 'iiprop': 'url|mime|extmetadata', 'iiurlwidth': 500})
            files.update({norm(page['title'].removeprefix('File:')): page
                          for page in response.get('query', {}).get('pages', [])
                          if isinstance(page, dict) and isinstance(page.get('title'), str)})
            checkpoint()
            if any(norm(name) not in files or not any(field in files[norm(name)]
                   for field in ('imageinfo', 'missing', 'invalid')) for name in requested):
                raise incomplete('Commons image')

    def resolve(group, *, qualified=False):
        names = {item['id']: ([item['title'] + ' (' + role + ')' for role in
                    ('philosopher', 'novelist', 'writer', 'poet', 'historian', 'author')]
                    if qualified else [item['title'], *item.get('title_aliases', [])][:3])
                 for item in group}
        load_titles([name for item_names in names.values() for name in item_names])
        choices_by_id, fallback = {}, []
        for item in group:
            choices = {}
            for name in names[item['id']]:
                page = find_page(name)
                props = page.get('pageprops', {})
                qid = props.get('wikibase_item', '')
                if 'disambiguation' not in props and re.fullmatch(r'Q\d+', qid):
                    choices[qid] = page
            if not qualified and len(choices) > 1:
                # Reviewed aliases must not resolve to different identities.
                result.completed.add(item['id'])
            elif not choices:
                if qualified:
                    result.completed.add(item['id'])
                else:
                    fallback.append(item)
            else:
                choices_by_id[item['id']] = choices
        needed = list(dict.fromkeys(qid for choices in choices_by_id.values() for qid in choices
                                    if qid not in entities))
        for start in range(0, len(needed), 50):
            requested = needed[start:start + 50]
            response = get_json('https://www.wikidata.org/w/api.php', {'action': 'wbgetentities',
                'ids': '|'.join(requested), 'props': 'claims'}).get('entities', {})
            entities.update(response)
            if any(qid not in response or not isinstance(response[qid], dict)
                   or ('claims' not in response[qid] and 'missing' not in response[qid])
                   for qid in requested):
                raise incomplete('entity')
        immediate, needs_extract = [], []

        def finish_identity(item, verified):
            if len(verified) == 1:
                row = verified[0]
                if row['filenames']:
                    return row
                result.completed.add(item['id'])
            elif len(verified) > 1 or qualified:
                result.completed.add(item['id'])
            else:
                fallback.append(item)
            return None

        for item in group:
            choices = choices_by_id.get(item['id'])
            if not choices:
                continue
            verified, uncertain = [], []
            for qid, page in choices.items():
                claims = entities[qid].get('claims', {})
                if not any(claim_id(claim, 'Q5') for claim in claims.get('P31', [])):
                    continue
                occupation = any(claim_id(claim, 'Q4964182') for claim in claims.get('P106', []))
                extract = page.get('extract', '')
                philosopher = bool(item.get('ranked', False) and occupation and
                                   re.search(r'\bphilosopher\b', extract[:2500], re.I))
                statements = sorted(claims.get('P18', []), key=lambda claim: claim.get('rank') != 'preferred')
                filenames = list(dict.fromkeys(claim.get('mainsnak', {}).get('datavalue', {}).get('value')
                    for claim in statements if claim.get('rank') != 'deprecated'
                    and isinstance(claim.get('mainsnak', {}).get('datavalue', {}).get('value'), str)))[:3]
                row = {'item': item, 'page': page, 'qid': qid, 'filenames': filenames,
                       'matched': matches(item, extract), 'philosopher': philosopher}
                if row['matched'] or philosopher:
                    verified.append(row)
                elif filenames and item.get('works', item.get('authors', [])):
                    uncertain.append(row)
            if uncertain:
                needs_extract.append((item, verified, uncertain))
            else:
                row = finish_identity(item, verified)
                if row:
                    immediate.append(row)
        # Complete cheap positive matches before requesting full articles for
        # harder people. A later outage must not throw away these candidates.
        add_images(immediate)
        for item, verified, uncertain in needs_extract:
            for row in uncertain:
                page_id = row['page'].get('pageid')
                if not isinstance(page_id, int) or page_id <= 0:
                    raise incomplete('page identity')
                # Keep bibliography markup: its emphasized titles and section
                # boundaries supply evidence that plaintext drops.
                detail = get_json('https://en.wikipedia.org/w/api.php', {'action': 'query',
                    'pageids': page_id, 'prop': 'extracts'})
                full_pages = detail.get('query', {}).get('pages', [])
                full_page = next((page for page in full_pages if page.get('pageid') == page_id), None)
                if full_page is None or ('extract' not in full_page and 'missing' not in full_page):
                    raise incomplete('full-article extract')
                row['matched'] = matches(item, full_page.get('extract', ''))
                if row['matched']:
                    verified.append(row)
            row = finish_identity(item, verified)
            if row:
                add_images([row])
        if fallback and not qualified:
            # An exact title may belong to a namesake (e.g. an actor). Failed
            # identity corroboration still gets one bounded qualified lookup.
            resolve(fallback, qualified=True)

    resolve(items)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--person-id', type=int)
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    stats = {'queued': 0, 'processed': 0, 'portraits': 0, 'provider_errors': 0, 'image_deferred': 0}
    cooldown = read_state(COOLDOWN, cooldown=True)
    if cooldown.get('until', 0) > time.time():
        saved_error = ProviderOutage(cooldown.get('reason', 'Provider cooldown is active'),
            retry_after=cooldown['until'], status=cooldown.get('http_status'),
            outage_type=cooldown.get('outage_type', 'unavailable'))
        atomic_state(RUN / 'latest-stats.json', {**stats, 'provider_outage': True,
            'retry_after': cooldown['until'], **saved_error.state_fields()})
        return
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.settings')
    import django
    django.setup()
    from django.db.models import Count, Q
    from backend.core.models import Person
    from backend.core.search import aliases
    known_aliases = aliases()
    queue = Queue('portraits', LEDGER)
    rotate(LEDGER)
    people = Person.objects.filter(is_archived=False, portrait='').prefetch_related('works').annotate(
        ranked=Count('rankingentry', filter=Q(rankingentry__is_archived=False,
            rankingentry__ranking__is_archived=False, rankingentry__ranking__owner__isnull=True), distinct=True))
    if args.person_id:
        people = people.filter(pk=args.person_id)
    items = [portrait_lookup_item(person, known_aliases) for person in people.order_by('-ranked', 'pk')]
    items = [item for item in items if queue.due(item, POLICY, retry=args.retry)]
    store = CandidateStore('wikimedia-portraits', version=POLICY)
    previous = CandidateStore('wikimedia-portraits', version=PREVIOUS_POLICY)
    ready = {item['id']: candidates for item in items
             if (candidates := cached_candidates(item, store, previous)) is not None}
    # Download already verified images before spending requests on discovery.
    items.sort(key=lambda item: (not bool(ready.get(item['id'])), queue.priority(item)))
    if args.limit:
        items = items[:args.limit]
    stats['queued'] = len(items)
    stopped = False
    deferred_error = None
    with LEDGER.open('a') as audit:
        def finish(item, record):
            record.update(work_id=item['id'], person_id=item['id'], name=item['title'])
            queue.finish(item, record, audit)
            stats['processed'] += 1
            stats['provider_errors'] = max(stats['provider_errors'], queue.batch_errors - stats['image_deferred'])
            atomic_state(RUN / 'latest-stats.json', {**stats, **queue.summary()})
            print(json.dumps({key: record[key] for key in ('person_id', 'name', 'status')}, ensure_ascii=False), flush=True)
        def remember_outage(error):
            nonlocal deferred_error
            errors = [value for value in (deferred_error, error) if value is not None]
            strongest = max(errors, key=lambda value: (
                value.status in {403, 429}, value.outage_type != 'maxlag', value.retry_after))
            deferred_error = ProviderOutage(strongest.reason,
                retry_after=max(value.retry_after for value in errors),
                status=strongest.status, outage_type=strongest.outage_type)
            atomic_state(COOLDOWN, {'until': deferred_error.retry_after, **deferred_error.state_fields()})
            stats.update(provider_outage=True, provider_errors=1, retry_after=deferred_error.retry_after,
                         **deferred_error.state_fields())

        def defer(item, error, diagnostics=None, *, stage='metadata'):
            if stage == 'image':
                stats['image_deferred'] += 1
                finish(item, {'status': 'image_deferred', 'provider_outage': True,
                              'retry_after': error.retry_after, 'error': error.reason,
                              'outage_stage': stage, **error.state_fields(), **(diagnostics or {})})
                return
            remember_outage(error)
            finish(item, {'status': 'provider_deferred', 'provider_outage': True,
                          'retry_after': error.retry_after, 'error': error.reason,
                          'outage_stage': stage, **error.state_fields(), **(diagnostics or {})})
        for start in range(0, len(items), 10):
            batch = items[start:start + 10]
            cached = {item['id']: ready.get(item['id']) for item in batch}
            missing = [item for item in batch if cached[item['id']] is None]
            if missing:
                try:
                    found = wikimedia_candidates(missing)
                    for item in missing:
                        if item['id'] in getattr(found, 'completed', found):
                            cached[item['id']] = found.get(item['id'], [])
                            cached[item['id']] = store.put(item, cached[item['id']])
                    for item in missing:
                        if error := getattr(found, 'deferred', {}).get(item['id']):
                            defer(item, error)
                    if getattr(found, 'outage', None) is not None:
                        remember_outage(found.outage)
                        stopped = True
                except ProviderOutage as error:
                    # Only the probe receives a deferred record. Other members
                    # remain untouched; one outage cannot exhaust twenty people.
                    defer(missing[0], error)
                    stopped = True
                except CandidateRejected as error:
                    finish(missing[0], {'status': 'provider_error', 'error': str(error)})
                    stopped = True
            for item in batch:
                if cached[item['id']] is None:
                    continue  # Preserve untouched records after metadata failure.
                try:
                    diagnostics = {}
                    match = download_candidates(cached[item['id']], diagnostics=diagnostics)
                    status = save_match('wikimedia-portraits', item, match) if match else 'no_safe_match'
                    record = {'status': status, **diagnostics}
                    if match:
                        record.update({key: value for key, value in match.items() if key != 'blob'})
                    stats['portraits'] += status == 'covered'
                    finish(item, record)
                except ProviderOutage as error:
                    defer(item, error, diagnostics, stage='image')
                    # Host cooldowns still apply. An image outage must not
                    # stop healthy metadata services or unrelated image hosts.
                    continue
                except Exception as error:
                    finish(item, {'status': 'provider_error', 'error': type(error).__name__})
                    if queue.batch_errors - stats['image_deferred'] >= 3:
                        stopped = True
                        break
            if stopped:
                break
    stats.update(queue.summary())
    queue.close()
    atomic_state(RUN / 'latest-stats.json', stats)
    print(json.dumps(stats), flush=True)


if __name__ == '__main__':
    with exclusive('portraits'):
        main()
