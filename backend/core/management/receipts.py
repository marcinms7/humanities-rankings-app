"""Keep the current import mapping readable without discarding older receipts."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def save_import_receipt(input_path, payload):
    path = Path(input_path)
    receipt = path.with_name(path.stem + '-import-receipt.json')
    if receipt.exists():
        previous = receipt.read_bytes()
        if json.loads(previous).get('input_sha256') == payload['input_sha256']:
            return receipt
        # The standard filename is used by downstream catalog-ID mapping tools.
        # Preserve its old bytes before atomically replacing it with this input's
        # receipt, instead of leaving downstream tools with stale mappings.
        digest = hashlib.sha256(previous).hexdigest()
        historical = receipt.with_name(f'{receipt.stem}-{digest}.json')
        try:
            with historical.open('xb') as stream:
                stream.write(previous)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if historical.read_bytes() != previous:
                raise ValueError(f'Historical receipt content conflict: {historical}')
    data = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    descriptor, temporary_name = tempfile.mkstemp(prefix=f'.{receipt.name}.', dir=receipt.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(receipt)
    finally:
        temporary.unlink(missing_ok=True)
    return receipt
