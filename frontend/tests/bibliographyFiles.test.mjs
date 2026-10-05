import assert from 'node:assert/strict'
import test from 'node:test'
import { bibliographyFile } from '../src/bibliographyFiles.ts'
import { mutationTags } from '../src/queryPolicies.ts'

test('bibliography downloads preserve Unicode, RIS line endings and distinct format contents', () => {
  const result = { plain_text: 'Éthique. 漢字.\n', ris: 'TY  - BOOK\r\nTI  - Éthique\r\nER  -\r\n', bibtex: '@book{marginalia7,\n title = {{Éthique}}\n}\n' }
  for (const [format, extension, mime] of [
    ['plain_text', 'txt', 'text/plain'], ['ris', 'ris', 'application/x-research-info-systems'], ['bibtex', 'bib', 'application/x-bibtex'],
  ]) {
    const file = bibliographyFile(result, format)
    assert.equal(file.name, `marginalia-bibliography.${extension}`)
    assert.equal(file.mime, `${mime};charset=utf-8`)
    assert.equal(file.text, result[format])
  }
})

test('read-only bibliography POST does not invalidate private reading data', () => {
  assert.equal(mutationTags('/api/bibliography/', { work_ids: [7] }).size, 0)
})
