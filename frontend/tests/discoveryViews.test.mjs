import assert from 'node:assert/strict'
import test from 'node:test'
import { QueryCache } from '../src/queryCache.ts'
import { queryTags, mutationTags } from '../src/queryPolicies.ts'
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

test('reading changes invalidate the atlas overlay but preserve publisher comparisons', async () => {
  const cache = new QueryCache()
  const atlas = '/api/catalog-atlas/?overlay=read'
  const comparison = '/api/published-comparison/?left=1&right=2'
  await cache.read(atlas, queryTags(atlas), async () => ({ read: 1 }), 1000)
  await cache.read(comparison, queryTags(comparison), async () => ({ shared: 2 }), 1000)
  cache.invalidate(mutationTags('/api/library/3/', { status: 'finished' }))
  assert.equal(cache.peek(atlas), null)
  assert.deepEqual(cache.peek(comparison), { data: { shared: 2 } })
  cache.invalidate(mutationTags('/api/rankings/1/', {}))
  assert.equal(cache.peek(comparison), null)
})

test('catalog edits invalidate atlas geography and publisher book cards', async () => {
  const cache = new QueryCache()
  const paths = ['/api/catalog-atlas/', '/api/published-comparison/?left=1&right=2']
  for (const path of paths) await cache.read(path, queryTags(path), async () => [], 1000)
  cache.invalidate(mutationTags('/api/works/9/', { countries: ['England'] }))
  for (const path of paths) assert.equal(cache.peek(path), null)
})

test('atlas response validation rejects malformed counts and dates before rendering', () => {
  const value = example(responseSchemas.ApiCatalogAtlas)
  assert.equal(responseContractIssue('/api/catalog-atlas/?overlay=read', 'GET', value), null)
  value.summary.read = 'private malformed count'
  assert.match(responseContractIssue('/api/catalog-atlas/', 'GET', value), /summary.read$/)
  value.summary.read = 0
  value.results = [example(responseSchemas.ApiCatalogAtlas.fields.results.item)]
  value.results[0].date_status = 'inferred'
  assert.match(responseContractIssue('/api/catalog-atlas/', 'GET', value), /date_status$/)
})

test('publisher response accepts absent ranks but rejects invented nonnumeric positions', () => {
  const value = example(responseSchemas.ApiPublishedComparison)
  value.results = [example(responseSchemas.ApiPublishedComparison.fields.results.item)]
  assert.equal(value.results[0].left_rank, null)
  assert.equal(value.results[0].delta, null)
  assert.equal(responseContractIssue('/api/published-comparison/', 'GET', value), null)
  value.results[0].right_rank = 'unrecorded'
  assert.match(responseContractIssue('/api/published-comparison/', 'GET', value), /right_rank$/)
})
