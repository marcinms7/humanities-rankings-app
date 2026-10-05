"""Rijksmuseum portraits joined to independently verified catalog authors.

The keyless Linked Art API separates objects, depicted people, reproduction
rights and image files. Follow those explicit links; a search hit, creator's
identity, coat of arms or metadata CC0 notice is never portrait evidence.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from research.media_transport import CandidateRejected, fetch_json

API_HOSTS = frozenset({'id.rijksmuseum.nl', 'data.rijksmuseum.nl'})
IMAGE_HOSTS = frozenset({'iiif.micr.io'})
MAX_OBJECTS = 3
OPEN_RIGHTS = frozenset({
    'https://creativecommons.org/publicdomain/mark/1.0/',
    'https://creativecommons.org/publicdomain/zero/1.0/',
})


def _rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _entity(value):
    return value if isinstance(value, str) and re.fullmatch(r'https://id\.rijksmuseum\.nl/[0-9]+', value) else ''


def _load(uri, kind, fetch):
    if not _entity(uri):
        return {}
    try:
        record = fetch(uri + '?_profile=la-framed', allowed_hosts=API_HOSTS)
    except CandidateRejected:
        return {}
    return record if (isinstance(record, dict) and record.get('id') == uri
                      and record.get('type') == kind) else {}


def _portrait_title(record):
    # Named sitter authorities also appear on bookplates and political scenes.
    # Require a museum-authored portrait title in addition to the authority.
    for row in _rows(record.get('identified_by')):
        title = row.get('content', '')
        if (row.get('type') == 'Name' and isinstance(title, str)
                and re.match(r'^(?:Portret van|Portrait of|Portrait de)\s+\S', title, re.I)):
            return title
    return ''


def _subject(visual, qid):
    subjects = _rows(visual.get('represents'))
    if len(subjects) != 1 or subjects[0].get('type') != 'Person':
        return ''
    subject = subjects[0]
    for row in _rows(subject.get('equivalent')):
        uri = row.get('id', '')
        if isinstance(uri, str) and re.fullmatch(r'https?://(?:www\.)?wikidata\.org/entity/' + re.escape(qid), uri):
            return _entity(subject.get('id'))
    return ''


def _rights(visual):
    # subject_of contains the metadata licence; it does not license the image.
    for right in _rows(visual.get('subject_to')):
        for classification in _rows(right.get('classified_as')):
            if classification.get('id') in OPEN_RIGHTS:
                return classification['id']
    return ''


def _image(digital, visual_uri):
    if not any(row.get('id') == visual_uri for row in _rows(digital.get('digitally_shows'))):
        return ''
    if not any(row.get('content') == 'downloadbaar' for row in _rows(digital.get('referred_to_by'))):
        return ''
    for point in _rows(digital.get('access_point')):
        uri = point.get('id', '')
        match = re.fullmatch(r'https://iiif\.micr\.io/([A-Za-z0-9_-]+)/full/max/0/default\.jpg', str(uri))
        if match:
            # Documented IIIF size selection, keeping the complete image.
            return f'https://iiif.micr.io/{match[1]}/full/600,/0/default.jpg'
    return ''


def _artists(record):
    production = record.get('produced_by', {})
    if not isinstance(production, dict):
        return []
    result = []
    for row in _rows(production.get('carried_out_by')):
        notation = row.get('notation', [])
        for value in _rows(notation if isinstance(notation, list) else [notation]):
            name = value.get('@value')
            if isinstance(name, str) and name and name not in result:
                result.append(name)
    return result[:3]


def candidates(item, fetch=None, identities=None):
    """At most one credited candidate, <=10 museum calls plus identity lookup.

    DBpedia's independent helper requires an authored catalog work (or the
    existing ranked-philosopher exception). Its verified QID must equal the
    museum's sole depicted person; matching names alone never suffice.
    """
    fetch = fetch or fetch_json
    if identities is None:
        from research.media_dbpedia_portraits import verified_identities
        identities = verified_identities
    proven = identities(item, fetch=fetch)
    if len(proven) != 1:
        return []
    identity = proven[0]
    qid = identity.get('wikidata', '')
    if not isinstance(qid, str) or not re.fullmatch(r'Q[1-9][0-9]*', qid):
        return []
    matched = identity.get('matched_works', [])
    if not matched and not (item.get('ranked') and identity.get('ranked_philosopher')):
        return []
    # Search is only candidate discovery, never proof of depiction/identity.
    url = 'https://data.rijksmuseum.nl/search/collection?' + urlencode({
        'aboutActor': item['title'], 'imageAvailable': 'true', 'title': 'portret',
    })
    try:
        result = fetch(url, allowed_hosts=API_HOSTS)
    except CandidateRejected:
        return []
    if not isinstance(result, dict) or not isinstance(result.get('orderedItems'), list):
        raise ValueError('Rijksmuseum returned invalid search metadata')
    for hit in _rows(result['orderedItems'])[:MAX_OBJECTS]:
        object_uri = _entity(hit.get('id'))
        record = _load(object_uri, 'HumanMadeObject', fetch)
        title = _portrait_title(record)
        if not title:
            continue
        for shown in _rows(record.get('shows'))[:1]:
            visual_uri = _entity(shown.get('id'))
            visual = _load(visual_uri, 'VisualItem', fetch)
            subject, rights = _subject(visual, qid), _rights(visual)
            if not subject or not rights:
                continue
            if not any(row.get('id') == object_uri for row in _rows(visual.get('shown_by'))):
                continue
            for shown_digitally in _rows(visual.get('digitally_shown_by'))[:1]:
                digital_uri = _entity(shown_digitally.get('id'))
                digital = _load(digital_uri, 'DigitalObject', fetch)
                image_url = _image(digital, visual_uri)
                if not image_url:
                    continue
                artists = ', '.join(_artists(record))
                return [{
                    'provider': 'rijksmuseum-portraits', 'source': object_uri, 'source_url': object_uri,
                    'image_url': image_url, 'allowed_image_hosts': sorted(IMAGE_HOSTS),
                    'title': title, 'rights': 'Public Domain', 'rights_url': rights,
                    'credit': f'Portrait / historical depiction. {artists + " · " if artists else ""}Rijksmuseum · Public Domain.',
                    'depiction_kind': 'historical_depiction',
                    'identity_basis': 'catalog_author_dbpedia_wikidata_rijksmuseum_subject',
                    'identity_evidence': [
                        f'Catalog-author identity: {identity["uri"]}; matched works: {matched}; '
                        f'ranked philosopher: {bool(identity.get("ranked_philosopher"))}',
                        f'Sole depicted person {subject} is Wikidata {qid}; visual record {visual_uri}',
                    ],
                    'matched_works': matched, 'wikidata_id': qid, 'subject_authority': subject,
                    'ranked_philosopher': bool(identity.get('ranked_philosopher')),
                    'visual_record': visual_uri, 'digital_record': digital_uri,
                }]
    return []
