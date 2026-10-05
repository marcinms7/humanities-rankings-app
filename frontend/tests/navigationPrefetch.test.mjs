import assert from 'node:assert/strict'
import test from 'node:test'
import { canPrefetch, internalPrefetchHash, prefetchPlan } from '../src/prefetchPlan.ts'
import { IntentPrefetch } from '../src/intentPrefetch.ts'
import { QueryCache, canonicalQueryKey } from '../src/queryCache.ts'

const flush = () => new Promise((resolve) => setImmediate(resolve))
const deferred = () => {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}
const keys = (hash, signedIn = true) => prefetchPlan(hash, signedIn)?.paths.map(canonicalQueryKey)

test('only same-document application links qualify for intent prefetch', () => {
  const current = 'https://example.test/app/?preview=yes#/catalog'
  assert.equal(internalPrefetchHash('#/books/42', current), '#/books/42')
  for (const href of [
    '#/catalog',
    '#main-content',
    '/accounts/logout/',
    'https://elsewhere.test/#/books/42',
    '/other/#/books/42',
    '?preview=no#/books/42',
    'mailto:reader@example.test',
  ])
    assert.equal(internalPrefetchHash(href, current), null, href)
})

test('hidden, offline, data-saving and slow connections do no speculative work', () => {
  assert.equal(canPrefetch(true, true), true)
  assert.equal(canPrefetch(true, true, { effectiveType: '4g', downlink: 10 }), true)
  for (const connection of [
    { saveData: true },
    { effectiveType: 'slow-2g' },
    { effectiveType: '2g' },
    { effectiveType: '3g' },
    { downlink: 0.9 },
  ])
    assert.equal(canPrefetch(true, true, connection), false)
  assert.equal(canPrefetch(false, true), false)
  assert.equal(canPrefetch(true, false), false)
})

test('prefetch matches filtered screen keys and remains bounded to the requested page', () => {
  assert.deepEqual(keys('#/catalog?q=Homer&country=Greece&page=2&saved_filter=9'), [
    '/api/works/?compact=1&country=Greece&page=2&saved_filter=9&search=Homer',
    '/api/works/facets/?country=Greece&saved_filter=9&search=Homer',
  ])
  assert.deepEqual(keys('#/books/42'), ['/api/works/42/', '/api/works/42/editions/'])
  assert.deepEqual(keys('#/rankings/5?group=collections'), ['/api/rankings/5/?compact=1'])
  assert.deepEqual(keys('#/published-rankings?rpage=3&rfield=philosophy'), [
    '/api/rankings/?field=philosophy&mode=published&ordering=title&page=3&paged=1&search=',
  ])
  assert.deepEqual(keys('#/authors/12?page=2'), ['/api/people/12/', '/api/works/?author=12&page=2'])
  assert.deepEqual(keys('#/library?status=reading&tag=Own&page=4'), [
    '/api/library/?compact=1&ordering=updated&page=4&status=reading&tag=Own',
    '/api/library/facets/?ordering=updated&status=reading&tag=Own',
  ])
  assert.deepEqual(keys('#/atlas?overlay=read&country=Poland'), [
    '/api/catalog-atlas/?century=&country=Poland&field=&overlay=read&page=1&q=',
  ])
  assert.deepEqual(keys('#/atlas?overlay=read', false), [
    '/api/catalog-atlas/?century=&country=&field=&overlay=all&page=1&q=',
  ])
  assert.deepEqual(keys('#/published-comparison?left=1&right=2&view=unique'), [
    '/api/published-comparison/',
    '/api/published-comparison/?left=1&page=1&right=2&search=&sort=left&view=unique',
  ])
})

test('private and administrative routes require the appropriate resolved session', () => {
  for (const route of [
    'library',
    'today',
    'planner',
    'profile',
    'my-lists',
    'saved',
    'classical-education',
    'sources',
    'trails',
    'discover',
  ])
    assert.equal(prefetchPlan(`#/${route}`, false), null, route)
  assert.equal(prefetchPlan('#/catalog-review', true, false), null)
  assert.equal(prefetchPlan('#/operations', true, false), null)
  assert.equal(prefetchPlan('#/operations', true, true).module, 'operations')
  assert.equal(prefetchPlan('#/books/42/delete', true), null)
  assert.equal(prefetchPlan('#/books/not-an-id', true), null)
  assert.deepEqual(prefetchPlan('#/today', true, false, new Date(2026, 8, 30)).paths, [
    '/api/today/?month=2026-09-01',
  ])
})

test('brief pointer movement cancels the delay without fetching a route', async () => {
  const calls = []
  const prefetch = new IntentPrefetch({
    allowed: () => true,
    delay: 0,
    loadModule: async (name) => calls.push(name),
    read: async (path) => calls.push(path),
  })
  prefetch.intend(prefetchPlan('#/books/42', true))
  prefetch.leave('#/books/42')
  await new Promise((resolve) => setTimeout(resolve, 5))
  assert.deepEqual(calls, [])
  prefetch.reset()
})

test('a clicked destination keeps its requests until navigation attaches consumers', async () => {
  const calls = [],
    responses = deferred()
  const prefetch = new IntentPrefetch({
    allowed: () => true,
    loadModule: async () => {},
    read: (path, signal) => {
      calls.push({ path, signal })
      return responses.promise
    },
  })
  prefetch.intend(prefetchPlan('#/books/42', true))
  prefetch.commit('#/books/42')
  await flush()
  prefetch.leave('#/books/42')
  prefetch.navigated('#/books/42')
  assert.equal(calls.length, 2)
  assert.ok(calls.every((call) => !call.signal.aborted))
  prefetch.navigated('#/catalog')
  assert.ok(calls.every((call) => call.signal.aborted))
  responses.resolve(null)
  prefetch.reset()
})

test('rapid changes cap speculative reads at two and drop obsolete queued work', async () => {
  const calls = [],
    responses = [deferred(), deferred(), deferred(), deferred()]
  const prefetch = new IntentPrefetch({
    allowed: () => true,
    loadModule: async () => {},
    read: (path, signal) => {
      const result = responses[calls.length]
      calls.push({ path, signal })
      return result.promise
    },
  })
  for (const id of [1, 2, 3]) {
    prefetch.intend(prefetchPlan(`#/books/${id}`, true))
    prefetch.commit(`#/books/${id}`)
    await flush()
  }
  assert.equal(calls.length, 2)
  assert.ok(calls.every((call) => call.signal.aborted))
  responses[0].resolve(null)
  responses[1].resolve(null)
  await flush()
  assert.equal(calls.length, 4)
  assert.ok(calls.slice(2).every((call) => call.path.startsWith('/api/works/3/')))
  responses[2].resolve(null)
  responses[3].resolve(null)
  prefetch.reset()
})

test('aborting speculation leaves an actual screen observer and warm result intact', async () => {
  const cache = new QueryCache(),
    response = deferred()
  let transports = 0
  const loader = () => {
    transports += 1
    return response.promise
  }
  const read = (path, signal) => cache.read(path, ['catalog'], loader, 1000, signal)
  const prefetch = new IntentPrefetch({ allowed: () => true, loadModule: async () => {}, read })
  prefetch.intend({ key: '#/books/42', module: 'catalog', paths: ['/api/works/42/'] })
  prefetch.commit('#/books/42')
  await flush()
  const screen = read('/api/works/42/')
  prefetch.reset()
  response.resolve({ id: 42 })
  assert.deepEqual(await screen, { id: 42 })
  assert.equal(transports, 1)
  assert.deepEqual(cache.peek('/api/works/42/'), { data: { id: 42 } })
})

test('account changes discard speculation and cannot restore a previous private response', async () => {
  const cache = new QueryCache(),
    response = deferred()
  cache.setAccount('reader-one')
  const generation = cache.generation
  const prefetch = new IntentPrefetch({
    allowed: () => generation === cache.generation,
    loadModule: async () => {},
    read: (path, signal) => cache.read(path, ['library'], () => response.promise, 1000, signal),
  })
  const unsubscribe = cache.subscribe((event) => {
    if (event.accountChanged) prefetch.reset()
  })
  prefetch.intend({ key: '#/library', module: 'library', paths: ['/api/library/'] })
  prefetch.commit('#/library')
  await flush()
  cache.setAccount('reader-two')
  response.resolve({ private: 'reader-one' })
  await flush()
  assert.equal(cache.peek('/api/library/'), null)
  prefetch.intend(prefetchPlan('#/library', true))
  prefetch.commit('#/library')
  await flush()
  assert.equal(cache.peek('/api/library/'), null)
  unsubscribe()
  prefetch.reset()
})
