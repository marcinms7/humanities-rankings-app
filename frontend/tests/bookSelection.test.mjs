import assert from 'node:assert/strict'
import test from 'node:test'
import { addSelectedBooks, parsePrivateLabels, selectionLimit } from '../src/bookSelection.ts'
import { mutationTags } from '../src/queryPolicies.ts'

test('page selection preserves click order and deduplicates country appearances', () => {
  const first = [{ id: 7, title: 'Seven' }, { id: 2, title: 'Two' }]
  assert.deepEqual(addSelectedBooks(first, [{ id: 2, title: 'Two' }, { id: 1, title: 'One' }]), [...first, { id: 1, title: 'One' }])
  assert.equal(first.length, 2)
})

test('selection stays within the server limit across repeated page additions', () => {
  const first = Array.from({ length: selectionLimit - 1 }, (_, id) => ({ id: id + 1, title: String(id) }))
  const merged = addSelectedBooks(first, [{ id: 999, title: 'Last' }, { id: 1000, title: 'Too many' }])
  assert.equal(merged.length, selectionLimit)
  assert.equal(merged.at(-1).id, 999)
})

test('private label input ignores empty values and exact duplicates', () => {
  assert.deepEqual(parsePrivateLabels(' History, , Book club,History, '), ['History', 'Book club'])
})

test('bulk private list changes invalidate list readers; library changes refresh private overlays', () => {
  assert.deepEqual([...mutationTags('/api/library/bulk/', { action: 'personal_list' })], ['rankings'])
  assert.ok(mutationTags('/api/library/bulk/', { action: 'read_next' }).has('library'))
})
