import assert from 'node:assert/strict'
import test from 'node:test'
import { responseContractIssue } from '../src/responseValidation.ts'
import { responseSchemas } from '../src/generated/responseSchemas.ts'
import { mutationRequest } from '../src/mutationRequests.ts'
import { mutationTags, queryTags } from '../src/queryPolicies.ts'
import { canonicalQueryKey } from '../src/queryCache.ts'
import { prefetchPlan } from '../src/prefetchPlan.ts'
import { catalogBrowseDefaults, catalogRequestParams } from '../src/catalogFilterState.ts'

function example(shape) {
  if (shape.nullable) return null
  if (shape.kind === 'object')
    return Object.fromEntries(shape.required.map((key) => [key, example(shape.fields[key])]))
  if (shape.kind === 'array') return []
  if (shape.kind === 'enum') return shape.values[0]
  return shape.kind === 'string'
    ? 'sample'
    : shape.kind === 'number'
      ? 1
      : shape.kind === 'boolean'
        ? false
        : null
}

test('search groups reject malformed destinations before display', () => {
  const response = {
    query: 'Plato',
    groups: [
      {
        key: 'books',
        label: 'Books',
        items: [{ id: '1', title: 'Republic', subtitle: 'Plato', href: '#/books/1' }],
        has_more: false,
        more_href: null,
      },
    ],
  }
  assert.equal(responseContractIssue('/api/app-search/?q=Plato', 'GET', response), null)
  response.groups[0].items[0].href = 42
  assert.match(responseContractIssue('/api/app-search/?q=Plato', 'GET', response), /items\[0\].href/)
})

test('facet counts and bibliography output must match generated contracts', () => {
  const facets = example(responseSchemas.ApiCatalogFacets)
  assert.equal(responseContractIssue('/api/works/facets/', 'GET', facets), null)
  facets.facets.country.options = [{ value: 'France', include_count: 'many', exclude_count: 0 }]
  assert.match(responseContractIssue('/api/works/facets/', 'GET', facets), /include_count/)
  const exportData = example(responseSchemas.ApiBibliographyExport)
  assert.equal(responseContractIssue('/api/bibliography/', 'POST', exportData), null)
  delete exportData.ris
  assert.match(responseContractIssue('/api/bibliography/', 'POST', exportData), /ris/)
})

test('bibliography reads neither create mutation retry keys nor invalidate existing views', () => {
  assert.equal(mutationRequest('/api/bibliography/', 'POST', { work_ids: [7] }), null)
  assert.equal(mutationTags('/api/bibliography/').size, 0)
  for (const tag of ['catalog', 'rankings', 'study-content'])
    assert.ok(queryTags('/api/app-search/?q=a').has(tag))
  for (const tag of ['saved-filters', 'library', 'rankings'])
    assert.ok(queryTags('/api/works/facets/?saved_filter=4').has(tag))
})

test('navigation prefetch uses identical multi-value filters for rows and prospective counts', () => {
  const browse = {
    ...catalogBrowseDefaults,
    q: 'History',
    country_any: JSON.stringify(['France', 'Bosnia, historical association']),
    genre_not: JSON.stringify(['Horror']),
    field: '',
    saved_filter: '8',
    page: '3',
  }
  const query = new URLSearchParams(browse)
  const filters = catalogRequestParams(browse)
  const rows = new URLSearchParams(filters)
  rows.set('compact', '1')
  rows.set('page', '3')
  assert.deepEqual(prefetchPlan(`#/catalog?${query}`, true).paths.map(canonicalQueryKey), [
    canonicalQueryKey(`/api/works/?${rows}`),
    canonicalQueryKey(`/api/works/facets/?${filters}`),
  ])
})
