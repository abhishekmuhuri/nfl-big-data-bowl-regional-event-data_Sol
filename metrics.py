"""Transparent retrospective separation metrics; no target or QB-read inference."""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MetricConfig:
    separation_yards: float = 2.0
    minimum_window_seconds: float = 0.3
    start_seconds: float = 0.5
    end_seconds: float = 3.5
    fps: float = 10.0

    def __post_init__(self):
        if not all(math.isfinite(v) for v in self.__dict__.values()):
            raise ValueError('Metric settings must be finite numbers.')
        if self.fps <= 0 or self.separation_yards <= 0 or self.minimum_window_seconds <= 0:
            raise ValueError('Frame rate, separation, and minimum duration must be positive.')
        if self.start_seconds < 0 or self.end_seconds <= self.start_seconds:
            raise ValueError('End time must be greater than start time, which cannot be negative.')


def true_runs(mask, frames):
    """Inclusive array bounds for true runs; absent frames always split a run."""
    mask = np.asarray(mask, dtype=bool)
    frames = np.asarray(frames)
    if len(mask) == 0:
        return []
    starts = np.flatnonzero(mask & np.r_[True, (~mask[:-1]) | (np.diff(frames) != 1)])
    ends = np.flatnonzero(mask & np.r_[(~mask[1:]) | (np.diff(frames) != 1), True])
    return list(zip(starts, ends)) if len(mask) else []


def sustained_mask(mask, frames, minimum_frames):
    result = np.zeros(len(mask), dtype=bool)
    for start, end in true_runs(mask, frames):
        if end - start + 1 >= minimum_frames:
            result[start:end + 1] = True
    return result


def longest_run(mask, frames, fps):
    return max((b - a + 1 for a, b in true_runs(mask, frames)), default=0) / fps


def spacing_candidate(rows, threshold):
    """An off-field route runner never supplies an eligible spatial option."""
    return rows.separation.ge(threshold) & rows.x.between(0,120) & rows.y.between(0,160/3)


def evaluate(features, config=MetricConfig()):
    """Return play, player/play and frame metrics, using observed exposure only.

    Each sample represents one 1/fps exposure bin. A 3-bin run at 10 Hz is
    defined as a 0.3-second window. Window qualification is retrospective.
    """
    if features.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    data = features.loc[features.elapsed.ge(config.start_seconds - 1e-7)
                        & features.elapsed.lt(config.end_seconds - 1e-7)].copy()
    data['candidate'] = spacing_candidate(data,config.separation_yards)
    required = max(1, math.ceil(config.minimum_window_seconds * config.fps - 1e-8))
    plays, people, frames_out = [], [], []
    for (game, play), f in data.groupby(['gameId', 'playId'], sort=False):
        frame_ids = np.sort(f.frameId.unique())
        ids = np.sort(f.nflId.unique())
        distances = f.pivot(index='frameId', columns='nflId', values='separation').reindex(index=frame_ids, columns=ids)
        candidates = f.pivot(index='frameId', columns='nflId', values='candidate').reindex(index=frame_ids, columns=ids)
        usable = np.isfinite(distances.to_numpy()).all(axis=1)
        matrix = np.zeros(distances.shape, dtype=bool)
        for j in range(len(ids)):
            raw = usable & candidates.iloc[:, j].fillna(False).to_numpy(dtype=bool)
            matrix[:, j] = sustained_mask(raw, frame_ids, required)
        counts = matrix.sum(axis=1)
        seconds = int(usable.sum()) / config.fps
        if seconds == 0:
            continue
        first = f.iloc[0]
        times = (frame_ids - int(first.snap_frame)) / config.fps
        beyond = f.pivot(index='frameId', columns='nflId', values='beyond_sticks').reindex(index=frame_ids, columns=ids).to_numpy(dtype=float)
        line_known = np.isfinite(beyond).all(axis=1) & usable
        beyond_open = (matrix & (np.nan_to_num(beyond) == 1)).any(axis=1)
        open_seconds = int((usable & (counts > 0)).sum()) / config.fps
        row = {'gameId': int(game), 'playId': int(play), 'observed_seconds': seconds,
               'option_seconds': open_seconds, 'option_coverage': open_seconds / seconds,
               'longest_gap': longest_run(usable & (counts == 0), frame_ids, config.fps),
               'beyond_seconds': int((beyond_open & line_known).sum()) / config.fps if line_known.any() else np.nan,
               'line_known_seconds': int(line_known.sum()) / config.fps,
               'observed_start': float(times[usable].min()), 'observed_end': float(times[usable].max() + 1 / config.fps),
               'routes': len(ids)}
        plays.append(row)
        for j, nfl_id in enumerate(ids):
            who = f.loc[f.nflId.eq(nfl_id)].iloc[0]
            windows = true_runs(matrix[:, j], frame_ids)
            open_time = int(matrix[:, j].sum()) / config.fps
            people.append({'gameId': int(game), 'playId': int(play), 'nflId': int(nfl_id),
                           'displayName': who.displayName, 'officialPosition': who.officialPosition,
                           'observed_seconds': seconds, 'open_seconds': open_time,
                           'unique_seconds': int((matrix[:, j] & (counts == 1)).sum()) / config.fps,
                           'windows': len(windows), 'mean_window': open_time / len(windows) if windows else 0.0,
                           'first_window': float(times[windows[0][0]]) if windows else np.nan})
        for i, frame in enumerate(frame_ids):
            if usable[i]:
                frames_out.append({'gameId': int(game), 'playId': int(play), 'frameId': int(frame),
                                   'elapsed': round(float(times[i]), 4), 'options': int(counts[i]),
                                   'open_ids': ','.join(str(int(ids[j])) for j in np.flatnonzero(matrix[i])),
                                   'beyond_option': bool(beyond_open[i]) if line_known[i] else None})
    return pd.DataFrame(plays), pd.DataFrame(people), pd.DataFrame(frames_out)


def player_summary(player_plays):
    if player_plays.empty:
        return pd.DataFrame()
    grouped = player_plays.groupby(['nflId', 'displayName', 'officialPosition'], as_index=False).agg(
        routes=('playId', 'size'), games=('gameId', 'nunique'), observed_seconds=('observed_seconds', 'sum'),
        open_seconds=('open_seconds', 'sum'), unique_seconds=('unique_seconds', 'sum'), windows=('windows', 'sum'))
    grouped['separated_pct'] = 100 * grouped.open_seconds / grouped.observed_seconds
    grouped['unique_seconds_per_route'] = grouped.unique_seconds / grouped.routes
    grouped['mean_window_seconds'] = grouped.open_seconds / grouped.windows.replace(0, np.nan)
    return grouped.sort_values('unique_seconds_per_route', ascending=False)


def cohort_summary(play_metrics, metadata, by, minimum_plays=10):
    if play_metrics.empty:
        return pd.DataFrame()
    joined = play_metrics.merge(metadata, on=['gameId', 'playId'], validate='one_to_one')
    out = joined.groupby(by, dropna=False).agg(plays=('playId', 'size'), games=('gameId', 'nunique'),
        observed_seconds=('observed_seconds', 'sum'), option_seconds=('option_seconds', 'sum'),
        median_gap=('longest_gap', 'median'), beyond_seconds=('beyond_seconds', lambda s: s.sum(min_count=1)),
        line_known_seconds=('line_known_seconds', 'sum')).reset_index()
    out['option_coverage_pct'] = 100 * out.option_seconds / out.observed_seconds
    out['beyond_coverage_pct'] = 100 * out.beyond_seconds / out.line_known_seconds.replace(0, np.nan)
    out['small_sample'] = out.plays < minimum_plays
    return out.sort_values('plays', ascending=False)


def game_bootstrap_interval(play_metrics, repeats=400, seed=2021):
    """Descriptive 95% game-cluster bootstrap interval for exposure-weighted coverage."""
    totals = play_metrics.groupby('gameId')[['option_seconds', 'observed_seconds']].sum().to_numpy()
    if len(totals) < 3:
        return None
    rng = np.random.default_rng(seed)
    draws = totals[rng.integers(0, len(totals), size=(repeats, len(totals)))].sum(axis=1)
    estimates = draws[:, 0] / draws[:, 1]
    return tuple(float(x) for x in np.percentile(estimates, [2.5, 97.5]))
