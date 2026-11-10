"""Validated, incremental processing of NFL-format CSV datasets."""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = Path(os.environ.get('ROUTE_RELAY_DATA_DIR', ROOT / 'data'))
DEFAULT_CACHE = Path(os.environ.get('ROUTE_RELAY_CACHE_DIR', ROOT / 'cache'))
VERSION = 'route-relay-1.0'
FIELD_WIDTH = 160 / 3
TABLES = {
    'games': (['gameId'], ['gameId', 'season', 'week', 'homeTeamAbbr', 'visitorTeamAbbr']),
    'plays': (['gameId', 'playId'], ['gameId', 'playId', 'possessionTeam', 'defensiveTeam', 'down', 'yardsToGo', 'passResult']),
    'players': (['nflId'], ['nflId', 'displayName', 'officialPosition']),
    'pffScoutingData': (['gameId', 'playId', 'nflId'], ['gameId', 'playId', 'nflId', 'pff_role']),
}
TRACKING_COLUMNS = ['gameId', 'playId', 'nflId', 'frameId', 'team', 'playDirection', 'x', 'y', 'event']
FEATURE_COLUMNS = ['gameId','playId','frameId','nflId','snap_frame','elapsed','x','y','separation',
                   'beyond_sticks','displayName','officialPosition','team']


class DataError(ValueError):
    pass


@contextmanager
def dataset_lock(data_dir):
    path = Path(data_dir) / '.route-relay.lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise DataError('Another import or rebuild is running. Try again when it finishes.') from None
    try:
        os.write(fd, f'{os.getpid()} {time.time()}'.encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def validate_table(name, df):
    key, required = TABLES[name]
    missing = set(required) - set(df.columns)
    if missing:
        raise DataError(f'{name}.csv is missing columns: {", ".join(sorted(missing))}')
    if df.empty:
        raise DataError(f'{name}.csv contains no rows.')
    for col in key:
        numeric = pd.to_numeric(df[col], errors='coerce')
        if numeric.isna().any() or not np.isfinite(numeric).all() or (numeric % 1 != 0).any():
            raise DataError(f'{name}.{col} must contain non-missing integer identifiers.')
        df[col] = numeric.astype('int64')
    if df.duplicated(key).any():
        raise DataError(f'{name}.csv has duplicate keys: {", ".join(key)}')
    for col in set(required) - set(key):
        if df[col].isna().any():
            raise DataError(f'{name}.{col} contains missing required values.')
    return df


def load_metadata(data_dir=DEFAULT_DATA):
    data_dir = Path(data_dir)
    result = {}
    for name in TABLES:
        path = data_dir / f'{name}.csv'
        if not path.exists():
            raise DataError(f'Missing {path.name}. Select a complete dataset folder or import all four supporting CSVs.')
        try:
            result[name] = validate_table(name, pd.read_csv(path))
        except (pd.errors.ParserError, UnicodeError) as exc:
            raise DataError(f'Cannot read {path.name}: {exc}') from exc
    g, p, players, sc = [result[n] for n in TABLES]
    if not p.gameId.isin(g.gameId).all():
        raise DataError('plays.csv refers to games absent from games.csv.')
    if not sc.nflId.isin(players.nflId).all():
        raise DataError('Scouting refers to players absent from players.csv.')
    pairs = pd.MultiIndex.from_frame(p[['gameId', 'playId']])
    if not pd.MultiIndex.from_frame(sc[['gameId', 'playId']]).isin(pairs).all():
        raise DataError('Scouting refers to plays absent from plays.csv.')
    for col, default in [('pff_passCoverage','Unknown'), ('pff_passCoverageType','Unknown'),
                         ('offenseFormation','Unknown'), ('playDescription',''), ('absoluteYardlineNumber',np.nan),
                         ('yardlineNumber',np.nan), ('yardlineSide',None), ('playResult',np.nan)]:
        if col not in p:
            p[col] = default
    p['down'] = pd.to_numeric(p.down, errors='coerce')
    p['yardsToGo'] = pd.to_numeric(p.yardsToGo, errors='coerce')
    if p[['down', 'yardsToGo']].isna().any().any() or not p.down.isin([0,1,2,3,4]).all() or p.yardsToGo.lt(0).any():
        raise DataError('Plays require down 0-4 and a nonnegative yardsToGo.')
    return result


def validate_tracking(df, source='tracking CSV'):
    missing = set(TRACKING_COLUMNS) - set(df.columns)
    if missing:
        raise DataError(f'{source} is missing columns: {", ".join(sorted(missing))}')
    if df.empty:
        raise DataError(f'{source} contains no observations.')
    for col in ['gameId', 'playId', 'frameId']:
        s = pd.to_numeric(df[col], errors='coerce')
        if s.isna().any() or not np.isfinite(s).all() or (s % 1 != 0).any():
            raise DataError(f'{source}: {col} must contain integer identifiers.')
        df[col] = s.astype('int64')
    if df.frameId.lt(1).any():
        raise DataError(f'{source}: frameId must start at 1 or greater.')
    if df.gameId.nunique() != 1:
        raise DataError(f'{source}: use one tracking CSV per game.')
    df['nflId'] = pd.to_numeric(df.nflId, errors='coerce')
    ball = df.team.eq('football')
    if df.team.isna().any() or df.loc[~ball, 'nflId'].isna().any() or df.loc[ball, 'nflId'].notna().any():
        raise DataError(f'{source}: player rows require nflId; ball rows require team=football and empty nflId.')
    if (df.nflId.dropna() % 1 != 0).any() or not np.isfinite(df.nflId.dropna()).all():
        raise DataError(f'{source}: nflId must contain integer player identifiers.')
    if df.duplicated(['gameId','playId','frameId','nflId']).any():
        raise DataError(f'{source}: duplicate entity/frame observations.')
    if not df.playDirection.isin(['left','right']).all():
        raise DataError(f'{source}: playDirection must be left or right.')
    for col in ['x','y']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def normalized_line(play, direction):
    absolute = pd.to_numeric(play.get('absoluteYardlineNumber'), errors='coerce')
    if pd.notna(absolute):
        return float(absolute if direction == 'right' else 120 - absolute), 'absoluteYardlineNumber'
    yard = pd.to_numeric(play.get('yardlineNumber'), errors='coerce')
    if pd.notna(yard) and yard == 50:
        return 60.0, 'midfield'
    side = play.get('yardlineSide')
    if pd.notna(yard) and pd.notna(side):
        return float(10 + yard if side == play.possessionTeam else 110 - yard), 'yardlineSide'
    return np.nan, 'missing'


def process_game(df, metadata, fps=10.0):
    df = validate_tracking(df)
    game_id = int(df.gameId.iloc[0])
    if game_id not in set(metadata['games'].gameId):
        raise DataError(f'Tracking game {game_id} is absent from games.csv.')
    play_lookup = metadata['plays'].set_index(['gameId','playId'])
    scouting = metadata['pffScoutingData']
    scout_groups = {k: v for k,v in scouting.loc[scouting.gameId.eq(game_id)].groupby('playId')}
    players = metadata['players'].set_index('nflId')
    output, quality = [], []
    for play_id, play_tracking in df.groupby('playId', sort=False):
        info = {'gameId': game_id, 'playId': int(play_id), 'status': 'excluded', 'reason': '',
                'snap_source': '', 'terminal_event': '', 'censored': True, 'invalid_frames': 0,
                'observed_frames': 0, 'out_of_bounds_player_rows': 0}
        try:
            if (game_id, play_id) not in play_lookup.index or play_id not in scout_groups:
                raise DataError('Missing play metadata or scouting.')
            play = play_lookup.loc[(game_id, play_id)]
            sc = scout_groups[play_id]
            if len(sc) != 22:
                raise DataError('Scouting must identify exactly 22 participants.')
            route_ids = sc.loc[sc.pff_role.str.casefold().eq('pass route'), 'nflId'].to_numpy(dtype=int)
            if len(route_ids) == 0:
                raise DataError('No Pass Route participants.')
            events = play_tracking[['frameId','event']].drop_duplicates()
            snap = events.loc[events.event.eq('ball_snap'), 'frameId']
            info['snap_source'] = 'ball_snap'
            if snap.empty:
                snap = events.loc[events.event.eq('autoevent_ballsnap'), 'frameId']
                info['snap_source'] = 'autoevent_ballsnap'
            if snap.empty:
                raise DataError('No observed snap tag; snap time is not assumed.')
            snap_frame = int(snap.min())
            terminal = events.loc[events.frameId.ge(snap_frame) & events.event.isin(
                ['pass_forward','qb_sack','qb_strip_sack','run'])].sort_values('frameId')
            if terminal.empty:
                terminal = events.loc[events.frameId.ge(snap_frame) & events.event.eq('autoevent_passforward')].sort_values('frameId')
            if terminal.empty:
                end = int(play_tracking.frameId.max()) + 1
                info['terminal_event'] = 'tracking cutoff'
            else:
                end = int(terminal.frameId.iloc[0])
                info['terminal_event'] = str(terminal.event.iloc[0])
                info['censored'] = False
            info['snap_frame'] = snap_frame
            info['end_frame_exclusive'] = end
            t = play_tracking.loc[play_tracking.frameId.ge(snap_frame) & play_tracking.frameId.lt(end)].copy()
            if t.empty:
                raise DataError('No observations between snap and terminal event.')
            if t.playDirection.nunique() != 1:
                raise DataError('Inconsistent playDirection within a play.')
            direction = t.playDirection.iloc[0]
            t['x'] = np.where(direction == 'left', 120 - t.x, t.x)
            t['y'] = np.where(direction == 'left', FIELD_WIDTH - t.y, t.y)
            ball = t.team.eq('football')
            offense = t.team.eq(play.possessionTeam)
            defense = t.team.eq(play.defensiveTeam)
            if (~(ball | offense | defense)).any():
                raise DataError('Tracking team does not match the play teams.')
            opponent_ids = np.sort(t.loc[defense,'nflId'].unique()).astype(int)
            offense_ids = np.sort(t.loc[offense,'nflId'].unique()).astype(int)
            if len(opponent_ids) != 11 or len(offense_ids) != 11 or not set(route_ids).issubset(offense_ids):
                raise DataError('Expected 11 players per team and offensive route runners.')
            if set(np.r_[opponent_ids,offense_ids]) != set(sc.nflId):
                raise DataError('Scouting participants and tracking participants differ.')
            t['finite'] = np.isfinite(t[['x','y']]).all(axis=1)
            counts = t.groupby('frameId').agg(entities=('team','size'), finite=('finite','all'))
            valid_frames = counts.index[(counts.entities == 23) & counts.finite]
            missing_whole_frames = max(0,end - snap_frame - len(counts))
            info['invalid_frames'] = int(len(counts) - len(valid_frames) + missing_whole_frames)
            if len(valid_frames) == 0:
                raise DataError('No complete finite 23-entity frames.')
            t = t.loc[t.frameId.isin(valid_frames)]
            t_players = t.loc[t.team.ne('football')]
            info['out_of_bounds_player_rows'] = int((~t_players.x.between(0,120) | ~t_players.y.between(0,FIELD_WIDTH)).sum())
            wide = t_players.pivot(index='frameId',columns='nflId',values=['x','y']).reindex(valid_frames)
            if wide.isna().any().any():
                raise DataError('Participant missing in an otherwise complete frame.')
            rxy = np.stack([wide['x'][route_ids].to_numpy(),wide['y'][route_ids].to_numpy()],axis=-1)
            dxy = np.stack([wide['x'][opponent_ids].to_numpy(),wide['y'][opponent_ids].to_numpy()],axis=-1)
            separation = np.sqrt(((rxy[:,:,None,:] - dxy[:,None,:,:]) ** 2).sum(axis=-1)).min(axis=-1)
            los, line_source = normalized_line(play,direction)
            sticks = min(110.0, los + float(play.yardsToGo)) if np.isfinite(los) else np.nan
            info.update(status='partial' if info['invalid_frames'] else 'ok', observed_frames=len(valid_frames),
                        line_of_scrimmage=los, first_down_line=sticks, line_source=line_source)
            for j,nfl_id in enumerate(route_ids):
                who = players.loc[nfl_id]
                output.append(pd.DataFrame({'gameId':game_id,'playId':int(play_id),'frameId':valid_frames.to_numpy(),
                    'nflId':int(nfl_id),'snap_frame':snap_frame,'elapsed':(valid_frames.to_numpy()-snap_frame)/fps,
                    'x':rxy[:,j,0].astype('float32'),'y':rxy[:,j,1].astype('float32'),
                    'separation':separation[:,j].astype('float32'),
                    'beyond_sticks':(rxy[:,j,0] >= sticks).astype(float) if np.isfinite(sticks) else np.nan,
                    'displayName':who.displayName,'officialPosition':who.officialPosition,'team':play.possessionTeam}))
        except (DataError, KeyError) as exc:
            info['reason'] = str(exc)
        quality.append(info)
    features = pd.concat(output, ignore_index=True) if output else pd.DataFrame(columns=FEATURE_COLUMNS)
    return features, pd.DataFrame(quality)


def fingerprint(path):
    stat = Path(path).stat()
    return f'{stat.st_size}:{stat.st_mtime_ns}'


def inventory_signature(data_dir=DEFAULT_DATA):
    data_dir = Path(data_dir)
    files = [data_dir / f'{n}.csv' for n in TABLES] + sorted((data_dir/'tracking').glob('*.csv'))
    return hashlib.sha256('|'.join(f'{p.name}:{fingerprint(p)}' for p in files if p.exists()).encode()).hexdigest()


def cache_home(data_dir=DEFAULT_DATA, cache_dir=DEFAULT_CACHE):
    # Separate caches for separate datasets, even if filenames match.
    return Path(cache_dir) / hashlib.sha256(str(Path(data_dir).resolve()).encode()).hexdigest()[:12]


def read_manifest(data_dir=DEFAULT_DATA, cache_dir=DEFAULT_CACHE):
    path = cache_home(data_dir,cache_dir) / 'manifest.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return {}


def build_dataset(data_dir=DEFAULT_DATA, cache_dir=DEFAULT_CACHE, fps=10.0, force=False, progress=None):
    if not np.isfinite(fps) or fps <= 0:
        raise DataError('Frame rate must be positive.')
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise DataError(f'Dataset folder does not exist: {data_dir}')
    with dataset_lock(data_dir):
        metadata = load_metadata(data_dir)
        files = sorted((data_dir/'tracking').glob('*.csv'))
        if not files:
            raise DataError('No tracking CSVs found in the tracking subfolder.')
        home = cache_home(data_dir,cache_dir)
        home.mkdir(parents=True, exist_ok=True)
        old = read_manifest(data_dir,cache_dir)
        meta_sig = hashlib.sha256('|'.join(fingerprint(data_dir/f'{n}.csv') for n in TABLES).encode()).hexdigest()
        manifest = {'version':VERSION,'fps':fps,'metadata_signature':meta_sig,'source_signature':inventory_signature(data_dir),
                    'built_at':datetime.now(timezone.utc).isoformat(),'files':{},'errors':[], 'rebuilt':0,'reused':0}
        for i,path in enumerate(files):
            sig = fingerprint(path)
            prev = old.get('files',{}).get(path.name,{})
            reusable = (not force and old.get('version') == VERSION and old.get('fps') == fps
                        and old.get('metadata_signature') == meta_sig and prev.get('fingerprint') == sig
                        and all((home/prev.get(k,'missing')).is_file() for k in ['features','quality']))
            if reusable:
                manifest['files'][path.name] = prev
                manifest['reused'] += 1
            else:
                try:
                    tracking = pd.read_csv(path)
                    features, quality = process_game(tracking,metadata,fps)
                    expected = f'tracking_{int(tracking.gameId.iloc[0])}.csv'
                    if path.name != expected:
                        raise DataError(f'Filename does not match the game identifier; use {expected}.')
                    token = hashlib.sha256(f'{VERSION}:{meta_sig}:{path.name}:{sig}:{fps}'.encode()).hexdigest()[:20]
                    names = {'features':f'{token}-features.parquet','quality':f'{token}-quality.parquet'}
                    for key,table in [('features',features),('quality',quality)]:
                        tmp = home/(names[key]+'.tmp')
                        table.to_parquet(tmp,index=False)
                        tmp.replace(home/names[key])
                    manifest['files'][path.name] = {'fingerprint':sig,**names,'rows':len(features),
                                                   'plays':len(quality),'excluded':int(quality.status.eq('excluded').sum())}
                    manifest['rebuilt'] += 1
                except (DataError,ValueError,pd.errors.ParserError) as exc:
                    manifest['errors'].append({'file':path.name,'message':str(exc)})
            if progress:
                progress(i+1,len(files),path.name)
        tmp = home/'manifest.json.tmp'
        tmp.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        tmp.replace(home/'manifest.json')
        return manifest


def load_features(data_dir=DEFAULT_DATA, cache_dir=DEFAULT_CACHE, game_ids=None):
    home = cache_home(data_dir,cache_dir)
    manifest = read_manifest(data_dir,cache_dir)
    frames,quality = [],[]
    for name,entry in manifest.get('files',{}).items():
        if game_ids is not None:
            # Metadata filters apply after loading, so nonstandard filenames also work.
            q = pd.read_parquet(home/entry['quality'])
            if not q.gameId.isin(game_ids).any():
                continue
        else:
            q = pd.read_parquet(home/entry['quality'])
        quality.append(q)
        frames.append(pd.read_parquet(home/entry['features']))
    return (pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=FEATURE_COLUMNS),
            pd.concat(quality,ignore_index=True) if quality else pd.DataFrame())


def play_metadata(metadata):
    p = metadata['plays'].merge(metadata['games'],on='gameId',validate='many_to_one')
    sc = metadata['pffScoutingData']
    names = sc.loc[sc.pff_role.str.casefold().eq('pass route')].merge(
        metadata['players'][['nflId','displayName']],on='nflId',validate='many_to_one')
    combinations = names.groupby(['gameId','playId']).displayName.agg(lambda s:' + '.join(sorted(s)))
    p = p.merge(combinations.rename('receiver_combination'),on=['gameId','playId'],how='left',validate='one_to_one')
    p['distance_band'] = pd.cut(p.yardsToGo,[-1,3,6,10,float('inf')],labels=['1-3 yards','4-6 yards','7-10 yards','11+ yards']).astype(str)
    return p
