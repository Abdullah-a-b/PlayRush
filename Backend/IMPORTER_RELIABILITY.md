# Content importer reliability

Game content and import state use `PLAYRUSH_DATA_DIR`, defaulting to `/home/playrush/data` on Azure and Backend/data locally. The bundled JSON files seed an absent persistent file once; deploys do not overwrite generated content or import state. Seeding and content writes are atomic and protected by OS locks. Prior JSON revisions are retained as `.previous`.

Before modifying imported database content, the importer snapshots **game content tables only** under `DATA_DIR/backups`. No user tables, tokens, or credentials are included. A full pre-release content backup was also taken outside the repository. Backups and runtime JSON are not committed to Git.

## Contracts
- `success` includes zero changes. `partial`/`error` retain the last successful timestamp and retry after one hour. Reports distinguish additions, updates, unchanged items and failed sources. A successful source does not prevent retrying another failed source.
- Manual content is protected. Stable source identities update generated content while retaining existing database/game IDs and therefore seen-history references. Known obsolete or ambiguous generated Huroof facts are marked inactive, not deleted, only when their full source returned safely. Legacy content outside known templates remains for the separate content review.
- Country questions group all relation values and exclude multi-valued questions instead of selecting the first response row. Old bank IDs are retained for matching questions; newly created IDs derive from the source entity/relation.
- Huroof extends country/element/curated sources with ISO-language facts. The experimental book source is **off by default** (`HUROOF_BOOK_IMPORT=0`) because its public query did not complete reliably in live checks. Facts remain finite; an unchanged source can legitimately add zero. Unreviewed live Gemini questions are no longer served directly to players.
- Spelling aliases are deterministic reviewed alternatives, not arbitrary letter substitutions/deletions.
- Career has separate refresh/discovery cursors. Refresh defaults to one existing-player batch per day (`CAREER_REFRESH_INTERVAL_DAYS=1`, batch defaults to 150); discovery defaults to seven days. Existing IDs, disabled flags and known logos are retained. Missing article-length responses preserve an existing difficulty instead of turning it into `hard`. Difficulty remains a heuristic, not a factual fame ranking. Incomplete entity responses do not replace stored club history. Recorded death/retirement takes precedence over an unfinished club claim. Background imports do not run schema ALTER statements; a queued ALTER was observed blocking behind a content read transaction during live verification. Initial read transactions are released before network work.
- Whoami uses stable Wikidata person IDs, paginates entity selection before joining nationalities, preserves existing character IDs, and refreshes known people. Missing death data does not assert life. Identity/name collisions and manual content are protected. Source labels and incomplete Wikidata claims still require editorial review.
- Knowledge templates are all refreshed, including previously new-only templates. Lists are paginated to completion or rejected as incomplete. A complete nonempty list below the game minimum (15 answers) is recorded as ineligible, not misreported as a transient network failure or retried hourly. Manual answers/aliases remain separate from the refreshed automatic list; initial legacy answers without provenance are preserved for review.
- File-backed game caches check file modification stamps; other workers can see new JSON without a restart. Huroof keeps its existing bounded database cache TTL.

## Validation
Run `python -m unittest discover -s tests -v` from Backend. Tests use real transformation code and isolated fake game-data sessions; they do not load .env or connect to production. The GitHub deployment workflow runs them before Azure deployment.

Public Wikidata integration checks are distinct from regression tests: country and ISO-language queries returned useful data, while some heavy queries timed out. Source availability and external factual correctness cannot be guaranteed by unit tests.

## Separate content review
`python scripts/audit_game_content.py --backup-dir PATH --output report.json` scans game-content backup files only and produces review flags. It does not connect to a database, edit questions or delete rows. Historical duplicate IDs, aliases, factual correctness, manual records and player curation are reviewed in the next phase; the detailed Career design session is deferred as requested.
