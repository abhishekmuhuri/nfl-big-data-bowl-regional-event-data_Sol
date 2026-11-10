# Add games and connect a feed

The dashboard does not hardcode the 2021 teams, players, game identifiers, or week range. The included data is a working example of the ingestion contract. Feed a new season using the same schema, with globally consistent identifiers and units; select the correct sampling rate for that feed.

## Folder contract

```text
data/
  games.csv
  plays.csv
  players.csv
  pffScoutingData.csv
  tracking/
    tracking_<gameId>.csv
```

The [original dictionary](../data/README.md) describes all supplied columns. The minimum supported fields are:

| Table | Required fields | Unique key |
| --- | --- | --- |
| games | gameId, season, week, homeTeamAbbr, visitorTeamAbbr | gameId |
| plays | gameId, playId, possessionTeam, defensiveTeam, down, yardsToGo, passResult | gameId, playId |
| players | nflId, displayName, officialPosition | nflId |
| pffScoutingData | gameId, playId, nflId, pff_role | gameId, playId, nflId |
| tracking | gameId, playId, nflId, frameId, team, playDirection, x, y, event | gameId, playId, frameId, entity |

Each play needs 22 scouting participants. Receiver roles use `Pass Route`; matching is case-insensitive. Tracking files contain one game each, with 11 players per team and a football row at every complete frame. The ball has `team=football` and no `nflId`. Player identifiers are integers and all supporting references must resolve.

Supply `absoluteYardlineNumber`, or `yardlineNumber` and `yardlineSide`, for beyond-sticks analysis. Coverage, formation, descriptions, dates, and play results enable richer filters but are not required for basic separation calculations. Coordinates are yards on a nominal 120 by 53 1/3 yard field. Convert other formats or metric units before ingestion.

## Option A: upload files in the dashboard

Open **Data & help**, select CSVs or a ZIP, and click **Import files and refresh**. A ZIP may contain a top-level project folder; supported CSV names are discovered within it. Other files are ignored, unsafe paths are rejected, and unpacked content is limited to 2 GB. The browser upload limit is 1,000 MB per file.

Supporting rows are upserted by their unique keys. Tracking rows are upserted by game/play/frame/entity. Incoming duplicate keys are rejected; an incoming row with the same key as an existing row intentionally updates it. Include the supporting rows for new games, plays, and players. Existing rows omitted from an import are retained.

The importer validates the batch in a staging folder before publishing files. A shared dataset lock prevents processing while the import publishes its files. File replacement is atomic per file; the import is not a crash-recoverable multi-file database transaction, so retain source batches and rerun a batch after an interrupted publication.

## Option B: import CSVs from a script

Use the canonical supporting filenames (`games.csv`, `plays.csv`, etc.) when supplying actual files:

```sh
python import_data.py incoming/games.csv incoming/plays.csv incoming/players.csv incoming/pffScoutingData.csv incoming/tracking_2026091000.csv
python process_data.py
```

Or import a dataset ZIP:

```sh
python import_data.py incoming/new_games.zip
python process_data.py
```

Use `--data-dir path/to/dataset` to import into a different dataset. Set the dashboard's **Dataset folder** to the same path. A complete new folder needs all four supporting CSVs.

## Option C: pipe a finite JSON batch

Each input line is a JSON object with a `table` and a `rows` array. Supported tables are `games`, `plays`, `players`, `pffScoutingData`, and `tracking`.

```json
{"table":"players","rows":[{"nflId":999999,"displayName":"Example Player","officialPosition":"WR"}]}
```

That example demonstrates the envelope; a new game also needs game, play, 22-player scouting, and tracking rows. The importer commits one finite batch on end-of-input. Tracking batches containing multiple games are partitioned into per-game CSVs.

Windows PowerShell:

```powershell
Get-Content incoming/batch.ndjson | python import_data.py --stdin
python process_data.py
```

macOS/Linux:

```sh
cat incoming/batch.ndjson | python import_data.py --stdin
python process_data.py
```

## Option D: watch a folder for completed deliveries

```sh
python process_data.py --watch --interval 10
```

Write completed files with a temporary extension, then rename them into place. Update supporting metadata before delivering tracking, or use the importer to stage the batch together. The watcher processes changes, and the dashboard sees the updated cache on its next interaction or refresh. It is a completed-batch pipeline, not a low-latency live-play service: sustained windows and terminal events are analyzed retrospectively.

## Incremental behavior

The cache is namespaced by dataset path. Each manifest records pipeline version, sampling rate, supporting-table signatures, and each source file's size plus SHA-256 content identity. Unchanged files are reused even when a Git checkout or deployment changes timestamps; changed tracking files are rebuilt. Changes to supporting tables or sampling rate invalidate affected cached interpretation, conservatively rebuilding all games.

Rejected files are listed in the manifest and their old cached results are not reused. Processing quality records explain exclusions and partial observations. Content hashes are memoized by path, size, and modification time within a running process; use `python process_data.py --force` if an external delivery mechanism can replace bytes while preserving both size and timestamp.

Environment variables `ROUTE_RELAY_DATA_DIR` and `ROUTE_RELAY_CACHE_DIR` set default locations. Both processing and the dashboard need write access to the cache and dataset lock location. Cached data is derived and can be regenerated; source CSVs are authoritative.

## Regenerate the hosted demonstration

```sh
python export_report.py --team KC --coverage Cover-1 Cover-3
```

For another dataset, add `--data-dir path/to/dataset --team TEAM --fps 10`. Update the root README's findings if publishing a different cohort, commit the generated files under `docs/`, and push. GitHub Pages will publish the new snapshot; the Python dashboard remains the interface for arbitrary live filters and imports.
