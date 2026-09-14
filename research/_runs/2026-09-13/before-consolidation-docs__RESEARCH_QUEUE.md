# Ranking research queue

**Checkpoint 13 September:** publish illustrated initial selections now, retaining both orders; expansion continues afterward. Actual source counts: 214 / 99 / 116 / 97 / 99. Catalog: eight books with eight verified English editions and eight authors; images and ranking entries are the next writes. See HANDOVER.md for the current checkpoint. Older pilot counts below are historical.

**Latest authorization:** complete and publish the five broad targets first, retaining both selected orderings; afterward research England, Ireland, United States, Germany, France, Poland, China and Japan, then philosophy by branch/topic. See [completion plan](../research/COMPLETION_PLAN.md). Earlier phase restrictions below are historical and do not prevent the authorized catalog/population work once evidence and methodology are ready.

Research resumed on 12 September 2026 for **the first five targets only**, superseding the earlier application-build pause. Each has its own saved and imported evidence ledger. The owner wants substantially more diverse, exploratory, worldwide and non-English sources—over 100 and toward 200 or more where useful for these broad scopes. Each target still requires **a hard minimum of 50 distinct, relevant, consulted, diverse sources, ideally many, many more than 50**, under [the research skill](skills/humanities-ranking-research/SKILL.md). These are source requirements, separate from the number of ranked entries; no threshold proves completion.

Criteria and weights remain to be designed per ranking. The owner requested actual draft rankings and chose **both critical standing/enduring influence and reading value today**. [Five two-lens pilot comparisons](../research/RANKING_DRAFTS.md) now order 25 candidates each with evidence links and caveats. These are partial editorial proposals, not completed worldwide Top 25s or app publications. Final criterion values and personalized positions stay unset. Publisher source positions remain separate; Penguin’s numbered classics selection is explicitly unordered.

| Target | Intended length | State |
| --- | --- | --- |
| All books, all time, across subjects | 100–200 | 191 eligible sources imported through batch 25; two 25-candidate pilot orders; incomplete |
| Literary fiction books, all time | 100–200 | 85 eligible sources imported; two 25-candidate pilot orders; incomplete |
| Nonfiction books, all time | 100–200 | 103 eligible sources imported; two 25-candidate pilot orders; incomplete |
| Philosophy books, all time | 100–200 | 91 eligible sources imported; two 25-candidate pilot orders; incomplete |
| Philosophers, all time | 100–200, subject to criteria | 93 eligible sources imported; two 25-candidate pilot orders; incomplete |
| Other literary works, all time | 100–200 with form filters | Queued |
| Short stories, essays, and poems separately | 100–200 where justified | Queued |
| Books by major country/literary tradition | 100–200 where justified | Queued; one target per country |
| Books by century | 100–200 where justified | Queued; one target per century |
| BCE works | Variable, up to broad-list range | Queued as an initial navigation grouping |
| Major philosophy topics: epistemology, metaphysics, ethics, political philosophy, aesthetics, logic, mind, language, science | Approximately 100 per major topic | Queued; one target per topic |
| Narrow philosophy topics, including philosophy of mathematics | Approximately 10 initially, adjustable | Queued; one target per topic |
| Genres, styles, eras, and custom themes/tags | 50–100 where justified | On-demand targets |
| An author's books / all eligible works | Usually 10–15 | On-demand targets |
| One or three books from every country | 1–3 per country | Queued; progressive country coverage |

Initial country priorities explicitly named: England, China, United States, France, and Japan. Further countries can be added without schema changes. Do not treat this starting set as the complete set of major traditions.

Immediate synthesis work: strengthen the pilot’s weak candidate dossiers with direct criticism and substantive reader responses, expand the comparison universe, and verify specific complete English editions. All-books/nonfiction need considerably more science, history, economics, art and biography. Philosophy needs more non-reference scholarship and independent reader discussion; literature needs deeper comparative scholarship and further worldwide candidate exploration. Per-target `RESEARCH.md` and `evidence-audit-v1.json` record actual language/family/domain distributions, limitations and remaining contenders. No catalog items or ranking entries have been populated by the research importer.

The bootstrap command creates empty database definitions for these initial country scopes, the broad/form scopes, centuries 1–21 and BCE, major philosophy topics (books and philosophers), mathematics, the world reading collection and named external collections. Each has its own stable slug and source relationships. Author-specific and custom-tag rankings are created as requested. The 51-source survey supplies no automatic source credit to these other rankings. A source about an unrelated subject does not count merely because it shares a domain or platform with useful material.

Save each consulted batch to its target ledger and import it with `manage.py import_research <file> --target <slug>`. Preserve `updated_at`, completed-research dates and source-check dates as distinct concepts. A partial batch or metadata edit never makes a ranking appear freshly researched; see [ranking freshness](RANKING_FRESHNESS.md).

Country membership follows a documented literary/cultural association and may be multiple. Keep England and the UK distinct. Separate country, original language, setting, and historical polity; do not derive one blindly from another. The every-country feature needs a maintained coverage registry including territories/contested classifications as explicit product choices, available English editions, research status, and gaps. Separately researched countries each need their own corpus with 50 as the hard minimum and many, many more sources as the desired breadth. A world overview cannot supply 50 loosely related sources to every country automatically.

English availability is an eligibility requirement for recommendations now. Works from any original language or country may qualify when an English translation exists. Verify a specific translation/edition, not merely an English title in an article. When availability cannot be verified, retain the candidate as unresolved rather than claiming the country has no literature.

Use original composition/publication dates for historical scopes, not the English translation date. Record uncertain dates/ranges. BCE is an initial grouping, not a claim that few ancient works survive. Century filters must use documented boundaries and handle no year zero. Distinguish the 1900–1909 decade from the twentieth century.

List sizes are targets, not permission to pad. If an author has fewer than ten eligible books, show the complete eligible set and its count. An author with three books must not gain invented titles or have individual essays inserted into a books-only list. Topic-specific depth and the availability of evidence determine whether a target of 50 or 100 is defensible.

Books-only rankings contain complete book-length works, with literary fiction and nonfiction available separately. All-works and other-works rankings can include individually identifiable stories, essays, poems, and other supported forms. Record collections and their contents separately so a collected edition and an individual story do not become accidental duplicates. Mixed-form eligibility is always explicit in the scope.

Translations deserve their own recommendation records: translator, edition, complete/abridged status, readability, style/fidelity tradeoffs, notes/apparatus, and sources. Consult translators, scholars, reviewers, forums, reader discussions, and Benjamin McEvoy's recommendations. A standalone requested translation-comparison research target carries the same hard minimum of 50 sources and the same explicit aim of many, many more than 50.
