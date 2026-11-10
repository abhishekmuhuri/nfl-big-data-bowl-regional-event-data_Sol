# Methods and interpretation

## Question and audience

Route Relay asks which receiving combinations sustain complementary separation windows, and when an offense has no separated route runner. The audience is an offensive coach or analyst selecting plays for film review and practice experiments. The project focuses on WRs, TEs, and RBs; all players tagged `Pass Route`, including FBs and unusual positional assignments, enter the option count to avoid falsely crediting someone as the only option.

## Data and provenance

The supplied dataset contains 122 games, 8,557 plays, 1,679 players, and 8,314,178 tracking observations from Weeks 1-8 of the 2021 NFL season. Tracking is supplied by NFL Next Gen Stats and scouting by Pro Football Focus. The original variable documentation is preserved in [data/README.md](../data/README.md), and the source repository is [ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data](https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data).

Every source CSV is included unchanged in `data/`; generated cache files are excluded from Git. New data must use the same schema and units or be converted upstream. Public availability does not imply a separate license grant; retain the providers' attribution and apply their terms when reusing the data.

## Joins and geometry

Games join on `gameId`, plays on `gameId, playId`, players on `nflId`, and scouting on `gameId, playId, nflId`. Supporting keys must be unique and references must resolve. Tracking entities are unique on game, play, frame, and player identifier, with missing `nflId` reserved for the football.

Left-moving plays rotate 180 degrees: `x_normalized = 120 - x`, `y_normalized = 160/3 - y`. Right-moving plays retain their coordinates. The same rotation applies to every entity, so distances are unchanged. Absolute line-of-scrimmage coordinates transform with direction; when absent, team side and yardline may supply the line, otherwise beyond-sticks metrics remain unavailable. The first-down line is capped at the opponent's goal line.

## Observation window

Use `ball_snap`, or `autoevent_ballsnap` when the primary tag is absent. A snap is never assumed to occur at a fixed frame. Stop before the first observed `pass_forward`, `qb_sack`, `qb_strip_sack`, or `run`; use `autoevent_passforward` only when no primary terminal tag exists. If no terminal tag exists, stop at the last available frame and mark the clip as censored.

Frame identifiers supply elapsed time: `(frameId - snap_frame) / fps`. The supplied data uses 10 Hz; whole-second timestamps are insufficient for temporal calculations and occasionally disagree across entities. Each observed frame represents a `1/fps` exposure bin. Thus three consecutive bins at 10 Hz are defined as 0.3 seconds, even though the first and last sample timestamps are 0.2 seconds apart.

The default analysis interval is 0.5 to 3.5 seconds after snap, bounded by actual tracking and the terminal event. The end is exclusive. Two-point attempts (`down == 0`) are excluded by default. Penalty-affected plays remain and recorded outcomes are not treated as official NFL passing statistics.

Frames must contain all 22 expected participants and the ball, with finite coordinates. Invalid frames do not contribute exposure and break sustained windows. The observed player roster must match scouting. Off-field coordinates are reported rather than silently clipped. An off-field route runner cannot supply a qualifying window, while the frame and the other receivers remain measurable.

## Separation rule and metrics

For receiver `r` at frame `t`, separation is the Euclidean distance to the nearest of all 11 opposing players. A sustained window is a contiguous run above the distance threshold whose bin count reaches `ceil(minimum_seconds * fps)`. Qualification is retrospective: the whole observed run is marked as a window once its duration qualifies. It is not an online prediction.

Let `N(t)` count route runners with a qualifying window, and let `dt = 1/fps`.

| Metric | Definition |
| --- | --- |
| Option coverage | `sum(dt where N(t) >= 1) / sum(valid observed dt)` |
| Longest gap | Longest contiguous observed run with `N(t) == 0` |
| Receiver unique contribution | `sum(dt where receiver qualifies and N(t) == 1)` |
| Mean receiver window duration | Total qualifying receiver seconds divided by qualifying window count |
| Beyond-sticks coverage | Time with a separated receiver at/beyond the first-down line divided by observed time with a known line |

Aggregate coverage uses matching exposure totals, not an unweighted average of play percentages. The headline gap is the median of per-play longest gaps. Single-option time is the sum of receiver unique seconds divided by observed play seconds. Overlap between options is useful and receives no penalty.

Player summaries include observed route and game counts. Unique contribution depends on teammate availability, route depth, deployment, and coverage; it is not a stand-alone receiver quality score. Situation groups below the configurable sample threshold are flagged rather than hidden or presented as reliable rankings.

The optional uncertainty interval resamples entire games with replacement 400 times using seed 2021 and recomputes the exposure-weighted coverage ratio. At least three games are required. It is a descriptive game-cluster bootstrap, not a causal interval. Later exposure-chart points describe the subset of plays still observed at that time, and should not be interpreted as a fixed-cohort trajectory.

## Findings and limits

The reproducible default KC comparison, its settings, and its evidence are stored in [findings.json](findings.json), [play metrics](demo_play_metrics.csv), and [receiver metrics](demo_receiver_metrics.csv). In this cohort, separation somewhere on the field is much more common than separation beyond the first-down line, while TE/RB windows sometimes supply the only spatial option.

The model does not infer intended routes, progressions, targets, defender assignments, receiver leverage, ball flight, passing-lane obstruction, quarterback visibility, catch probability, or safety of a throw. No counterfactual claim is made that moving a route will cause a better outcome. The tool identifies patterns for football review; a team should combine them with film, playbook context, and practice evaluation.

The brief's focus on a useful skill-position insight, Python code, clear visual output, reproducibility, assumptions, and limitations is reflected in the dashboard, standalone demonstration, tests, and root README. This repository does not establish compliance with event attendance or on-site timing rules.
