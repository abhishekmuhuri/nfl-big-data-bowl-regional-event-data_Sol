"""Create a portable interactive demonstration, CSV evidence, and findings JSON."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import html
import json
import numpy as np
import pandas as pd
from pipeline import DEFAULT_DATA,DEFAULT_CACHE,build_dataset,load_metadata,play_metadata,load_features
from metrics import MetricConfig,evaluate,player_summary,cohort_summary,game_bootstrap_interval
from charts import exposure_chart,player_chart,timeline_chart,replay_chart

REPOSITORY='https://github.com/abhishekmuhuri/nfl-big-data-bowl-regional-event-data_Sol'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--cache-dir',type=Path,default=DEFAULT_CACHE)
    parser.add_argument('--team',default='KC')
    parser.add_argument('--coverage',nargs='*',default=['Cover-1','Cover-3'])
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'docs/index.html')
    parser.add_argument('--fps',type=float,default=10)
    args=parser.parse_args()
    manifest=build_dataset(args.data_dir,args.cache_dir,args.fps)
    raw=load_metadata(args.data_dir)
    metadata=play_metadata(raw)
    chosen=metadata.loc[metadata.possessionTeam.eq(args.team)&metadata.down.isin([1,2,3,4])]
    if args.coverage:
        chosen=chosen.loc[chosen.pff_passCoverage.isin(args.coverage)]
    if chosen.empty:
        raise ValueError('No plays match the selected team and coverage filters.')
    features,quality=load_features(args.data_dir,args.cache_dir,chosen.gameId.unique())
    features=features.merge(chosen[['gameId','playId']],on=['gameId','playId'],validate='many_to_one')
    config=MetricConfig(fps=args.fps)
    plays,people,frames=evaluate(features,config)
    if plays.empty:
        raise ValueError('No analyzable plays match the selected filters.')
    grouped=player_summary(people)
    coverage=cohort_summary(plays,chosen,['pff_passCoverage'])
    total=plays.observed_seconds.sum()
    only_te_rb=people.loc[people.officialPosition.isin(['TE','RB'])]
    unique_seconds=float(only_te_rb.unique_seconds.sum())
    unique_plays=only_te_rb.loc[only_te_rb.unique_seconds.gt(0),['gameId','playId']].drop_duplicates()
    evidence=plays.merge(chosen,on=['gameId','playId'],validate='one_to_one')
    interval=game_bootstrap_interval(plays)
    finding=(f'For {args.team} against {" and ".join(args.coverage) if args.coverage else "all coverages"}, '
             f'TEs and RBs supplied the only separated option on {len(unique_plays)} of {len(plays)} measured plays '
             f'({100*len(unique_plays)/len(plays):.1f}%), totaling {unique_seconds:.1f} seconds. '
             'These are complementary spatial windows, not proof of a safe pass or an unrecognized quarterback read.')
    findings={'team':args.team,'coverages':args.coverage,'settings':config.__dict__,
        'matching_plays':len(chosen),'measured_plays':len(plays),'games':int(plays.gameId.nunique()),
        'observed_seconds':float(total),'option_coverage':float(plays.option_seconds.sum()/total),
        'median_longest_gap':float(plays.longest_gap.median()),
        'te_rb_unique_seconds':unique_seconds,'te_rb_unique_plays':len(unique_plays),
        'coverage_comparison':json.loads(coverage.to_json(orient='records')),
        'option_coverage_95pct_game_bootstrap':interval,'finding':finding,
        'source_signature':manifest['source_signature'],'generated_at':datetime.now(timezone.utc).isoformat(),
        'limitations':['Spatial separation is not pass safety.','Comparisons are descriptive and not causal.',
            'Frames outside available clips are not observed.','Availability varies with route depth and deployment.',
            'Data contains penalty-affected plays; raw outcomes are not official passing statistics.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    (args.output.parent/'findings.json').write_text(json.dumps(findings,indent=2,allow_nan=False),encoding='utf-8')
    evidence.to_csv(args.output.parent/'demo_play_metrics.csv',index=False)
    people.to_csv(args.output.parent/'demo_receiver_metrics.csv',index=False)

    def fragment(fig,include=False):
        return fig.to_html(full_html=False,include_plotlyjs=True if include else False,
                           config={'displaylogo':False,'responsive':True})

    examples=[]
    rb=only_te_rb.groupby(['gameId','playId']).unique_seconds.sum().sort_values(ascending=False)
    top=rb.index[0]
    candidates=[('A TE/RB supplies a complementary option',int(top[0]),int(top[1])),
                ('Investigate the longest receiving gap',int(plays.loc[plays.longest_gap.idxmax(),'gameId']),int(plays.loc[plays.longest_gap.idxmax(),'playId'])),
                ('A comparison with sustained options',int(plays.loc[plays.option_coverage.idxmax(),'gameId']),int(plays.loc[plays.option_coverage.idxmax(),'playId']))]
    used=set()
    for title,game,play in candidates:
        if (game,play) in used:
            continue
        used.add((game,play))
        pf=features.loc[features.gameId.eq(game)&features.playId.eq(play)]
        ff=frames.loc[frames.gameId.eq(game)&frames.playId.eq(play)]
        q=quality.loc[quality.gameId.eq(game)&quality.playId.eq(play)].iloc[0]
        match=evidence.loc[evidence.gameId.eq(game)&evidence.playId.eq(play)].iloc[0]
        tracking=pd.read_csv(args.data_dir/'tracking'/f'tracking_{game}.csv')
        tracking=tracking.loc[tracking.playId.eq(play)]
        examples.append(f'<section><p class="eyebrow">PLAY STUDY · {game} / {play}</p><h2>{html.escape(title)}</h2>'
            f'<p>{html.escape(str(match.playDescription))}</p><p class="muted">{html.escape(str(match.pff_passCoverage))} · '
            f'Option coverage {match.option_coverage*100:.1f}% · longest gap {match.longest_gap:.2f}s · '
            f'{"Tracking cutoff; terminal event not observed" if q.censored else "Stops before " + html.escape(str(q.terminal_event))}</p>'
            +fragment(timeline_chart(pf,config))+fragment(replay_chart(tracking,pf,ff,q,args.fps))+'</section>')
    clean_players=grouped.loc[grouped.officialPosition.isin(['TE','WR','RB'])]
    table=coverage[['pff_passCoverage','plays','games','option_coverage_pct','median_gap','beyond_coverage_pct']].rename(columns={
        'pff_passCoverage':'Coverage','plays':'Plays','games':'Games','option_coverage_pct':'Option coverage (%)',
        'median_gap':'Median longest gap (s)','beyond_coverage_pct':'Beyond-sticks coverage (%)'}).round(2).to_html(index=False,border=0)
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Route Relay | Who keeps the options open?</title><style>
*{box-sizing:border-box}body{margin:0;background:#0a111e;color:#dbe5ef;font:16px/1.7 system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:35px 28px}nav{display:flex;gap:24px;justify-content:space-between;align-items:center;border-bottom:1px solid #26364b;padding-bottom:24px}a{color:#53dfce;text-decoration:none}h1{font-size:clamp(36px,5vw,65px);line-height:1.08;letter-spacing:-.055em;margin:28px 0}h2{font-size:29px;letter-spacing:-.03em}p{max-width:950px}.eyebrow{color:#3dd5be;font-size:12px;letter-spacing:.16em;font-weight:700}.muted{color:#a5b5c9}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:30px 0}.card{background:#111e2f;border:1px solid #2b3a50;border-radius:12px;padding:22px}.value{display:block;color:#54dfce;font-size:34px;font-weight:650}.label{font-size:13px;color:#a5b5c9}section{padding:30px 0;border-bottom:1px solid #253449}.finding{background:#102b32;border-left:3px solid #2dd4bf;padding:22px 28px;border-radius:0 12px 12px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:14px;border-bottom:1px solid #28374a}th{color:#a3b5cb}code{background:#142338;padding:4px 7px;border-radius:4px}footer{padding:30px 0;color:#9aadc3;font-size:13px}.pill{border:1px solid #345348;border-radius:30px;padding:7px 12px;color:#8fe1d1;font-size:12px}@media(max-width:760px){.cards{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}main{padding:22px 14px}nav{flex-wrap:wrap}.js-plotly-plot{max-width:100%}}
</style></head><body><main><nav><b>🏈 ROUTE RELAY</b><span class="pill">INTERACTIVE DEMONSTRATION</span><a href="REPO">Source & download</a><a href="REPO/blob/main/docs/GETTING_STARTED.md">Run the full dashboard</a></nav>
<p class="eyebrow">RECEIVER TIMING · DEMO_TEAM OFFENSE</p><h1>Who keeps<br>the options open?</h1><p class="muted">A receiver’s contribution can happen between someone else’s windows. Follow WR, TE, and RB separation through the dropback, then take the pattern to film.</p>
<div class="cards">CARDS</div><div class="finding"><b>The finding</b><p>FINDING</p></div>
<p class="muted">SCOPE. Separation ≥ 2 yards for ≥ 0.3 seconds, from 0.5 to 3.5 seconds after snap, stopping before the throw, sack, scramble, or available cutoff. Exposure is measured in 0.1-second bins.</p>
<section><div class="grid"><div>EXPOSURE</div><div>PLAYERS</div></div><p class="muted">Later time points include only still-observed dropbacks. Unique contribution depends on role, depth, and teammates; it is not an isolated talent grade.</p><div class="table-wrap">TABLE</div></section>
EXAMPLES
<section><h2>Make the next coaching question specific.</h2><p>Review the gaps between receiving windows. Compare similar downs, distances, formations, and coverage. Look for recurring timing patterns before selecting a practice adjustment.</p><h3>Run the full tool</h3><p>Download and extract the <a href="REPO/archive/refs/heads/main.zip">repository ZIP</a>. Install Python 3.12 or newer, then double-click <code>START_WINDOWS.bat</code> or run <code>python start.py</code>. The dashboard includes all teams, adjustable thresholds, imports, quality details, and CSV downloads.</p><p><a href="demo_play_metrics.csv">Download demo play metrics</a> · <a href="demo_receiver_metrics.csv">Receiver evidence</a> · <a href="findings.json">Settings and findings</a></p></section>
<footer>This page is a reproducible snapshot, not the live import dashboard. Spatial separation is not proof of a safe pass: lanes, leverage, ball flight, vision, and reads are not modeled. The 2021 data is a historical demonstration. NFL Next Gen Stats tracking and PFF scouting; source documentation is preserved in the repository. Regenerate this page with <code>python export_report.py</code>.</footer></main></body></html>'''
    cards=''.join(f'<div class="card"><span class="value">{value}</span><span class="label">{label}</span></div>' for value,label in [
        (f'{len(plays):,}','Measured plays'),(f'{100*plays.option_seconds.sum()/total:.1f}%','Option coverage'),
        (f'{plays.longest_gap.median():.2f}s','Median longest gap'),(f'{unique_seconds:.1f}s','TE/RB unique option time')])
    values={'REPO':REPOSITORY,'DEMO_TEAM':html.escape(args.team),'CARDS':cards,'FINDING':html.escape(finding),
            'SCOPE':f'{len(plays)} plays across {plays.gameId.nunique()} games; coverages: '+html.escape(', '.join(args.coverage)),
            'EXPOSURE':fragment(exposure_chart(frames,args.fps),True),'PLAYERS':fragment(player_chart(clean_players)),
            'TABLE':table,'EXAMPLES':''.join(examples)}
    # Mark template slots before injecting JavaScript; never replace bare words
    # such as TABLE inside Plotly's bundled library or serialized chart data.
    for key in values:
        page=page.replace(key,'{{'+key+'}}')
    for key,value in values.items():
        page=page.replace('{{'+key+'}}',value)
    args.output.write_text(page,encoding='utf-8')
    (args.output.parent/'.nojekyll').touch()
    print(json.dumps(findings,indent=2))
    print(f'Interactive report: {args.output}')


if __name__=='__main__':
    main()
