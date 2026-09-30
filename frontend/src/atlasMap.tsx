import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, LocateFixed, Minus, Plus, RotateCcw } from 'lucide-react'
import paths from './assets/atlasWorldPaths.json'
import { projectCountry } from './atlasGeography'
import './atlasMap.css'

export { isMappedCountry } from './atlasGeography'

export type AtlasCountry = { key: string; label: string; count: number; saved: number; read: number }
type Metric = 'all' | 'saved' | 'read'
type View = { x: number; y: number; width: number; height: number }
type Marker = { key: string; x: number; y: number; entries: AtlasCountry[]; count: number }

const WORLD: View = { x: 0, y: 10, width: 720, height: 290 }
const ASPECT = WORLD.width / WORLD.height
const REGIONS: Record<string, [number, number, number, number]> = {
  Europe: [-16, 32, 46, 73],
  Africa: [-22, -36, 57, 38],
  Asia: [35, -12, 155, 75],
  Americas: [-170, -58, -32, 76],
  'Australia & western Pacific': [110, -50, 180, 25],
  'Central & eastern Pacific': [-180, -40, -125, 30],
}

function boundedView(x: number, y: number, width: number): View {
  const safeWidth = Math.min(WORLD.width, Math.max(30, width))
  const height = safeWidth / ASPECT
  return {
    x: Math.max(0, Math.min(WORLD.width - safeWidth, x)),
    y: Math.max(WORLD.y, Math.min(WORLD.y + WORLD.height - height, y)),
    width: safeWidth,
    height,
  }
}

function metricCount(country: AtlasCountry, metric: Metric) {
  return metric === 'all' ? country.count : country[metric]
}

function metricLabel(metric: Metric) {
  return metric === 'all' ? 'catalog books' : metric === 'saved' ? 'saved books' : 'books read'
}

export default function AtlasMap({
  countries,
  selected,
  metric,
  onSelect,
}: {
  countries: AtlasCountry[]
  selected: string
  metric: Metric
  onSelect: (key: string) => void
}) {
  const id = useId()
  const [view, setView] = useState(WORLD)
  const [region, setRegion] = useState('World')
  const [highlight, setHighlight] = useState('')
  const [expanded, setExpanded] = useState('')
  const [keyboardKey, setKeyboardKey] = useState('')
  const markerElements = useRef(new Map<string, SVGGElement>())
  const svgElement = useRef<SVGSVGElement>(null)
  const [viewportWidth, setViewportWidth] = useState(720)
  useEffect(() => {
    const element = svgElement.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setViewportWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const groups = useMemo(() => {
    const result = new Map<string, Marker>()
    for (const country of countries) {
      const point = projectCountry(country.key)
      const count = metricCount(country, metric)
      if (!point || !count) continue
      const key = point.join(',')
      let group = result.get(key)
      if (!group) {
        group = { key, x: point[0], y: point[1], count: 0, entries: [] }
        result.set(key, group)
      }
      group.entries.push(country)
      // Alternative saved labels can overlap; summing would double count books.
      group.count = Math.max(group.count, count)
    }
    return [...result.values()].sort((a, b) => b.count - a.count)
  }, [countries, metric])
  const visible = groups.filter(
    (marker) =>
      marker.x >= view.x &&
      marker.x <= view.x + view.width &&
      marker.y >= view.y &&
      marker.y <= view.y + view.height,
  )
  const selectedMarker = groups.find((group) => group.entries.some((entry) => entry.key === selected))
  const active = groups.find((group) => group.key === highlight) || selectedMarker
  const expandedMarker = groups.find((group) => group.key === expanded)
  const tabMarker =
    visible.find((marker) => marker.key === keyboardKey) ||
    visible.find((marker) => marker.key === selectedMarker?.key) ||
    visible[0]
  const selectedPoint = projectCountry(selected)
  const scale = view.width / Math.max(240, viewportWidth)

  function moveView(dx: number, dy: number) {
    setRegion('Custom')
    setView((current) =>
      boundedView(current.x + current.width * dx, current.y + current.height * dy, current.width),
    )
  }

  function zoom(factor: number) {
    setRegion('Custom')
    setView((current) => {
      const width = Math.min(720, Math.max(30, current.width * factor))
      return boundedView(
        current.x + (current.width - width) / 2,
        current.y + (current.height - width / ASPECT) / 2,
        width,
      )
    })
  }

  function chooseRegion(value: string) {
    if (value === 'Custom') return
    setRegion(value)
    if (value === 'World') {
      setView(WORLD)
      return
    }
    const [west, south, east, north] = REGIONS[value]
    const width = Math.max((east - west) * 2, (north - south) * 2 * ASPECT)
    setView(boundedView((west + east + 360 - width) / 2, (180 - north - south - width / ASPECT) / 2, width))
  }

  function activate(marker: Marker) {
    setHighlight(marker.key)
    if (marker.entries.length === 1) {
      setExpanded('')
      onSelect(marker.entries[0].key)
    } else {
      setExpanded(marker.key)
    }
  }

  function moveFocus(marker: Marker, key: string) {
    const direction = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[key]
    if (!direction) return
    const [dx, dy] = direction
    const target = visible
      .filter((other) => (other.x - marker.x) * dx + (other.y - marker.y) * dy > 0)
      .sort((a, b) => {
        const score = (candidate: Marker) => {
          const x = candidate.x - marker.x
          const y = candidate.y - marker.y
          return Math.hypot(x, y) + Math.abs(x * dy - y * dx) * 2
        }
        return score(a) - score(b)
      })[0]
    if (target) {
      setKeyboardKey(target.key)
      markerElements.current.get(target.key)?.focus()
    }
  }

  return (
    <section className="atlas-map" aria-label="Map of catalog country associations">
      <div className="atlas-map-toolbar">
        <label htmlFor={`${id}-region`}>
          Map area
          <select id={`${id}-region`} value={region} onChange={(event) => chooseRegion(event.target.value)}>
            <option>World</option>
            {Object.keys(REGIONS).map((name) => (
              <option key={name}>{name}</option>
            ))}
            {region === 'Custom' && <option>Custom</option>}
          </select>
        </label>
        <div className="atlas-map-buttons" role="group" aria-label="Map zoom">
          <button
            type="button"
            className="button secondary"
            title="Zoom in"
            aria-label="Zoom in"
            disabled={view.width <= 30}
            onClick={() => zoom(1 / 1.6)}
          >
            <Plus size={17} />
          </button>
          <button
            type="button"
            className="button secondary"
            title="Zoom out"
            aria-label="Zoom out"
            disabled={view.width >= 720}
            onClick={() => zoom(1.6)}
          >
            <Minus size={17} />
          </button>
          <button
            type="button"
            className="button secondary"
            title="Reset world map"
            aria-label="Reset world map"
            onClick={() => chooseRegion('World')}
          >
            <RotateCcw size={17} />
          </button>
          <button
            type="button"
            className="button secondary"
            title="Focus selected country"
            aria-label="Focus selected country"
            disabled={!selectedPoint}
            onClick={() => {
              if (!selectedPoint) return
              setRegion('Custom')
              setView(boundedView(selectedPoint[0] - 60, selectedPoint[1] - 60 / ASPECT, 120))
            }}
          >
            <LocateFixed size={17} />
          </button>
        </div>
        <div className="atlas-map-buttons" role="group" aria-label="Move map">
          <button
            type="button"
            className="button secondary"
            title="Move west"
            aria-label="Move map west"
            disabled={view.x <= 0}
            onClick={() => moveView(-0.3, 0)}
          >
            <ArrowLeft size={17} />
          </button>
          <button
            type="button"
            className="button secondary"
            title="Move east"
            aria-label="Move map east"
            disabled={view.x + view.width >= 720}
            onClick={() => moveView(0.3, 0)}
          >
            <ArrowRight size={17} />
          </button>
          <button
            type="button"
            className="button secondary"
            title="Move north"
            aria-label="Move map north"
            disabled={view.y <= WORLD.y}
            onClick={() => moveView(0, -0.3)}
          >
            <ArrowUp size={17} />
          </button>
          <button
            type="button"
            className="button secondary"
            title="Move south"
            aria-label="Move map south"
            disabled={view.y + view.height >= WORLD.y + WORLD.height}
            onClick={() => moveView(0, 0.3)}
          >
            <ArrowDown size={17} />
          </button>
        </div>
      </div>
      <p id={`${id}-keys`} className="atlas-map-help">
        Select a point to filter books. Zoom or choose an area for nearby countries. With a point focused, use
        arrow keys to move and Enter to select.
      </p>
      <svg
        ref={svgElement}
        className="atlas-map-svg"
        onMouseLeave={() => setHighlight('')}
        viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
        role="group"
        aria-label={`Country association map, ${metricLabel(metric)}`}
        aria-describedby={`${id}-keys`}
      >
        <g aria-hidden="true" className="atlas-map-land">
          {paths.map((path, index) => (
            <path key={index} d={path} vectorEffect="non-scaling-stroke" />
          ))}
        </g>
        <g aria-hidden="true" className="atlas-map-grid">
          {[-30, 0, 30, 60].map((latitude) => (
            <line
              key={latitude}
              x1="0"
              x2="720"
              y1={(90 - latitude) * 2}
              y2={(90 - latitude) * 2}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </g>
        {visible.map((marker) => {
          const isSelected = marker.entries.some((entry) => entry.key === selected)
          const label = marker.entries
            .map(
              (entry) =>
                `${entry.label}: ${metricCount(entry, metric).toLocaleString()} ${metricLabel(metric)}`,
            )
            .join('; ')
          const radius = (4 + Math.min(7, Math.log2(marker.count + 1))) * scale
          return (
            <g
              key={marker.key}
              ref={(element) => {
                if (element) markerElements.current.set(marker.key, element)
                else markerElements.current.delete(marker.key)
              }}
              className={`atlas-map-marker${isSelected ? ' is-selected' : ''}${marker.key === active?.key ? ' is-active' : ''}`}
              role="button"
              tabIndex={tabMarker?.key === marker.key ? 0 : -1}
              aria-label={label}
              aria-pressed={isSelected}
              aria-expanded={marker.entries.length > 1 ? expanded === marker.key : undefined}
              onMouseEnter={() => setHighlight(marker.key)}
              onFocus={() => {
                setKeyboardKey(marker.key)
                setHighlight(marker.key)
              }}
              onClick={() => activate(marker)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  activate(marker)
                } else if (event.key.startsWith('Arrow')) {
                  event.preventDefault()
                  moveFocus(marker, event.key)
                } else if (event.key === 'Escape') setExpanded('')
              }}
            >
              <title>
                {label}
                {marker.entries.length > 1 ? '. Select to choose a saved label.' : ''}
              </title>
              <circle
                className="atlas-map-hit"
                cx={marker.x}
                cy={marker.y}
                r={Math.max(radius, 12 * scale)}
              />
              <circle
                className="atlas-map-dot"
                cx={marker.x}
                cy={marker.y}
                r={radius}
                vectorEffect="non-scaling-stroke"
              />
              {marker.entries.length > 1 && (
                <circle
                  className="atlas-map-alias"
                  cx={marker.x}
                  cy={marker.y}
                  r={radius * 0.45}
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </g>
          )
        })}
      </svg>
      <div className="atlas-map-readout" aria-live="polite">
        {active ? (
          active.entries.map((entry) => (
            <span key={entry.key}>
              <strong>{entry.label}</strong> · {metricCount(entry, metric).toLocaleString()}{' '}
              {metricLabel(metric)}
            </span>
          ))
        ) : (
          <span>
            Larger points represent more books. Ringed points have separate saved labels at the same location.
          </span>
        )}
        {!visible.length && <span>No mapped countries with {metricLabel(metric)} in this area.</span>}
      </div>
      {expandedMarker && (
        <div className="atlas-map-aliases">
          <p>Choose the saved label. These labels share a map point but keep separate catalog filters.</p>
          <div>
            {expandedMarker.entries.map((entry, index) => (
              <button
                key={entry.key}
                type="button"
                autoFocus={index === 0}
                className={selected === entry.key ? 'button primary' : 'button secondary'}
                onClick={() => {
                  markerElements.current.get(expandedMarker.key)?.focus()
                  setExpanded('')
                  onSelect(entry.key)
                }}
              >
                {entry.label} · {metricCount(entry, metric).toLocaleString()}
              </button>
            ))}
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                setExpanded('')
                markerElements.current.get(expandedMarker.key)?.focus()
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
      <p className="atlas-map-credit">
        Modern reference map; points locate saved country labels, not authors’ birthplaces or historical
        borders. Small islands may have a point without a visible outline.{' '}
        <a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noreferrer">
          Made with Natural Earth
        </a>{' '}
        (public domain).
      </p>
    </section>
  )
}
