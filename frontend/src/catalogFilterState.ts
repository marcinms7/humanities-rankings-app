export const catalogFacetNames = ['field', 'genre', 'form', 'country'] as const
export type CatalogFacetName = (typeof catalogFacetNames)[number]
export type CatalogFacetMode = 'include' | 'exclude'
export const catalogSelectionLimit = 50

export function matchingCatalogOptions<T extends { value: string }>(
  options: T[],
  selection: { include: string[]; exclude: string[] },
  search: string,
): T[] {
  const selected = new Set([...selection.include, ...selection.exclude])
  const term = search.trim().toLocaleLowerCase()
  return options
    .filter((option) => option.value.replace(/_/g, ' ').toLocaleLowerCase().includes(term))
    .sort((a, b) => Number(selected.has(b.value)) - Number(selected.has(a.value)))
}

export const catalogBrowseDefaults = {
  q: '',
  field: 'all',
  form: 'all',
  country: 'all',
  genre: 'all',
  field_any: '',
  field_not: '',
  form_any: '',
  form_not: '',
  country_any: '',
  country_not: '',
  genre_any: '',
  genre_not: '',
  page: '1',
  saved_filter: '',
}

/** Shared by actual navigation and intent preloading. [] is an explicit override. */
export function catalogRequestParams(browse: Record<string, string>): URLSearchParams {
  const params = new URLSearchParams()
  if (browse.q) params.set('search', browse.q)
  if (browse.saved_filter) params.set('saved_filter', browse.saved_filter)
  for (const name of catalogFacetNames) {
    if (browse[`${name}_any`]) params.set(`${name}_any`, browse[`${name}_any`])
    else if (browse[name] !== undefined && browse[name] !== 'all') params.set(name, browse[name])
    if (browse[`${name}_not`]) params.set(`${name}_not`, browse[`${name}_not`])
  }
  return params
}

export function toggleCatalogValue(
  selection: { include: string[]; exclude: string[] },
  mode: CatalogFacetMode,
  value: string,
): { include: string[]; exclude: string[] } {
  const include = new Set(selection.include)
  const exclude = new Set(selection.exclude)
  const target = mode === 'include' ? include : exclude
  const opposite = mode === 'include' ? exclude : include
  if (target.has(value)) target.delete(value)
  else if (target.size < catalogSelectionLimit) {
    target.add(value)
    opposite.delete(value)
  }
  return { include: [...include], exclude: [...exclude] }
}

export function catalogSelectionPatch(
  name: CatalogFacetName,
  selection: { include: string[]; exclude: string[] },
) {
  return {
    [name]: null,
    [`${name}_any`]: JSON.stringify(selection.include),
    [`${name}_not`]: selection.exclude.length ? JSON.stringify(selection.exclude) : null,
    page: 1,
  }
}
