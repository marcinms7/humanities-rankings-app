#!/usr/bin/env python3
"""Mark the independently checked Philosophy of Language intake sources eligible.

The supplied report described its URLs as prospective cross-checks.  This
script records only the subset actually accessed during the 13 September 2026
intake; all other URLs remain visible, uneligible leads.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = 'books-philosophy-of-language'
VERIFIED_NUMBERS = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 13, 14, 15, 16, 17, 20, 22, 26, 27,
    30, 31, 34, 36, 37, 38, 39, 40, 41, 43, 44, 45, 46, 48, 49, 51, 52,
    53, 54, 57, 58, 60, 61, 63, 64, 65, 73, 74, 90, 91, 93, 94, 95, 96,
}


def main():
    path = ROOT / 'research' / TARGET / 'sources.json'
    ledger = json.loads(path.read_text())
    verified = 0
    for source in ledger['sources']:
        number = int(source['source_id'].rsplit('-', 1)[1])
        if number not in VERIFIED_NUMBERS:
            continue
        source['count_eligible'] = True
        source['accessed_at'] = '2026-09-13'
        source['relevance_by_target'][TARGET] = (
            'Independently accessed during intake and found relevant to the '
            'Philosophy of Language target; retained as source-level, not '
            'candidate-specific, evidence.'
        )
        source['evidence_notes'] = (
            'Independently accessed during the 13 September 2026 intake. '
            'The retrieved bibliography, reference work, course list, '
            'publisher record, poll, or community discussion is relevant to '
            'the target. It supports corpus-level inclusion only; detailed '
            'candidate mappings remain pending.'
        )
        source['disagreement_or_limitations'] = (
            'Verified at source level during intake; no candidate-specific '
            'evidence map or separate reading-value order was supplied.'
        )
        verified += 1
    if verified != len(VERIFIED_NUMBERS):
        raise ValueError(f'Expected {len(VERIFIED_NUMBERS)} verified sources, found {verified}')
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n')
    print(f'Qualified {verified} of {len(ledger["sources"])} source records; remaining URLs stay uneligible.')


if __name__ == '__main__':
    main()
