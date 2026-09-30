import test from 'node:test'
import assert from 'node:assert/strict'
import { clearDrafts, compatibleDraft, draftLease, draftsEnabled, readDrafts, registerDraftFlush, removeDraft, setDraftAccount, setDraftsEnabled, writeDraft } from '../src/draftStore.ts'
class MemoryStorage {
  items = new Map()
  get length() { return this.items.size }
  key(index) { return [...this.items.keys()][index] ?? null }
  getItem(key) { return this.items.get(key) ?? null }
  setItem(key, value) { this.items.set(key, value) }
  removeItem(key) { this.items.delete(key) }
}
const save = (storage, user, slot, value = 'Unsaved note', scope = 'notes:1', lease = draftLease(user)) => writeDraft(storage, user, scope, slot, value, 'saved-version-1', 'Book note', lease)
test('draft copies round-trip without changing saved records and retain base revision', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const row = save(storage, 1, 'editor')
  assert.deepEqual(readDrafts(storage, 1, 'notes:1'), [row])
  assert.equal(row.baseVersion, 'saved-version-1')
  assert.equal(readDrafts(storage, 1, 'notes:2').length, 0)
})
test('recovery reads and clear operations are scoped to the signed-in account', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true); save(storage, 1, 'editor')
  setDraftAccount(2); save(storage, 2, 'editor', 'Second reader')
  assert.equal(readDrafts(storage, 2)[0].value, 'Second reader')
  clearDrafts(storage, 2)
  assert.equal(readDrafts(storage, 1).length, 1)
  assert.equal(readDrafts(storage, 2).length, 0)
})
test('account switch flushes old account first, then revokes delayed callbacks', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const lease = draftLease(1)
  const unregister = registerDraftFlush(() => save(storage, 1, 'flush', 'last keystrokes', 'notes:1', lease))
  setDraftAccount(2); unregister()
  assert.equal(readDrafts(storage, 1)[0].value, 'last keystrokes')
  assert.equal(save(storage, 1, 'delayed', 'wrong session', 'notes:1', lease), null)
  assert.equal(readDrafts(storage, 2).length, 0)
})
test('sign-out preserves recovery copies but old leases stay invalid after re-login', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const old = draftLease(1); save(storage, 1, 'original')
  setDraftAccount(null); setDraftAccount(1)
  assert.equal(old(), false)
  assert.equal(save(storage, 1, 'stale', 'late', 'notes:1', old), null)
  assert.equal(readDrafts(storage, 1).length, 1)
})
test('forced same-account session refresh also revokes old write callbacks', () => {
  setDraftAccount(1, true); const old = draftLease(1)
  setDraftAccount(1, true)
  assert.equal(old(), false)
  assert.equal(draftLease(1)(), true)
})
test('independent tabs retain separate recovery copies of the same editor', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const a = save(storage, 1, 'tab-a', 'A'), b = save(storage, 1, 'tab-b', 'B')
  assert.equal(readDrafts(storage, 1).length, 2)
  removeDraft(storage, a)
  assert.deepEqual(readDrafts(storage, 1), [b])
})
test('saving/discarding a reviewed copy cannot clear a newer copy with the same key', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const old = save(storage, 1, 'editor', 'Old')
  save(storage, 1, 'editor', 'New')
  removeDraft(storage, old)
  assert.equal(readDrafts(storage, 1)[0].value, 'New')
})
test('disable clears only this account and prevents future writes until enabled', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true); save(storage, 1, 'one')
  setDraftsEnabled(storage, 1, false)
  assert.equal(draftsEnabled(storage, 1), false)
  assert.equal(save(storage, 1, 'two'), null)
  assert.equal(readDrafts(storage, 1).length, 0)
  setDraftsEnabled(storage, 1, true)
  assert.ok(save(storage, 1, 'three'))
})
test('oversize and total budget failures preserve existing copies', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true); save(storage, 1, 'first')
  assert.throws(() => save(storage, 1, 'huge', 'x'.repeat(200_001)), /too large/)
  for (let i = 0; i < 4; i++) save(storage, 1, `large-${i}`, 'x'.repeat(180_000))
  assert.throws(() => save(storage, 1, 'over-budget', 'x'.repeat(180_000)), /storage is full/)
  assert.equal(readDrafts(storage, 1).length, 5)
})
test('copy count cap refuses new copies without eviction', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  for (let i = 0; i < 40; i++) save(storage, 1, `editor-${i}`)
  assert.throws(() => save(storage, 1, 'extra'), /storage is full/)
  assert.equal(readDrafts(storage, 1).length, 40)
})
test('malformed stored entries and mismatched account envelopes never restore', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const row = save(storage, 1, 'valid')
  storage.setItem(row.key, '{broken')
  assert.deepEqual(readDrafts(storage, 1), [])
  storage.setItem(row.key, JSON.stringify({ ...row, account: 2 }))
  assert.deepEqual(readDrafts(storage, 1), [])
  assert.equal(compatibleDraft({ essay: 'invalid' }, { essay: { title: '', draft: '' } }), false)
  assert.equal(compatibleDraft({ title: '', draft: 'Retained' }, { title: '', draft: '' }), true)
})
test('browser quota failures are surfaced to the UI layer', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  storage.setItem = () => { throw new DOMException('Quota exceeded', 'QuotaExceededError') }
  assert.throws(() => save(storage, 1, 'quota'), { name: 'QuotaExceededError' })
})
test('session generation subscription renews same-account editor leases', async () => {
  const { subscribeDraftAccount, draftGeneration } = await import('../src/draftStore.ts')
  setDraftAccount(1, true)
  let epoch = draftGeneration(), lease = draftLease(1), changes = 0
  const previous = lease
  const unsubscribe = subscribeDraftAccount(() => { epoch = draftGeneration(); lease = draftLease(1); changes += 1 })
  const before = epoch
  setDraftAccount(1, true)
  assert.equal(changes, 1)
  assert.equal(epoch, before + 1)
  assert.equal(previous(), false)
  assert.equal(lease(), true)
  unsubscribe()
})
test('a new editor preserves its own text while an earlier recovery copy awaits review', () => {
  const storage = new MemoryStorage(); setDraftAccount(1, true)
  const earlier = save(storage, 1, 'old-session', 'Earlier unfinished writing')
  const candidate = readDrafts(storage, 1, 'notes:1')[0]
  const current = save(storage, 1, 'new-session', 'New writing without restoring earlier text')
  assert.equal(candidate.key, earlier.key)
  assert.deepEqual(new Set(readDrafts(storage, 1).map((row) => row.value)), new Set([earlier.value, current.value]))
})
