# Drop ranking research files here

Put Microsoft Word `.docx` research documents, PDFs, `.odt`, Markdown, JSON, spreadsheets, or accompanying image files here. A folder per target/batch is helpful but optional. Keep related documents and images together; descriptive filenames help identify their scope. Word `.docx` is preferred for the external-agent research brief, but other readable documents can be processed.

This is a persistent project inbox, not an automatic importer. Dropping files here does not change the app database. Ask a chat opened in this project to process them. The uploaded contents are gitignored; this README is retained in version control. Keep your own backup of original files.

Copy this prompt into a new chat:

> Read AGENTS.md, HANDOVER.md and docs/EXTERNAL_AGENT_RESULTS_INTAKE.md. Process the unprocessed files in pending_rankings_to_process/ and update the relevant rankings from the supplied material. Preserve the originals, reconcile sources and catalog identities with the existing database, and save supported evidence and authorized ranking/collection updates with provenance and revisions. Keep private user data intact. Do not invent missing criteria, scores or sources. Do not start a new broad web-research project; identify missing evidence and do only necessary source verification unless I ask for more research. Record what was processed and imported, what remains, and update HANDOVER.md.

Optional accompanying `NOTES.md`: target/ranking slug, research synthesis vs original published ranking vs reading collection, which files belong together, agreed criteria if any, and any requested corrections. You do not have to supply JSON or manually map database IDs.

## Instructions for the receiving agent

Follow the [intake guide](../docs/EXTERNAL_AGENT_RESULTS_INTAKE.md). List actual files, excluding this README and your own tracking files; do not assume everything has already been processed or that a folder name is definitive scope. Read the prior `PROCESSING_LOG.md` if one exists.

For each batch, record paths and content hashes, received/processed timestamps, resolved target, original-copy location, outcome, imported counts, pending questions and errors in `PROCESSING_LOG.md`. Copy originals to `research/incoming/<target>/<run-id>/` before normalization, preserving the inbox files. For attachments, save an accessible local original before relying on it across chats. If an attachment cannot be accessed, ask the owner to place it in this folder rather than pretending it was read.

Recognize unchanged previously processed files by content hash and outcome, not just filename. Resume partial or failed batches from the recorded state; changed files are new revisions requiring reconciliation. Use statuses such as `received`, `partially_imported`, `imported`, or `needs_clarification`. File processing status does not mean the ranking research is complete or published. No status may claim success before a confirmed database write.

The source standard still applies: **50 is the hard minimum per synthesis target, ideally many, many more relevant diverse consulted sources**. Files below that standard can supply useful evidence but do not establish completed research. Faithfully extracted named published lists/collections follow the separate import rules. Source evidence imports alone do not create catalog entries or final rankings; report these outcomes separately. No supplied file authorizes deleting shared records, overwriting private preferences, or inventing missing facts.
