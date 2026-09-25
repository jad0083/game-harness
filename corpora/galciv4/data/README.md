# Generated game data

Files in this directory are **generated** from the game's own definition files by
`scripts/extract-galciv4.py` and must never be edited by hand. Regenerate after every game patch.

Contract:

- `<kind>.json` — a JSON array of records for one entity kind (`tech`, `improvement`, `order`,
  `ship`, `planet`, …). The file stem is the kind.
- `_meta.json` — `{ "game_version": "...", "generated_at": "...", "generator": "<commit>" }`.
  Files starting with `_` are not loaded as records.

Record shape (extra keys go under `fields`; the extractor decides which fields each kind has):

```json
{
  "id": "tech:colonial_policies",        // optional; defaults to "<kind>:<slug of name>"
  "name": "Colonial Policies",           // required
  "aliases": ["col policies"],           // optional, matched like the name
  "summary": "Adds a policy slot.",      // optional one-liner shown in search results
  "fields": {                            // optional, rendered in order by corpus_get
    "tree": "Colonization",
    "cost": 27,
    "prerequisites": ["Planetary Improvements"],
    "unlocks": ["Supply Ship", "Minister of Colonization"]
  }
}
```

The loader rejects a record without a `name` and any duplicate `id`, so a bad extract fails at
startup rather than during a game turn.

Source data on the Windows PC (see ARCHITECTURE.md): `<install>/Data/Gameplay/*.xml` for
definitions and `<install>/Data/English/Text/*.xml` for display strings.
