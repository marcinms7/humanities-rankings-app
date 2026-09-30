# Ranking update prompts — 27 September 2026

Each prompt is complete and independent: it includes its task, current ranking, saved editorial orders, candidate evidence, and every current target-local source record with its saved evidence/access labels. Start a separate agent conversation for each target.

## How to use

1. Open a **complete prompt** below and copy the whole file into the other agent. You can attach the text file instead and say: ‘Read the entire attached request, including all entries and source records, and carry out the update.’
2. If the paste is too large, use that target’s **numbered parts**, in order, in the same conversation. Each part instructs the agent to wait until the last part. These are message-size chunks; they do not increase the other agent’s total context capacity. If the full record does not fit, use an agent that can read attached files or a larger context.
3. The requested return is a complete Word `.docx` report with the revised ranking, full source register, candidate citations and change log. Structured Markdown/text is accepted when document creation is unavailable. Return those files to the app integration agent for reconciliation/import.

Snapshot: `2026-09-27T20:44:44.053349+00:00`. **66 rankings; 8,996 current ranking entries; 17,142 source records.** Source totals are per-target records, including leads; they are not a count of globally unique or verified sources. Also included: 218 conflicting current English-history ledger records in an explicit separate namespace. No live ranking, source record or private data was changed.

The pack covers all researched/curated rankings. Priorities 1 and 2 cover the evidence/identity improvements flagged in the audit; priority 3 contains optional follow-ups for comparatively better-supported targets. Original publisher rankings and reading collections are outside this synthesis-update pack.

Snapshots are exported directly from the current SQLite database in a single read-only transaction. Current `sources.json` ledgers were also reconciled; nonconflicting source records are already in the database export. The raw public research snapshot for each target is available in `snapshots/`. No account details, private preferences, library records or share tokens are included.

## First: evidence and identity repairs (14)

| Ranking | Entries | All source records | Complete prompt | Numbered parts |
|---|---:|---:|---|---|

| Top 3 books by country | 617 | 1395 | [Open](prompts/books-every-country.txt) | [46 parts](paste-parts/books-every-country/INDEX.md) |

| Ancient Rome · Books | 100 | 226 | [Open](prompts/history-books-ancient-rome.txt) | [10 parts](paste-parts/history-books-ancient-rome/INDEX.md) |

| Medieval history · Books | 50 | 137 | [Open](prompts/history-books-medieval.txt) | [6 parts](paste-parts/history-books-medieval/INDEX.md) |

| Books · Africa | 149 | 255 | [Open](prompts/books-africa.txt) | [12 parts](paste-parts/books-africa/INDEX.md) |

| Historical fiction · All time | 99 | 263 | [Open](prompts/books-historical-fiction.txt) | [10 parts](paste-parts/books-historical-fiction/INDEX.md) |

| Horror books · All time | 150 | 267 | [Open](prompts/books-horror-all-time.txt) | [16 parts](paste-parts/books-horror-all-time/INDEX.md) |

| Shōnen manga · All time | 200 | 276 | [Open](prompts/manga-shonen-all-time.txt) | [14 parts](paste-parts/manga-shonen-all-time/INDEX.md) |

| Seinen manga · All time | 200 | 253 | [Open](prompts/manga-seinen-all-time.txt) | [13 parts](paste-parts/manga-seinen-all-time/INDEX.md) |

| Shōjo manga · All time | 200 | 273 | [Open](prompts/manga-shojo-all-time.txt) | [14 parts](paste-parts/manga-shojo-all-time/INDEX.md) |

| Josei manga · All time | 200 | 304 | [Open](prompts/manga-josei-all-time.txt) | [14 parts](paste-parts/manga-josei-all-time/INDEX.md) |

| History books · All time | 234 | 200 | [Open](prompts/history-books-all-time.txt) | [24 parts](paste-parts/history-books-all-time/INDEX.md) |

| Poetry · All time | 162 | 200 | [Open](prompts/poetry-all-time.txt) | [20 parts](paste-parts/poetry-all-time/INDEX.md) |

| Philosophy books · All time | 250 | 256 | [Open](prompts/philosophy-books-all-time.txt) | [25 parts](paste-parts/philosophy-books-all-time/INDEX.md) |

| Literary fiction · All time | 250 | 101 | [Open](prompts/literature-all-time.txt) | [13 parts](paste-parts/literature-all-time/INDEX.md) |

## Next: targeted evidence and coverage updates (41)

| Ranking | Entries | All source records | Complete prompt | Numbered parts |
|---|---:|---:|---|---|

| Ancient works · All time | 130 | 221 | [Open](prompts/books-ancient.txt) | [10 parts](paste-parts/books-ancient/INDEX.md) |

| Ancient world · History books | 100 | 230 | [Open](prompts/history-books-ancient-world.txt) | [9 parts](paste-parts/history-books-ancient-world/INDEX.md) |

| Biography & autobiography · All time | 150 | 277 | [Open](prompts/books-biography-autobiography-all-time.txt) | [17 parts](paste-parts/books-biography-autobiography-all-time/INDEX.md) |

| Books · All time | 250 | 415 | [Open](prompts/books-all-time.txt) | [30 parts](paste-parts/books-all-time/INDEX.md) |

| Books · Arabic tradition | 98 | 207 | [Open](prompts/books-arabic.txt) | [9 parts](paste-parts/books-arabic/INDEX.md) |

| Books · England | 100 | 247 | [Open](prompts/books-england.txt) | [10 parts](paste-parts/books-england/INDEX.md) |

| Books · France | 100 | 130 | [Open](prompts/books-france.txt) | [7 parts](paste-parts/books-france/INDEX.md) |

| Books · Germany | 100 | 103 | [Open](prompts/books-germany.txt) | [7 parts](paste-parts/books-germany/INDEX.md) |

| Books · India | 100 | 188 | [Open](prompts/books-india.txt) | [8 parts](paste-parts/books-india/INDEX.md) |

| Books · Ireland | 49 | 239 | [Open](prompts/books-ireland.txt) | [7 parts](paste-parts/books-ireland/INDEX.md) |

| Books · Italy | 100 | 145 | [Open](prompts/books-italy.txt) | [7 parts](paste-parts/books-italy/INDEX.md) |

| Books · Medieval world | 100 | 118 | [Open](prompts/books-medieval.txt) | [7 parts](paste-parts/books-medieval/INDEX.md) |

| Books · Scotland | 50 | 270 | [Open](prompts/books-scotland.txt) | [8 parts](paste-parts/books-scotland/INDEX.md) |

| Books · South America | 150 | 260 | [Open](prompts/books-south-america.txt) | [12 parts](paste-parts/books-south-america/INDEX.md) |

| Books · Southeast Asia | 150 | 268 | [Open](prompts/books-southeast-asia.txt) | [14 parts](paste-parts/books-southeast-asia/INDEX.md) |

| Books · Turkish literary tradition | 100 | 137 | [Open](prompts/books-turkish-tradition.txt) | [8 parts](paste-parts/books-turkish-tradition/INDEX.md) |

| Books · United States | 100 | 113 | [Open](prompts/books-united-states.txt) | [7 parts](paste-parts/books-united-states/INDEX.md) |

| Books · Victorian world | 150 | 229 | [Open](prompts/books-victorian.txt) | [12 parts](paste-parts/books-victorian/INDEX.md) |

| Chinese history · Books | 49 | 120 | [Open](prompts/history-books-chinese-history.txt) | [5 parts](paste-parts/history-books-chinese-history/INDEX.md) |

| Classical education · Guide | 250 | 311 | [Open](prompts/classical-education-guide.txt) | [20 parts](paste-parts/classical-education-guide/INDEX.md) |

| English history · Books | 100 | 218 | [Open](prompts/history-books-england.txt) | [13 parts](paste-parts/history-books-england/INDEX.md) |

| Epistemology · Works | 100 | 163 | [Open](prompts/books-epistemology.txt) | [8 parts](paste-parts/books-epistemology/INDEX.md) |

| Essays · All time | 100 | 225 | [Open](prompts/essay-all-time.txt) | [9 parts](paste-parts/essay-all-time/INDEX.md) |

| Ethics · Works | 98 | 138 | [Open](prompts/books-ethics.txt) | [7 parts](paste-parts/books-ethics/INDEX.md) |

| Fantasy books · All time | 150 | 267 | [Open](prompts/books-fantasy-all-time.txt) | [17 parts](paste-parts/books-fantasy-all-time/INDEX.md) |

| Funniest books · All time | 150 | 354 | [Open](prompts/books-funniest-all-time.txt) | [19 parts](paste-parts/books-funniest-all-time/INDEX.md) |

| History of London · Books | 50 | 266 | [Open](prompts/history-books-london.txt) | [8 parts](paste-parts/history-books-london/INDEX.md) |

| Metaphysics · Books | 100 | 153 | [Open](prompts/books-metaphysics.txt) | [8 parts](paste-parts/books-metaphysics/INDEX.md) |

| Most beautifully written books · All time | 150 | 320 | [Open](prompts/books-beautifully-written-all-time.txt) | [18 parts](paste-parts/books-beautifully-written-all-time/INDEX.md) |

| Most important literary works · All time | 250 | 611 | [Open](prompts/other-works-all-time.txt) | [25 parts](paste-parts/other-works-all-time/INDEX.md) |

| Nonfiction · All time | 250 | 322 | [Open](prompts/nonfiction-all-time.txt) | [26 parts](paste-parts/nonfiction-all-time/INDEX.md) |

| Philosophers · All time | 23 | 100 | [Open](prompts/philosophers-all-time.txt) | [4 parts](paste-parts/philosophers-all-time/INDEX.md) |

| Philosophy of language · Works | 20 | 135 | [Open](prompts/books-philosophy-of-language.txt) | [4 parts](paste-parts/books-philosophy-of-language/INDEX.md) |

| Philosophy of mathematics · Works | 20 | 132 | [Open](prompts/books-philosophy-of-mathematics.txt) | [4 parts](paste-parts/books-philosophy-of-mathematics/INDEX.md) |

| Philosophy of mind · Works | 50 | 153 | [Open](prompts/books-philosophy-of-mind.txt) | [6 parts](paste-parts/books-philosophy-of-mind/INDEX.md) |

| Philosophy of science · Works | 50 | 120 | [Open](prompts/books-philosophy-of-science.txt) | [5 parts](paste-parts/books-philosophy-of-science/INDEX.md) |

| Plays · All time | 149 | 266 | [Open](prompts/play-all-time.txt) | [12 parts](paste-parts/play-all-time/INDEX.md) |

| Political philosophy · Works | 50 | 133 | [Open](prompts/books-political-philosophy.txt) | [6 parts](paste-parts/books-political-philosophy/INDEX.md) |

| Short stories · All time | 150 | 227 | [Open](prompts/short-story-all-time.txt) | [11 parts](paste-parts/short-story-all-time/INDEX.md) |

| Social history · Books | 50 | 243 | [Open](prompts/history-books-social.txt) | [7 parts](paste-parts/history-books-social/INDEX.md) |

| World history · Books | 150 | 228 | [Open](prompts/history-books-world.txt) | [12 parts](paste-parts/history-books-world/INDEX.md) |

## Optional: focused follow-up and maintenance (11)

| Ranking | Entries | All source records | Complete prompt | Numbered parts |
|---|---:|---:|---|---|

| Books · Caribbean | 50 | 225 | [Open](prompts/books-caribbean.txt) | [7 parts](paste-parts/books-caribbean/INDEX.md) |

| Books · Chinese-language tradition | 100 | 245 | [Open](prompts/books-china.txt) | [10 parts](paste-parts/books-china/INDEX.md) |

| Books · Japan | 100 | 259 | [Open](prompts/books-japan.txt) | [11 parts](paste-parts/books-japan/INDEX.md) |

| Books · Poland | 100 | 241 | [Open](prompts/books-poland.txt) | [11 parts](paste-parts/books-poland/INDEX.md) |

| Books · Russian literary tradition | 99 | 220 | [Open](prompts/books-russian.txt) | [9 parts](paste-parts/books-russian/INDEX.md) |

| Comics and graphic novels · All time | 250 | 827 | [Open](prompts/comics-graphic-novels-all-time.txt) | [34 parts](paste-parts/comics-graphic-novels-all-time/INDEX.md) |

| Manga · All time | 250 | 596 | [Open](prompts/manga-all-time.txt) | [26 parts](paste-parts/manga-all-time/INDEX.md) |

| Most addictive books · All time | 150 | 281 | [Open](prompts/books-addictive-all-time.txt) | [14 parts](paste-parts/books-addictive-all-time/INDEX.md) |

| Most mainstream-loved books · All time | 150 | 281 | [Open](prompts/books-mainstream-loved-all-time.txt) | [16 parts](paste-parts/books-mainstream-loved-all-time/INDEX.md) |

| Science books · All time | 150 | 270 | [Open](prompts/science-books-all-time.txt) | [16 parts](paste-parts/science-books-all-time/INDEX.md) |

| Science fiction · All time | 150 | 289 | [Open](prompts/books-science-fiction-all-time.txt) | [16 parts](paste-parts/books-science-fiction-all-time/INDEX.md) |

## Files and checks

`manifest.json` and `manifest.csv` list exact counts, file sizes and SHA-256 hashes. `evidence-audit.csv` is the earlier saved evidence audit; its metrics are indicators of saved linkage, not independent source verification. The export checked that every current curated target, active entry and registered source is present, all prompt sections match their counts, and concatenating the paste-part bodies reproduces each complete prompt.

Known input defects are preserved and labelled. Horror includes old editorial mappings after catalog repairs; English history includes conflicting file-ledger source IDs. Missing references are supplied as citation stubs rather than represented as verified sources. The other agent is instructed to report proposed repairs explicitly.


**Latest instruction: research at least 100 genuinely new, relevant, substantively consulted sources per selected ranking, then update it using the expanded evidence. Existing sources, supplied leads, mirrors and copied lists do not count toward these 100 additions. This does not mean all 66 rankings need to be commissioned; start with the priority targets.**
