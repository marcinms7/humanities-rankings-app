import assert from 'node:assert/strict'
import test from 'node:test'
import { browseTarget } from '../src/browseState.ts'
import {
  catalogBrowseDefaults,
  catalogRequestParams,
  catalogSelectionLimit,
  catalogSelectionPatch,
  matchingCatalogOptions,
  toggleCatalogValue,
} from '../src/catalogFilterState.ts'

test('comma labels round trip through URL state without splitting values', () => {
  const choice = { include: ['France, Russia', 'Côte d’Ivoire'], exclude: ['United Kingdom'] }
  const hash = browseTarget('#/catalog?saved_filter=7&page=3&unrelated=retained', catalogSelectionPatch('country', choice), catalogBrowseDefaults)
  const params = new URLSearchParams(hash.split('?')[1])
  const request = catalogRequestParams({ ...catalogBrowseDefaults, ...Object.fromEntries(params) })
  assert.deepEqual(JSON.parse(request.get('country_any')), choice.include)
  assert.deepEqual(JSON.parse(request.get('country_not')), choice.exclude)
  assert.equal(params.get('saved_filter'), '7')
  assert.equal(params.get('unrelated'), 'retained')
  assert.equal(params.has('page'), false)
})

test('saved facet inheritance differs from deliberately allowing any value', () => {
  const inherited = catalogRequestParams({ ...catalogBrowseDefaults, saved_filter: '7' })
  assert.equal(inherited.has('country'), false)
  assert.equal(inherited.has('country_any'), false)
  const clear = catalogRequestParams({ ...catalogBrowseDefaults, saved_filter: '7', country_any: '[]' })
  assert.equal(clear.get('country_any'), '[]')
  assert.equal(clear.get('saved_filter'), '7')
  const legacyClear = catalogRequestParams({ ...catalogBrowseDefaults, country: '', saved_filter: '7' })
  assert.equal(legacyClear.get('country'), '')
})

test('legacy single links keep working and multi selections supersede them', () => {
  assert.equal(catalogRequestParams({ field: 'philosophy', q: 'ethics' }).get('field'), 'philosophy')
  const params = catalogRequestParams({ field: 'philosophy', field_any: '["literature","nonfiction"]' })
  assert.equal(params.has('field'), false)
  assert.equal(params.get('field_any'), '["literature","nonfiction"]')
})

test('include and exclude toggles are mutually exclusive without losing other selections', () => {
  const first = { include: ['France', 'Russia'], exclude: ['England'] }
  const excluded = toggleCatalogValue(first, 'exclude', 'France')
  assert.deepEqual(excluded, { include: ['Russia'], exclude: ['England', 'France'] })
  assert.deepEqual(toggleCatalogValue(excluded, 'exclude', 'France'), { include: ['Russia'], exclude: ['England'] })
  assert.deepEqual(first, { include: ['France', 'Russia'], exclude: ['England'] })
})

test('selection limits still allow deselecting and do not silently remove the opposite filter', () => {
  const selection = { include: Array.from({ length: catalogSelectionLimit }, (_, i) => String(i)), exclude: ['extra'] }
  assert.deepEqual(toggleCatalogValue(selection, 'include', 'extra'), selection)
  assert.equal(toggleCatalogValue(selection, 'include', '1').include.length, catalogSelectionLimit - 1)
})

test('search reaches selected and unselected values beyond the sixty-option display cap', () => {
  const values = Array.from({ length: 120 }, (_, i) => `Country ${i}`)
  const options = values.map(value => ({ value }))
  const selection = { include: values.slice(0, 50), exclude: values.slice(50, 100) }
  assert.deepEqual(matchingCatalogOptions(options, selection, 'Country 98'), [{ value: 'Country 98' }])
  assert.deepEqual(matchingCatalogOptions(options, selection, 'Country 111'), [{ value: 'Country 111' }])
  assert.equal(matchingCatalogOptions([{ value: 'short_story' }], selection, 'Short story').length, 1)
})
