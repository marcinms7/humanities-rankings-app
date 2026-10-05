import { useState } from 'react'
import { label } from './components'
import type { ApiCatalogFacets } from './generated/apiContracts'
import type { BrowseChanges } from './browseState'
import {
  catalogFacetNames,
  catalogSelectionLimit,
  catalogSelectionPatch,
  matchingCatalogOptions,
  toggleCatalogValue,
  type CatalogFacetMode,
  type CatalogFacetName,
} from './catalogFilterState'
import './catalogFilters.css'

type Facet = ApiCatalogFacets['facets']['field']
const titles: Record<CatalogFacetName, string> = {
  field: 'Subjects',
  genre: 'Genres',
  form: 'Forms',
  country: 'Countries & associations',
}
const emptyFacet: Facet = { include: [], exclude: [], inherited: false, options: [] }

function FacetPicker({
  name,
  facet,
  disabled,
  saved,
  patch,
}: {
  name: CatalogFacetName
  facet: Facet
  disabled: boolean
  saved: boolean
  patch: (values: BrowseChanges) => void
}) {
  const [search, setSearch] = useState('')
  const selected = new Set([...facet.include, ...facet.exclude])
  const options = matchingCatalogOptions(facet.options, facet, search)
  const visible = options.slice(0, 60)
  const change = (mode: CatalogFacetMode, value: string) =>
    patch(catalogSelectionPatch(name, toggleCatalogValue(facet, mode, value)))

  return (
    <details className="catalog-facet">
      <summary>
        <span>{titles[name]}</span>
        <span className="small-text muted">
          {selected.size ? `${facet.include.length} included · ${facet.exclude.length} excluded` : 'Any'}
          {facet.inherited && ' · saved'}
        </span>
      </summary>
      <div className="catalog-facet-panel">
        <div className="catalog-facet-tools">
          <button
            type="button"
            className="text-link small-text"
            onClick={() => patch(catalogSelectionPatch(name, { include: [], exclude: [] }))}
          >
            Allow any
          </button>
          {saved && name !== 'form' && (
            <button
              type="button"
              className="text-link small-text"
              onClick={() => patch({ [name]: null, [`${name}_any`]: null, [`${name}_not`]: null, page: 1 })}
            >
              Use saved {name === 'field' ? 'subject' : name}
            </button>
          )}
        </div>
        {(facet.options.length > 12 || search) && (
          <input
            className="input"
            aria-label={`Find ${titles[name].toLowerCase()} filters`}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={`Find ${titles[name].toLowerCase()}…`}
          />
        )}
        <div className="catalog-facet-options" aria-busy={disabled}>
          {visible.map((option) => (
            <div className="catalog-facet-option" key={option.value}>
              <span>{label(option.value)}</span>
              <div>
                {(['include', 'exclude'] as const).map((mode) => {
                  const active = facet[mode].includes(option.value)
                  const verb = active ? 'Remove' : mode === 'include' ? 'Include' : 'Exclude'
                  const count = option[`${mode}_count`]
                  return (
                    <button
                      key={mode}
                      type="button"
                      className={`catalog-facet-choice ${mode}`}
                      aria-pressed={active}
                      aria-label={`${verb} ${label(option.value)}${active ? ` ${mode === 'include' ? 'inclusion' : 'exclusion'}` : ''}: ${disabled ? 'updating result count' : `${count.toLocaleString()} books would match`}`}
                      title={`${active ? 'Remove this filter' : `${label(mode)} this value`} · ${count.toLocaleString()} total books after clicking`}
                      disabled={disabled || (!active && facet[mode].length >= catalogSelectionLimit)}
                      onClick={() => change(mode, option.value)}
                    >
                      {active ? '✓ ' : ''}
                      {label(mode)} <span>{disabled ? '…' : count.toLocaleString()}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
          {!visible.length && (
            <p className="small-text muted">{disabled ? 'Loading filters…' : 'No matching options.'}</p>
          )}
        </div>
        {options.length > visible.length && (
          <p className="small-text muted">
            Showing {visible.length} of {options.length} options. Search to find more.
          </p>
        )}
        {(facet.include.length >= catalogSelectionLimit || facet.exclude.length >= catalogSelectionLimit) && (
          <p className="small-text muted">
            Up to {catalogSelectionLimit} values per include or exclude selection.
          </p>
        )}
      </div>
    </details>
  )
}

export function CatalogFilters({
  data,
  loading,
  saved,
  patch,
}: {
  data: ApiCatalogFacets | null
  loading: boolean
  saved: boolean
  patch: (values: BrowseChanges) => void
}) {
  // Keep the option controls mounted while the next exact counts load, so
  // keyboard focus and the local option search survive each selection.
  const [lastData, setLastData] = useState(data)
  if (data && data !== lastData) setLastData(data)
  const current = data || lastData
  return (
    <section className="catalog-filters" aria-label="Catalog filters">
      <p className="small-text muted">
        Include any selected value within a filter; every filter applies together. Exclusions remove matching
        books. Numbers show the <strong>total books after clicking</strong>, including when removing a
        selection.
      </p>
      <div className="catalog-facet-grid">
        {catalogFacetNames.map((name) => (
          <FacetPicker
            key={name}
            name={name}
            facet={current?.facets[name] || emptyFacet}
            disabled={loading || !data}
            saved={saved}
            patch={patch}
          />
        ))}
      </div>
    </section>
  )
}
