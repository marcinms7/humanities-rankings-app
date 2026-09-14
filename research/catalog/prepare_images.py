"""Prepare reviewable public-image manifests and curl configs; no downloads or DB writes."""
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit


def commons_config(pages_path, output, config):
    pages = json.loads(Path(pages_path).read_text())['query']['pages'].values()
    titles = ['File:' + unquote(urlsplit(p['original']['source']).path.rsplit('/', 1)[-1]) for p in pages if 'original' in p]
    url = 'https://commons.wikimedia.org/w/api.php?' + urlencode(dict(action='query', format='json', prop='imageinfo', iiprop='url|extmetadata', iiurlwidth=500, titles='|'.join(titles)))
    Path(config).write_text('url = ' + json.dumps(url) + '\noutput = ' + json.dumps(output) + '\n')


def manifest(pages_path, commons_path, batch):
    root = Path(f'research/catalog/images-{batch}')
    root.mkdir(exist_ok=True)
    pages = json.loads(Path(commons_path).read_text())['query']['pages'].values()
    original = json.loads(Path(pages_path).read_text())['query']['pages'].values()
    byfile = {unquote(urlsplit(p['original']['source']).path.rsplit('/', 1)[-1]).replace('_', ' '): p['title'] for p in original if 'original' in p}
    records = []
    for p in pages:
        i = p['imageinfo'][0]
        m = i['extmetadata']
        clean = lambda k: html.unescape(re.sub('<[^>]+>', '', m.get(k, {}).get('value', ''))).strip()
        name = byfile[p['title'][5:].replace('_', ' ')]
        key = re.sub('[^a-z0-9]+', '-', name.lower()).strip('-')
        path = root / (key + Path(urlsplit(i['url']).path).suffix)
        records.append(dict(kind='portrait', person_name=name, download_url=i.get('thumburl', i['url']).split('?')[0], local_path=str(path), source_url=i['descriptionurl'], artist=clean('Artist'), license=clean('LicenseShortName'), license_url=clean('LicenseUrl'), description=clean('ImageDescription'), attribution=f"{clean('Artist')}; {clean('LicenseShortName')}. {i['descriptionurl']}" + (' Historical depiction, not a contemporary likeness.' if name == 'Murasaki Shikibu' else '')))
    return records


if __name__ == '__main__':
    if sys.argv[1] == 'first':
        records = manifest('/tmp/ranking-author-images.json', '/tmp/ranking-commons-metadata.json', '01')
        for batch in ['01', '02']:
            for w in json.loads(Path(f'research/catalog/batch-{batch}.json').read_text())['works']:
                e = w['edition']
                records.append(dict(kind='cover', isbn=e['isbn'], download_url='https://images.penguinrandomhouse.com/cover/' + e['isbn'], local_path=f"research/catalog/images-01/{e['isbn']}.jpg", source_url=e['source_url'], license='Publisher cover artwork; copyright retained by rights holders', artist=e['publisher'], attribution=f"Cover: {e['publisher']}. Publisher-supplied image for ISBN {e['isbn']}; copyright remains with rights holders."))
        Path('research/catalog/images-01.json').write_text(json.dumps(dict(consulted_on='2026-09-13', images=records), ensure_ascii=False, indent=2) + '\n')
        Path('/tmp/ranking-images-curl.conf').write_text('\n'.join('url = ' + json.dumps(r['download_url']) + '\noutput = ' + json.dumps(r['local_path']) for r in records) + '\n')
        titles = ['Plato', 'Aristotle', 'Immanuel Kant', 'Confucius', 'David Hume', 'Avicenna', 'Nagarjuna', 'Thomas Aquinas', 'Ludwig Wittgenstein', 'Adi Shankara', 'Baruch Spinoza', 'Friedrich Nietzsche', 'Simone de Beauvoir', 'Al-Ghazali', 'Mencius', 'Hannah Arendt', 'John Rawls', 'Frantz Fanon', 'Xunzi', 'Mozi', 'John Stuart Mill', 'B. R. Ambedkar', 'Kwasi Wiredu', 'Mary Wollstonecraft', 'Mulla Sadra', 'W. E. B. Du Bois', 'Charles Darwin', 'Rachel Carson']
        url = 'https://en.wikipedia.org/w/api.php?' + urlencode(dict(action='query', format='json', prop='pageimages', piprop='original', redirects=1, titles='|'.join(titles)))
        Path('/tmp/ranking-philosophers-curl.conf').write_text('url = ' + json.dumps(url) + '\noutput = "/tmp/ranking-philosopher-images.json"\n')
    elif sys.argv[1] == 'philosophers-metadata':
        commons_config('/tmp/ranking-philosopher-images.json', '/tmp/ranking-philosopher-commons.json', '/tmp/ranking-philosopher-commons.conf')
