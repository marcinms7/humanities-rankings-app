import { useState } from 'react'
import { BookOpen, Compass, PenLine, Library, Sun, ArrowRight } from 'lucide-react'

const groups = [
  {
    name: 'My study',
    caption: 'Start & plan',
    icon: Sun,
    items: ['Today’s study', 'Start here', 'My classical plan'],
  },
  {
    name: 'Read',
    caption: 'Texts & reading paths',
    icon: BookOpen,
    items: ['Reading desk', 'Syllabus', 'Rankings', 'Works & preparation', 'Reading order', 'Edition guide'],
  },
  {
    name: 'Practise',
    caption: 'Write & remember',
    icon: PenLine,
    items: [
      'Translation lab',
      'Recall & review',
      'Essay workshop',
      'Languages',
      'Passage exercises',
      'Notebook',
      'Commonplace book',
    ],
  },
  {
    name: 'Explore',
    caption: 'The ancient world',
    icon: Compass,
    items: [
      'Historical atlas',
      'Context & glossary',
      'Reception trails',
      'Connections',
      'Timeline',
      'Art & archaeology',
    ],
  },
  {
    name: 'Resources',
    caption: 'Courses & references',
    icon: Library,
    items: [
      'Courses & materials',
      'Listening guide',
      'Course options',
      'Expanded curriculum',
      'Study sources',
      'Sources & approach',
    ],
  },
]

export function ClassicalNavigation({
  tab,
  change,
  disabled,
}: {
  tab: string
  change: (tab: string) => void
  disabled: boolean
}) {
  const [last, setLast] = useState<Record<string, string>>({})
  const selected = groups.find((g) => g.items.includes(tab)) || groups[0]
  function navigate(value: string) {
    setLast((s) => ({ ...s, [selected.name]: tab }))
    change(value)
  }
  return (
    <nav className="study-navigation" aria-label="Classical education sections">
      <div className="study-areas">
        {groups.map((g) => (
          <button
            type="button"
            disabled={disabled}
            key={g.name}
            className={`study-area ${g === selected ? 'is-active' : ''}`}
            aria-pressed={g === selected}
            onClick={() => navigate(g === selected ? tab : last[g.name] || g.items[0])}
          >
            <g.icon size={19} aria-hidden="true" />
            <span>
              <strong>{g.name}</strong>
              <small>{g.caption}</small>
            </span>
          </button>
        ))}
      </div>
      <div className="study-destinations" aria-label={`${selected.name} pages`}>
        {selected.items.map((item) => (
          <button
            type="button"
            disabled={disabled}
            className={`study-destination ${tab === item ? 'is-active' : ''}`}
            aria-current={tab === item ? 'page' : undefined}
            key={item}
            onClick={() => navigate(item)}
          >
            <span>{item}</span>
            {tab === item && <ArrowRight size={14} aria-hidden="true" />}
          </button>
        ))}
      </div>
    </nav>
  )
}
