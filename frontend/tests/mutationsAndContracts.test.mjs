import assert from 'node:assert/strict'
import test from 'node:test'
import { mutationRequest, finishMutation } from '../src/mutationRequests.ts'
import { queryCache } from '../src/queryCache.ts'
import { responseContractIssue } from '../src/responseValidation.ts'
import { responseSchemas } from '../src/generated/responseSchemas.ts'

function example(shape) {
  if (shape.nullable) return null
  if (shape.kind === 'object') return Object.fromEntries(shape.required.map(key => [key, example(shape.fields[key])]))
  if (shape.kind === 'array') return []
  if (shape.kind === 'record') return {}
  if (shape.kind === 'enum') return shape.values[0]
  return shape.kind === 'string' ? 'sample' : shape.kind === 'number' ? 1 : shape.kind === 'boolean' ? false : null
}

test('a write with an unknown outcome keeps its key for explicit retry', () => {
  const first = mutationRequest('/api/library/1/', 'PATCH', { notes: 'private text' })
  finishMutation(first, 503)
  assert.equal(mutationRequest('/api/library/1/', 'PATCH', { notes: 'private text' }).key, first.key)
  finishMutation(first, 200)
  assert.notEqual(mutationRequest('/api/library/1/', 'PATCH', { notes: 'private text' }).key, first.key)
})

test('account changes discard retry keys and corrected requests have distinct keys', () => {
  const first = mutationRequest('/api/library/1/', 'PATCH', { notes: 'one' })
  const edited = mutationRequest('/api/library/1/', 'PATCH', { notes: 'two' })
  assert.notEqual(edited.key, first.key)
  queryCache.setAccount('another-account', true)
  assert.notEqual(mutationRequest('/api/library/1/', 'PATCH', { notes: 'one' }).key, first.key)
})

test('GET, session and file requests do not create replay keys', () => {
  assert.equal(mutationRequest('/api/library/', 'GET'), null)
  assert.equal(mutationRequest('/api/session/', 'POST', { action: 'login' }), null)
  assert.equal(mutationRequest('/api/editions/1/', 'PATCH', new FormData()), null)
})

test('a late response cannot clear the newer account retry key', () => {
  const first = mutationRequest('/api/library/1/', 'PATCH', { notes: 'same text' })
  queryCache.setAccount('next-account', true)
  const next = mutationRequest('/api/library/1/', 'PATCH', { notes: 'same text' })
  finishMutation(first, 200)
  assert.equal(mutationRequest('/api/library/1/', 'PATCH', { notes: 'same text' }).key, next.key)
})

test('complex responses accept complete contracts and reject missing fields', () => {
  const valid = example(responseSchemas.ApiRecommendationBundle)
  assert.equal(responseContractIssue('/api/recommendations/', 'GET', valid), null)
  delete valid.preferences.short_pages
  assert.match(responseContractIssue('/api/recommendations/', 'GET', valid), /preferences.short_pages/)
})

test('invalid study paths and wrong array types are rejected before merging', () => {
  const valid = example(responseSchemas.ApiStudyDelta)
  valid.changes = [{ path: ['modules', 'a', 'notes'], value: 'private note' }]
  assert.equal(responseContractIssue('/api/classical-education/?part=delta', 'PATCH', valid), null)
  valid.changes[0].path = 'not an array'
  const error = responseContractIssue('/api/classical-education/?part=delta', 'PATCH', valid)
  assert.match(error, /changes\[0\].path/)
  assert.ok(!error.includes('private note'))
})

test('preview validation does not mistake a successful application for a preview', () => {
  assert.equal(responseContractIssue('/api/reading-allocation/', 'POST', { applied: true, plan: {} }), null)
  assert.match(responseContractIssue('/api/reading-allocation/', 'POST', { applied: false }), /preview_token/)
})
