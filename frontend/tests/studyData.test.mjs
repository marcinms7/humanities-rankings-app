import assert from 'node:assert/strict'
import test from 'node:test'
import { applyStudyChanges, mergeStudySummary } from '../src/studyData.ts'

test('summary refresh preserves loaded note text while updating completion', () => {
  const state = { modules: { iliad: { notes: 'retained', revision: { light: false } } } }
  const result = mergeStudySummary(state, { modules: { iliad: { revision: { light: true } } } })
  assert.equal(result.modules.iliad.notes, 'retained')
  assert.equal(result.modules.iliad.revision.light, true)
  assert.equal(state.modules.iliad.revision.light, false)
})
test('first-session deltas and paged sessions preserve stable array positions', () => {
  const initial = applyStudyChanges({}, [{ path: ['learning'], value: { sessions: { 0: { id: 'one' } } } }])
  assert.ok(Array.isArray(initial.learning.sessions))
  const later = applyStudyChanges(initial, [{ path: ['learning', 'sessions', '29'], value: { id: 'thirty' } }])
  assert.equal(later.learning.sessions[0].id, 'one')
  assert.equal(later.learning.sessions[29].id, 'thirty')
  assert.deepEqual(later.learning.sessions.filter(Boolean).map(row => row.id), ['one', 'thirty'])
})
test('loading another family preserves notes and rejects unsafe record paths', () => {
  const state = { modules: { iliad: { notes: 'saved' } } }
  const result = applyStudyChanges(state, [{ path: ['companion', 'commonplaces', 'one'], value: { reflection: 'new' } }])
  assert.equal(result.modules.iliad.notes, 'saved')
  assert.throws(() => applyStudyChanges({}, [{ path: ['__proto__', 'polluted'], value: true }]), /invalid record path/)
})
