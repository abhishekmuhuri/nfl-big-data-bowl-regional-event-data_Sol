# Validation performed

The implementation was checked on Python 3.12 using the pinned runtime requirements in `requirements.txt`.

- **21 unit and pipeline tests passed.** These cover hand-calculated receiving windows, complementary options, left/right coordinate equivalence, threshold changes, missing snap tags, fallback snap tags, terminal-event exclusion, missing entities and entire missing frames, off-field eligibility, unknown first-down lines, duplicate keys, schema failures, incremental reuse and invalidation, content-stable cache identity across timestamp changes, rejected-import isolation, ZIP traversal rejection, filename/game agreement, and a new game supplied as JSON batches.
- **All 122 tracking CSVs processed without file-level errors.** There are 8,533 measured-capable plays and 24 plays excluded because neither snap tag is available; exclusions are surfaced rather than assigned a guessed snap time.
- **All 126 source CSVs were compared byte-for-byte by SHA-256** against the supplied original folder: 873,626,827 bytes matched. The bundled file inventory is in [SOURCE_MANIFEST.json](../data/SOURCE_MANIFEST.json).
- **Streamlit AppTest exercised real-data controls:** initial rendering, a separation-threshold change from 2 to 3 yards, a team change from KC to TB, and empty-week filters. The dashboard handled each without an application exception.
- **A separate headless browser checked the application:** team overview, receiver timeline and animated replay, data/import view, and a 390-pixel mobile viewport. It also rendered the standalone HTML demonstration; no browser JavaScript errors were observed.
- **The one-command launcher was smoke-tested**, including dependency installation checks and starting the local dashboard server. `pip check` reported no broken requirements.

The default reproduction consists of 137 KC plays against Cover-1/Cover-3 in eight games, using 0.5-3.5 seconds after snap, a 2-yard distance threshold, and 0.3-second sustained windows. The exact findings and settings are in [findings.json](findings.json), with play and receiver CSV evidence next to it.

This is software and data consistency validation, not a comparison of every tracking measurement against film. Coaching interpretations remain descriptive and require football context. The GitHub workflow reruns the unit/pipeline suite on Linux for subsequent pushes and pull requests.
