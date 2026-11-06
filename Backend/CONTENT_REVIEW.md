# Content review — 6 November 2026

Scope: game questions, answer lists, character profiles and player records only. No accounts, personal data, purchases, match history or balances were queried or changed. Existing record IDs remain stable. Quarantine uses `active: false`; records are not deleted.

The review plan and full old/new values are retained beside timestamped production content backups. `CONTENT_REVIEW_2026-11-06.json` records the evidence scope and limitations. The original snapshot contains 1,101 Huroof records, 307 players, 711 Bank questions, 101 Who Am I profiles and 15 Knowledge lists.

Key corrections:
- Bank: false/ambiguous premises narrowed; 25 automatic copies of manual facts quarantined, plus the second manual Australia-capital question. The single-continent question about the whole Danish realm is held.
- Knowledge: rebuilt answer groups by country identity, approved atomic number, current ISO currency code and date-scoped league membership. EPL and LaLiga lists contain clubs rather than people. Aliases for different fruits/animals were separated. The complete 12-country South America list remains below the engine's 15-answer minimum.
- Who Am I: person identities reconciled, duplicate biographies held, selected unsupported or dated clues replaced. Uncertain ancient dates and unsuitable/disputed profiles are held rather than fabricated.
- Career: corrupted Arabic labels corrected against official club profiles; generic first-name aliases removed. Incomplete eras no longer presented as complete periods. Non-football fame candidates and three unresolved club histories are held. The generic Wikidata work-period end property P2032 is not treated as a football retirement announcement. Future club membership is not a completed career stop.

Reviewed Knowledge lists have `_curation.hold_import = true`: the old unrestricted merge must not silently reintroduce removed answers. This is an explicit review hold, not a claim of automatic daily verification. Source status exposes `held_sources`. Other importer refresh lanes remain enabled. The two official player-name corrections and reviewed retirement override live in `data/career_review_overrides.json` and take priority over external labels.

Evidence includes current Wikidata snapshots; UN M49 and membership identities; SIX ISO 4217 List One published 2026-09-17; IUPAC and NIH PubChem; official EPL documentation; and the RSSSF historical Spanish league table. A Wikidata round trip is not independent primary-source proof. It cannot guarantee complete recent transfers for all 307 players or every surviving hand-written anecdote. These limitations must stay visible; the review is not a 100% factual certification.

`python scripts/apply_game_content_review.py PLAN.json` previews. `--apply` obtains importer locks, verifies unchanged old values, takes a second content backup, updates only allowlisted game tables/files and retains IDs. Stale snapshots and duplicate answer aliases fail closed. Applying requires DATABASE_URL supplied by the deployment environment, not a checked-in credential.

Verification: isolated importer/reader tests plus content-plan precondition tests. Live content and pool checks are performed separately after application; unit tests alone do not establish normal gameplay quality.

A subsequent, separate fame review is documented in [CAREER_FAME_REVIEW.md](CAREER_FAME_REVIEW.md); it supersedes the earlier article-length classification, not the factual content quarantine.
