#!/usr/bin/env python3
"""Create copy-ready expansion briefs containing each saved source register."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research' / '_prompts' / '2026-09-14-country-ranking-expansion'

TARGETS = {
    'books-japan': {
        'filename': 'japan-books-all-time-expansion-prompt.txt',
        'label': 'Japanese books',
        'title': 'Japanese books',
        'coverage': 'Japanese and international perspectives: Japanese newspapers, literary magazines, universities, libraries, prize archives, publishers, reader communities, criticism, scholarship, translation studies, and multilingual forums. Cover classical, medieval, early-modern, modern and contemporary literature; fiction, poetry, drama, essays, criticism, religious/philosophical classics and major collections where justified.',
    },
    'books-china': {
        'filename': 'chinese-language-books-all-time-expansion-prompt.txt',
        'label': 'books from the Chinese-language tradition',
        'title': 'books from the Chinese-language tradition',
        'coverage': 'Chinese and international perspectives across mainland China, Taiwan, Hong Kong and historically relevant Sinitic traditions. Use Chinese literary histories, universities, libraries, prize archives, literary journals, publishers, Douban and other reader communities, scholarship, translation studies and comparative criticism. Cover classical, imperial, republican, modern and contemporary writing, including fiction, poetry, drama, essays, philosophy, history and major collections where justified.',
    },
    'books-poland': {
        'filename': 'polish-books-all-time-expansion-prompt.txt',
        'label': 'Polish books',
        'title': 'Polish books',
        'coverage': 'Polish and international perspectives: Polish literary criticism, universities, libraries, prize archives, newspapers and magazines, publishers, school and university canons, literary-history resources, reader communities, scholarship, translation criticism and diaspora perspectives. Cover older Polish writing through the present day, including fiction, poetry, drama, essays, reportage, memoir, philosophy and historically important collections where warranted.',
    },
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, config in TARGETS.items():
        sources = json.loads((ROOT / 'research' / slug / 'sources.json').read_text())['sources']
        register = '\n'.join(f"{source['source_id']} — {source['title']}\n{source['canonical_url']}" for source in sources)
        text = f"""Can you use the {len(sources)} existing target-specific sources below to compile and improve an ultimate all-time ranking of the best {config['title']}?\n\nThis is an expansion of an existing ranking, not a fresh replacement. Audit the supplied corpus, retain useful relevant sources, reconcile duplicates or weak leads, and then supplement it with at least 100 additional genuinely consulted, relevant sources with direct URLs. Do not blindly treat every existing source as equally authoritative or as an independent merit vote.\n\nResearch broadly across {config['coverage']}\n\nReturn a copyable UTF-8 .txt report containing:\n1. Scope and methodology.\n2. A revised Top 100 {config['label']} of all time.\n3. Author or traditional attribution, original title where relevant, date, language/region, form, and a concise rationale for every entry.\n4. A complete source register: all {len(sources)} existing sources below plus at least 100 genuinely new sources, every one with a direct URL, source type, language/region where known, and a brief note on use.\n5. A transparent change log explaining additions, removals and substantial moves from the existing ranking.\n\nDo not invent sources, URLs, source positions, publication details, translations or access claims. Preserve disputed, anonymous, collective, composite and historically uncertain works explicitly. Make clear when a source supports historical context, criticism, reception or bibliographic facts rather than the exact final rank.\n\nEXISTING TARGET-SPECIFIC SOURCE REGISTER ({len(sources)} SOURCES)\n\n{register}\n"""
        (OUT / config['filename']).write_text(text)
        print(f"{slug}: {len(sources)} sources -> {config['filename']}")


if __name__ == '__main__':
    main()
