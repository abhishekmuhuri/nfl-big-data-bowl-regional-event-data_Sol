"""Route Relay: an evidence-first receiver timing dashboard."""
from dataclasses import asdict
from pathlib import Path
import io
import json
import numpy as np
import pandas as pd
import streamlit as st

from pipeline import (ROOT, DEFAULT_DATA, DEFAULT_CACHE, VERSION, DataError, load_metadata,
                      inventory_signature, read_manifest, build_dataset, load_features, play_metadata)
from metrics import MetricConfig, evaluate, player_summary, cohort_summary, game_bootstrap_interval
from charts import exposure_chart, timeline_chart, player_chart, replay_chart
from import_data import import_inputs

st.set_page_config(page_title='Route Relay | Receiver timing',page_icon='🏈',layout='wide')
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
html,body,[class*="css"] {font-family:'DM Sans',sans-serif;}
.stApp {background:#0a111e;color:#e3ebf4;}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif!important;letter-spacing:-.035em;}
[data-testid="stSidebar"] {background:#101b2b;border-right:1px solid #233249;}
[data-testid="stMetric"] {background:#111e2f;border:1px solid #29394e;border-radius:12px;padding:18px 16px;}
[data-testid="stMetricLabel"] {font-size:12px;color:#a6b7cc;}
[data-testid="stMetricValue"] {font-family:'Space Grotesk',sans-serif;font-size:28px;color:#54dfce;}
.eyebrow {color:#39d4bd;letter-spacing:.18em;font-size:11px;font-weight:700;margin-top:8px;}
.intro {color:#a5b5c9;font-size:17px;max-width:850px;line-height:1.6;}
.note {border-left:3px solid #2dd4bf;padding:12px 18px;background:#112334;border-radius:0 8px 8px 0;line-height:1.65;}
.stTabs [data-baseweb="tab-list"] {gap:28px;border-bottom:1px solid #26364b;}
.stTabs [aria-selected="true"] {color:#54dfce!important;}
div.stButton>button[kind="primary"] {background:#24bba6;color:#06161a;border:0;}
</style>''',unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_metadata(folder,signature):
    raw = load_metadata(folder)
    return raw,play_metadata(raw)


@st.cache_data(show_spinner=False,max_entries=12)
def cached_features(folder,signature,games):
    return load_features(folder,DEFAULT_CACHE,games)


@st.cache_data(show_spinner=False,max_entries=16)
def cached_evaluate(features,config):
    return evaluate(features,config)


@st.cache_data(show_spinner=False,max_entries=8)
def raw_game(folder,game,signature):
    # Find by game content too, so imported/nonstandard filenames remain readable.
    manifest = read_manifest(folder,DEFAULT_CACHE)
    for name in manifest.get('files',{}):
        if name == f'tracking_{game}.csv':
            return pd.read_csv(Path(folder)/'tracking'/name)
    for path in sorted((Path(folder)/'tracking').glob('*.csv')):
        if int(pd.read_csv(path,nrows=1).gameId.iloc[0]) == game:
            return pd.read_csv(path)
    raise DataError(f'Cannot locate tracking for game {game}.')


def rebuild(folder,fps):
    bar = st.progress(0,text='Preparing the dataset. The first run processes each game once.')
    try:
        result = build_dataset(folder,DEFAULT_CACHE,fps,progress=lambda i,n,name:
                               bar.progress(i/n,text=f'Preparing game {i} of {n}'))
    finally:
        bar.empty()
    return result


def pretty_table(table):
    return table.rename(columns={
        'displayName':'Player','officialPosition':'Position','routes':'Observed routes','games':'Games',
        'separated_pct':'Separated time (%)','unique_seconds_per_route':'Unique seconds / route',
        'mean_window_seconds':'Mean window (s)','unique_seconds':'Unique seconds','open_seconds':'Separated seconds',
        'observed_seconds':'Observed seconds','windows':'Windows','plays':'Plays','option_coverage_pct':'Option coverage (%)',
        'median_gap':'Median longest gap (s)','beyond_coverage_pct':'Beyond-sticks coverage (%)',
        'small_sample':'Small sample','pff_passCoverage':'Coverage','offenseFormation':'Formation',
        'down':'Down','distance_band':'Distance','receiver_combination':'Receiver combination'})


st.sidebar.markdown('## 🏈 Route Relay')
st.sidebar.caption('Receiver timing · 2021 demo + your data')
default_folder_label = 'data' if DEFAULT_DATA.resolve() == (ROOT/'data').resolve() else str(DEFAULT_DATA)
folder_input = st.sidebar.text_input('Dataset folder',value=default_folder_label,help='Use the included data folder or paste a folder with the same CSV structure.')
folder = str((ROOT/Path(folder_input)).resolve() if not Path(folder_input).is_absolute() else Path(folder_input).resolve())
fps = st.sidebar.number_input('Tracking frames per second',min_value=1.0,max_value=100.0,value=10.0,step=1.0,
                             help='The supplied dataset uses 10 Hz. Change this for a new feed only if its sampling rate differs.')
refresh = st.sidebar.button('↻ Refresh data',width='stretch',help='Detect added or changed files and process only affected games.')
try:
    if (Path(folder)/'.route-relay.lock').exists():
        st.info('The dataset is being imported or processed. Refresh this page when that job finishes.')
        st.stop()
    signature = inventory_signature(folder)
    metadata,meta = cached_metadata(folder,signature)
    manifest = read_manifest(folder,DEFAULT_CACHE)
    needs_build = not manifest or manifest.get('version') != VERSION or manifest.get('fps') != fps
    if refresh or needs_build:
        manifest = rebuild(folder,fps)
    elif manifest.get('source_signature') != signature:
        st.warning('The dataset has changed. Click Refresh data to update the analysis before continuing.')
        st.stop()
except (DataError,OSError,ValueError) as exc:
    st.error(f'Cannot open this dataset: {exc}')
    st.info('Use the included data folder, or see docs/GETTING_STARTED.md for the required files.')
    st.stop()

teams = sorted(meta.possessionTeam.unique())
team = st.sidebar.selectbox('Offensive team',teams,index=teams.index('KC') if 'KC' in teams else 0)
team_meta = meta.loc[meta.possessionTeam.eq(team)]
weeks = sorted(team_meta.week.unique().tolist())
selected_weeks = st.sidebar.multiselect('Weeks',weeks,default=weeks)
coverage_values = sorted(team_meta.pff_passCoverage.fillna('Unknown').unique())
coverages = st.sidebar.multiselect('Defensive coverage',coverage_values,
    default=[x for x in ['Cover-1','Cover-3'] if x in coverage_values] or coverage_values)
downs = st.sidebar.multiselect('Down',[1,2,3,4],default=[1,2,3,4])
distance = st.sidebar.slider('Yards to go',0,max(1,int(meta.yardsToGo.max())),(0,max(1,int(meta.yardsToGo.max()))))
formations = st.sidebar.multiselect('Offensive formation',sorted(team_meta.offenseFormation.fillna('Unknown').unique()),
                                    help='Leave empty to include every formation.')
include_conversions = st.sidebar.checkbox('Include two-point attempts',value=False)
with st.sidebar.expander('Measurement settings'):
    threshold = st.slider('Separation threshold (yards)',1.0,4.0,2.0,0.25)
    duration = st.slider('Minimum window (seconds)',0.1,1.0,0.3,0.1)
    interval = st.slider('Analyze time after snap (seconds)',0.0,6.0,(0.5,3.5),0.1)
    minimum_sample = st.number_input('Small-sample flag below this many plays',min_value=2,max_value=100,value=10)
    complete_only = st.checkbox('Require an observed terminal event',value=False,
                               help='Otherwise observed tracking cutoffs are included and clearly flagged.')
if interval[1] <= interval[0]:
    st.error('Choose an analysis interval with end time after start time.')
    st.stop()
config = MetricConfig(threshold,duration,interval[0],interval[1],fps)
selected_downs = downs + ([0] if include_conversions else [])
selected = team_meta.loc[team_meta.week.isin(selected_weeks)&team_meta.pff_passCoverage.fillna('Unknown').isin(coverages)
    &team_meta.down.isin(selected_downs)&team_meta.yardsToGo.between(*distance)]
if formations:
    selected = selected.loc[selected.offenseFormation.fillna('Unknown').isin(formations)]
games = tuple(sorted(selected.gameId.unique().tolist()))
features,quality = cached_features(folder,manifest.get('built_at',''),games)
keys = pd.MultiIndex.from_frame(selected[['gameId','playId']])
features = features.loc[pd.MultiIndex.from_frame(features[['gameId','playId']]).isin(keys)].copy()
if not quality.empty:
    quality = quality.loc[pd.MultiIndex.from_frame(quality[['gameId','playId']]).isin(keys)].copy()
    if complete_only:
        available = quality.loc[~quality.censored,['gameId','playId']]
        features = features.merge(available,on=['gameId','playId'],validate='many_to_one')

with st.spinner('Calculating receiving windows…'):
    play_scores,player_scores,frame_scores = cached_evaluate(features,config)

st.markdown('<div class="eyebrow">FILM REVIEW STARTS WITH A BETTER QUESTION</div>',unsafe_allow_html=True)
st.title('Who keeps the options open?')
st.markdown('<p class="intro">Follow the receiving options through the dropback. Find gaps in route timing, '
            'see who supplies the only separated option, and inspect the plays behind the numbers.</p>',unsafe_allow_html=True)
st.caption(f'{team} offense · {len(selected):,} matching plays · {len(games)} games · '
           f'{threshold:g}-yard separation · sustained for {duration:.1f}s · {interval[0]:.1f}–{interval[1]:.1f}s after snap')
overview,explorer,data_tab = st.tabs(['Team overview','Play explorer','Data & help'])

with overview:
    if play_scores.empty:
        st.info('No analyzable plays match these filters. Broaden the situation or review the data-quality details.')
    else:
        observed = play_scores.observed_seconds.sum()
        total_windows = player_scores.windows.sum()
        beyond_denominator = play_scores.line_known_seconds.sum()
        cards = st.columns(5)
        cards[0].metric('Option coverage',f'{100*play_scores.option_seconds.sum()/observed:.1f}%',
                        help='Share of observed pre-throw time with at least one sustained separation window.')
        cards[1].metric('Median longest gap',f'{play_scores.longest_gap.median():.2f}s')
        cards[2].metric('Single-option time',f'{100*player_scores.unique_seconds.sum()/observed:.1f}%',
                        help='Share of observed time when exactly one route runner supplies separation.')
        cards[3].metric('Mean window duration',f'{player_scores.open_seconds.sum()/total_windows:.2f}s' if total_windows else 'No windows')
        cards[4].metric('Beyond-sticks coverage',f'{100*play_scores.beyond_seconds.sum()/beyond_denominator:.1f}%' if beyond_denominator else 'Unavailable')
        ci = game_bootstrap_interval(play_scores)
        st.caption(f'{len(play_scores):,} measured plays · {observed:,.1f} observed seconds. '
                   + (f'Option coverage 95% game-bootstrap interval: {ci[0]*100:.1f}–{ci[1]*100:.1f}%.' if ci else
                      'At least three games are needed for a game-bootstrap interval.'))
        if len(play_scores) < len(selected):
            st.info(f'{len(selected)-len(play_scores)} matching plays have no measured exposure under these settings. '
                    'See Data & help for exclusions; clips ending before the chosen start time also have no exposure.')
        left,right = st.columns([1.15,1])
        with left:
            st.plotly_chart(exposure_chart(frame_scores,fps),width='stretch',key='exposure')
            st.caption('Each point uses only plays still observed at that time. Later points describe a surviving subset of dropbacks.')
        with right:
            grouped_players = player_summary(player_scores)
            skill_players = grouped_players.loc[grouped_players.officialPosition.isin(['WR','TE','RB'])]
            st.plotly_chart(player_chart(skill_players),width='stretch',key='players')
            st.caption('All route runners, including FBs, enter the option count. Player comparisons depend on role, depth, and teammates.')
        cohort_name = st.selectbox('Compare situations',['Coverage','Formation','Down and distance','Receiver combination'])
        grouping = {'Coverage':['pff_passCoverage'],'Formation':['offenseFormation'],
                    'Down and distance':['down','distance_band'],'Receiver combination':['receiver_combination']}[cohort_name]
        cohort = cohort_summary(play_scores,selected,grouping,int(minimum_sample))
        st.dataframe(pretty_table(cohort[grouping+['plays','games','option_coverage_pct','median_gap','beyond_coverage_pct','small_sample']]).round(2),
                     hide_index=True,width='stretch')
        st.caption('Comparisons are descriptive. Review similar downs, distances, depth, formation, and coverage before changing a call.')
        st.subheader('Player contributions')
        st.dataframe(pretty_table(skill_players[['displayName','officialPosition','routes','games','separated_pct',
            'unique_seconds_per_route','mean_window_seconds']]).round(2),hide_index=True,width='stretch')
        csv = play_scores.merge(selected,on=['gameId','playId'],validate='one_to_one').to_csv(index=False)
        st.download_button('Download filtered play metrics',csv,file_name=f'route_relay_{team}_plays.csv',mime='text/csv')
        st.download_button('Download receiver metrics',player_scores.to_csv(index=False),file_name=f'route_relay_{team}_receivers.csv',mime='text/csv')

with explorer:
    if play_scores.empty:
        st.info('Choose a situation with measured plays to see the replay.')
    else:
        candidates = play_scores.merge(selected,on=['gameId','playId'],validate='one_to_one')
        sort_by = st.selectbox('Find a play',['Longest receiving gap','Highest option coverage','Lowest option coverage'])
        candidates = candidates.sort_values('longest_gap' if sort_by == 'Longest receiving gap' else 'option_coverage',
                                            ascending=sort_by == 'Lowest option coverage')
        labels = {i:f'Week {int(r.week)} · {r.possessionTeam} vs {r.defensiveTeam} · '
                    f'{int(r.down)} & {int(r.yardsToGo)} · {r.pff_passCoverage} · play {int(r.playId)}'
                  for i,r in candidates.iterrows()}
        chosen = st.selectbox('Play',list(labels),format_func=labels.get)
        play = candidates.loc[chosen]
        pf = features.loc[features.gameId.eq(play.gameId)&features.playId.eq(play.playId)]
        ff = frame_scores.loc[frame_scores.gameId.eq(play.gameId)&frame_scores.playId.eq(play.playId)]
        q = quality.loc[quality.gameId.eq(play.gameId)&quality.playId.eq(play.playId)].iloc[0]
        st.write(str(play.playDescription))
        st.caption(f'Observed outcome: {play.passResult} · Option coverage: {play.option_coverage*100:.1f}% · '
                   f'Longest gap: {play.longest_gap:.2f}s · Measured exposure: {play.observed_seconds:.1f}s')
        if q.censored:
            st.info('This clip ends without an observed throw, sack, or scramble tag. Metrics use only the available tracking.')
        if q.invalid_frames:
            st.warning(f'{q.invalid_frames} incomplete frames were excluded and break sustained windows.')
        st.plotly_chart(timeline_chart(pf,config),width='stretch',key='timeline')
        with st.spinner('Loading the field replay…'):
            tracking = raw_game(folder,int(play.gameId),signature)
            tracking = tracking.loc[tracking.playId.eq(play.playId)]
            st.plotly_chart(replay_chart(tracking,pf,ff,q,fps),width='stretch',key='replay')
        st.caption('Green route runners meet the sustained-separation rule inside the selected analysis interval. '
                   'Blue dotted line: scrimmage. Yellow line: first down / goal line. Replay stops before the terminal event.')
        st.markdown('<div class="note"><b>Take it to film:</b> Identify the transition between receiving windows. '
                    'Is a late outlet leaving a gap? Does the same pattern recur in comparable situations? '
                    'Use these observations to choose a practice experiment, rather than infer the quarterback’s intended read.</div>',unsafe_allow_html=True)

with data_tab:
    st.subheader('Bring in the next game')
    st.write('Upload supporting CSVs, tracking CSVs, or a ZIP with the same structure. New identifiers are added; '
             'matching identifiers are updated. Include the supporting rows for new games, plays, and players.')
    uploads = st.file_uploader('Choose dataset files',type=['csv','zip'],accept_multiple_files=True)
    if st.button('Import files and refresh',type='primary',disabled=not uploads):
        try:
            with st.spinner('Validating and importing the batch…'):
                changed = import_inputs([(u.name,u.getvalue()) for u in uploads],folder)
            rebuild(folder,fps)
            st.success(f'Imported {len(changed)} files. The dataset is ready.')
            st.rerun()
        except (DataError,OSError,ValueError) as exc:
            st.error(f'Import rejected: {exc}')
    st.markdown('For an automated feed, write completed CSVs atomically into `data/tracking/`, then use '
                '`python process_data.py --watch`. A finite JSON batch can be piped into '
                '`python import_data.py --stdin`; see `docs/DATA_PIPELINE.md`.')
    st.subheader('Data coverage and exclusions')
    st.write(f'{len(manifest.get("files",{}))} processed tracking files. '
             f'Last build: {manifest.get("built_at","unavailable")} (UTC).')
    if manifest.get('errors'):
        st.error('Some tracking files were rejected. They do not contribute stale cached results.')
        st.dataframe(pd.DataFrame(manifest['errors']),hide_index=True)
    if not quality.empty:
        st.dataframe(quality[['gameId','playId','status','reason','snap_source','terminal_event','censored',
                              'invalid_frames','observed_frames','out_of_bounds_player_rows']],hide_index=True,width='stretch')
        st.download_button('Download data-quality details',quality.to_csv(index=False),'route_relay_quality.csv','text/csv')
    st.subheader('What the metrics mean')
    st.markdown('''
- A receiver has a **separation window** when their nearest opposing defender stays at least the selected distance away for the selected minimum duration.
- **Option coverage** divides time with one or more such receivers by valid observed time. Multiple options are useful; overlap is not treated as waste.
- **Unique contribution** is time when a player supplies the only separated option. It depends on teammates and deployment, and is not an isolated talent grade.
- **Beyond-sticks coverage** requires a separated receiver at or beyond the first-down line, capped at the goal line. Unknown line positions remain unavailable.
- Every frame represents one sampling interval. Missing frames break windows. Time outside the clip, after the throw, and before the selected start is never counted as failure.
- Off-field route runners do not supply qualifying windows; other receivers in the same valid frame remain measurable.
- These are retrospective spatial measures. Passing lanes, defender leverage, ball flight, route assignments, quarterback vision, and intended reads are not modeled.
- Exclude conversions, filter comparable situations, inspect sample sizes, and vary the thresholds before drawing a coaching conclusion.
''')
    st.link_button('Source code and instructions','https://github.com/abhishekmuhuri/nfl-big-data-bowl-regional-event-data_Sol')

st.divider()
st.caption('Route Relay · NFL Next Gen Stats + PFF · Separation shows space, not proof of a safe pass. '
           'The included 2021 data is a historical demonstration; import new data for current team analysis.')
