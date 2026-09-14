# Interface direction

The requested character is modern, elegant, academic, and comfortable for browsing books and authors. The interface should work equally well in light and dark themes, with images integrated into the layout.

Two researched references:

- [Linear's interface redesign](https://linear.app/now/how-we-redesigned-the-linear-ui): study its navigation hierarchy, restrained surfaces, list/detail layouts, and coordinated light/dark themes. Use its clarity as inspiration while developing a distinct literary identity.
- [Readwise Reader appearance controls](https://docs.readwise.io/reader/docs/faqs/appearance): study reading-oriented typography and the light/dark/system preference. Font, spacing, and line-width controls are useful references for long ranking explanations.

Proposed application:

- Warm neutral backgrounds, ink text, and restrained green accents in light mode; charcoal, warm text, and muted gold accents in dark mode. Central theme variables control surfaces, borders, text, focus, and accents.
- Serif titles and readable sans-serif interface labels, with balanced density rather than a decorative antique-library treatment.
- Ranking rows with a stable rank/score column, uncropped cover, title/contributors, compact tags, estimated reading time, and a clear save action.
- Portraits in author summaries, with consistent sizing and predictable fallbacks; preserve the original cover/portrait colors across themes. Theme the surrounding surface instead of inverting images.
- A detail panel for score explanations, evidence, and translations. Source count and research status should be discoverable without overwhelming every browsing row.
- Filters for field, country/tradition, century, genre, form, and user tags; saved filter views and weight profiles.
- Planner month columns on larger screens and a focused month view on phones. Support keyboard alternatives to drag-and-drop.
- Persistent light/dark/system setting, readable contrast, visible focus, reduced motion, and intentional loading, missing-image, empty, and incomplete-research states.

The initial interface implements this visual direction; the owner explicitly likes its colours and style. Preserve the palette. September 12 refinements: Reading collections immediately follows Published rankings; the left sidebar scrolls independently; search uses separated icon/input space; the planner rhythm is a compact summary with expandable, equal-height controls; each month has an add button. The latest refinements are built, with browser verification left to the owner as requested. Future controls should keep the month cards near the top and avoid a large settings panel above the plan.
