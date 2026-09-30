// Saved regressions. Run only when the owner authorizes test execution.
import assert from 'node:assert/strict'
import test from 'node:test'
import { QueryCache, canonicalQueryKey } from '../src/queryCache.ts'
import { cacheLifetime, mutationTags, queryTags } from '../src/queryPolicies.ts'

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('query ordering is canonical without dropping duplicate parameters', () => {
  assert.equal(canonicalQueryKey('/api/library/?b=2&a=1&a=3'), '/api/library/?a=1&a=3&b=2')
})

test('concurrent observers share one request and departing observers do not cancel others', async () => {
  const cache = new QueryCache(), response = deferred(), first = new AbortController()
  let calls = 0
  const loader = () => { calls += 1; return response.promise }
  const one = cache.read('books', ['library'], loader, 1000, first.signal)
  const two = cache.read('books', ['library'], loader, 1000)
  const rejected = assert.rejects(one, { name: 'AbortError' })
  first.abort()
  await Promise.resolve()
  assert.equal(calls, 1)
  response.resolve([{ id: 1 }])
  await rejected
  assert.deepEqual(await two, [{ id: 1 }])
})

test('changing accounts clears fulfilled data and rejects late previous-account results', async () => {
  const cache = new QueryCache(), response = deferred()
  cache.setAccount('reader-one')
  await cache.read('profile', ['profile'], async () => ({ note: 'private' }), 1000)
  const old = cache.read('history', ['library'], () => response.promise, 1000)
  const rejected = assert.rejects(old, { name: 'AbortError' })
  await Promise.resolve()
  cache.setAccount('reader-two')
  assert.equal(cache.peek('profile'), null)
  response.resolve({ note: 'earlier reader' })
  await rejected
  assert.equal(cache.peek('history'), null)
})

test('a warm-cache read cannot complete after its account is replaced', async () => {
  const cache = new QueryCache()
  await cache.read('library', ['library'], async () => ['private'], 1000)
  const old = cache.read('library', ['library'], async () => ['unexpected'], 1000)
  const rejected = assert.rejects(old, { name: 'AbortError' })
  cache.setAccount('another-reader')
  await rejected
})

test('invalidating one resource preserves unrelated cached values', async () => {
  const cache = new QueryCache()
  await cache.read('library', ['library'], async () => [1], 1000)
  await cache.read('facets', ['catalog'], async () => ['Japan'], 1000)
  cache.invalidate(['library'])
  assert.equal(cache.peek('library'), null)
  assert.deepEqual(cache.peek('facets'), { data: ['Japan'] })
})

test('a pre-mutation response cannot overwrite the replacement request', async () => {
  const cache = new QueryCache(), response = deferred()
  const old = cache.read('library', ['library'], () => response.promise, 1000)
  const rejected = assert.rejects(old, { name: 'AbortError' })
  await Promise.resolve()
  cache.invalidate(['library'])
  assert.deepEqual(await cache.read('library', ['library'], async () => ['new'], 1000), ['new'])
  response.resolve(['old'])
  await rejected
  assert.deepEqual(cache.peek('library'), { data: ['new'] })
})

test('expiration and entry limits release cached records', async () => {
  let now = 0
  const cache = new QueryCache({ maxEntries: 2, now: () => now })
  await cache.read('one', ['catalog'], async () => 1, 1000)
  now = 10
  await cache.read('two', ['catalog'], async () => 2, 1000)
  now = 20
  await cache.read('three', ['catalog'], async () => 3, 1000)
  assert.equal(cache.peek('one'), null)
  assert.deepEqual(cache.peek('two'), { data: 2 })
  now = 2000
  cache.expire()
  assert.equal(cache.peek('three'), null)
})

test('oversized responses are delivered but not retained', async () => {
  const cache = new QueryCache({ maxBytes: 20 })
  assert.equal(await cache.read('large', ['library'], async () => 'a'.repeat(100), 1000), 'a'.repeat(100))
  assert.equal(cache.peek('large'), null)
})

test('failed reads are retryable and never retained as successful cache entries', async () => {
  const cache = new QueryCache()
  await assert.rejects(cache.read('library', ['library'], async () => { throw new Error('failed') }, 1000), /failed/)
  assert.equal(cache.peek('library'), null)
  assert.equal(await cache.read('library', ['library'], async () => 4, 1000), 4)
})

test('preview commands invalidate nothing; confirmations invalidate their dependencies', () => {
  for (const path of ['/api/plan/suggest/', '/api/plan/carryover/', '/api/reading-allocation/', '/api/read-next/plan/', '/api/library/2/edition-change/']) {
    assert.equal(mutationTags(path, { apply: false }).size, 0)
    assert.ok(mutationTags(path, { apply: true }).size > 0)
  }
  assert.equal(mutationTags('/api/rankings/3/preview/', { weights: {} }).size, 0)
  assert.equal(mutationTags('/api/classical-education/?part=delta', { companion: { action: 'plan-preview' } }).size, 0)
})

test('library changes refresh private contexts without reloading public catalog facets', () => {
  const changed = mutationTags('/api/library/4/', { rating: 8 })
  assert.ok([...queryTags('/api/ranking-browse/3/')].some(tag => changed.has(tag)))
  assert.ok([...queryTags('/api/today/')].some(tag => changed.has(tag)))
  assert.ok(![...queryTags('/api/works/facets/')].some(tag => changed.has(tag)))
})

test('study note changes preserve static curriculum cache and saved filters invalidate their users', () => {
  const changed = mutationTags('/api/classical-education/?part=delta', { module: 'one', notes: 'private' })
  assert.ok([...queryTags('/api/classical-education/?part=state')].some(tag => changed.has(tag)))
  assert.ok(![...queryTags('/api/classical-education/?part=content')].some(tag => changed.has(tag)))
  assert.ok(queryTags('/api/works/?saved_filter=1').has('saved-filters'))
})

test('catalog corrections refresh ranking books while preserving metadata-only overview cards', () => {
  const changed = mutationTags('/api/works/4/', { title: 'Corrected title' })
  for (const path of ['/api/rankings/3/entries/', '/api/rankings/recommendations/', '/api/ranking-browse/3/']) {
    assert.ok([...queryTags(path)].some(tag => changed.has(tag)), path)
  }
  assert.ok(![...queryTags('/api/rankings/explore/')].some(tag => changed.has(tag)))
  assert.ok([...queryTags('/api/rankings/explore/')].some(tag => mutationTags('/api/rankings/3/preference/').has(tag)))
})

test('confirmed companion allocations refresh plan and library but preserve static study content', () => {
  const changed = mutationTags('/api/classical-education/?part=delta', { companion: { action: 'plan-add' } })
  for (const path of ['/api/plan/', '/api/library/overview/', '/api/classical-education/?part=state']) {
    assert.ok([...queryTags(path)].some(tag => changed.has(tag)), path)
  }
  assert.ok(![...queryTags('/api/classical-education/?part=content')].some(tag => changed.has(tag)))
})

test('session and exports are uncached; appearance-only profile updates preserve reading estimates', () => {
  assert.equal(cacheLifetime('/api/session/'), 0)
  assert.equal(cacheLifetime('/api/export/'), 0)
  assert.equal(cacheLifetime('/api/classical-education/?export=txt'), 0)
  assert.ok(!mutationTags('/api/profile/', { theme: 'dark' }).has('reading-estimates'))
  assert.ok(mutationTags('/api/profile/', { words_per_minute: 300 }).has('reading-estimates'))
})

test('calendar previews preserve views; confirmed exceptions refresh affected planning views', () => {
  assert.equal(mutationTags('/api/reading-calendar/', { apply: false }).size, 0)
  const changed = mutationTags('/api/reading-calendar/', { apply: true })
  for (const path of ['/api/reading-calendar/', '/api/plan/capacity/', '/api/today/', '/api/classical-education/?part=summary'])
    assert.ok([...queryTags(path)].some(tag => changed.has(tag)), path)
  for (const path of ['/api/works/facets/', '/api/classical-education/?part=content'])
    assert.ok(![...queryTags(path)].some(tag => changed.has(tag)), path)
})
