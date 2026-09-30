import assert from 'node:assert/strict'
import test from 'node:test'
import { browseTarget, positivePage } from '../src/browseState.ts'

test('changing a ranking page keeps bookmarked context and unrelated filters', () => {
  assert.equal(browseTarget('#/rankings/8?view=bookmarked&group=collections&rgenre=Poetry', { rpage: 2 }, { rpage: '1' }), '#/rankings/8?view=bookmarked&group=collections&rgenre=Poetry&rpage=2')
})
test('empty explicit override is retained when the default means inherit', () => {
  assert.equal(browseTarget('#/catalog?saved_filter=7', { genre: '' }, { genre: 'all' }), '#/catalog?saved_filter=7&genre=')
})
test('default page and removed parameters disappear without dropping others', () => {
  assert.equal(browseTarget('#/catalog?q=Plato&page=3&field=philosophy', { page: 1, q: null }, { page: '1', q: '' }), '#/catalog?field=philosophy')
})
test('search text is encoded as query text, never as navigation syntax', () => {
  const target = browseTarget('#/catalog', { q: 'Łódź & #/profile?' }, { q: '' })
  const url = new URL(target.slice(1), 'https://marginalia.local')
  assert.equal(url.pathname, '/catalog')
  assert.equal(url.searchParams.get('q'), 'Łódź & #/profile?')
  assert.equal(url.hash, '')
})
test('malformed page values cannot create negative or unbounded offsets', () => {
  for (const value of ['-4', 'NaN', '1.4', 'abc', '']) assert.equal(positivePage(value), 1)
  assert.equal(positivePage('99999999999999'), 1000000)
  assert.equal(positivePage('12'), 12)
})
