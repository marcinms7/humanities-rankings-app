# API cover test

Google Books returned HTTP 429 for an unauthenticated title/author query. Open Library Search returned a valid result, and its Covers endpoint is suitable for verified ISBN/cover IDs. Bulk enrichment therefore uses Open Library with exact title/author matching, a resumable cache, and preserved attribution; existing covers are skipped.
