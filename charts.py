"""Shared Plotly visualizations for the dashboard and standalone report."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from metrics import MetricConfig, sustained_mask, true_runs, spacing_candidate
from pipeline import FIELD_WIDTH

TEAL = '#2dd4bf'
AMBER = '#fbbf24'
BLUE = '#60a5fa'
RED = '#fb7185'
BG = '#101b2b'
COLORS = [TEAL,BLUE,AMBER,'#c084fc','#fb923c','#a3e635']


def style(fig,height=360):
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor=BG,
        font=dict(family='Arial, sans-serif',color='#dbe5ef',size=12),height=height,
        margin=dict(l=30,r=20,t=45,b=45),legend=dict(orientation='h',y=1.12,x=0),
        hoverlabel=dict(bgcolor='#172a3d'),xaxis=dict(gridcolor='#263548'),yaxis=dict(gridcolor='#263548'))
    return fig


def exposure_chart(frames,fps=10):
    if frames.empty:
        return style(go.Figure())
    data = frames.assign(t=(frames.elapsed*fps).round().astype(int))
    groups = data.groupby('t').agg(plays=('playId','size'),with_option=('options',lambda s:int(s.gt(0).sum())))
    groups['coverage'] = 100 * groups.with_option/groups.plays
    fig = go.Figure(go.Scatter(x=groups.index/fps,y=groups.coverage,mode='lines',fill='tozeroy',
        line=dict(color=TEAL,width=3),customdata=groups[['plays']],
        hovertemplate='%{x:.1f}s after snap<br>%{y:.1f}% with an option<br>%{customdata[0]} observed plays<extra></extra>'))
    fig.update_layout(title='Receiving options through the dropback',xaxis_title='Seconds after snap',
                      yaxis_title='Observed plays with separation (%)')
    fig.update_yaxes(range=[0,100])
    return style(fig)


def timeline_chart(features,config=MetricConfig()):
    fig = go.Figure()
    f = features.loc[features.elapsed.ge(config.start_seconds-1e-7)&features.elapsed.lt(config.end_seconds-1e-7)]
    required = int(np.ceil(config.minimum_window_seconds*config.fps-1e-8))
    names = []
    for i,(_,part) in enumerate(f.groupby('nflId',sort=False)):
        part = part.sort_values('frameId')
        name = f'{part.displayName.iloc[0]} ({part.officialPosition.iloc[0]})'
        names.append(name)
        fig.add_trace(go.Scatter(x=part.elapsed,y=[name]*len(part),mode='lines',line=dict(color='#344255',width=12),
            showlegend=False,customdata=part[['separation']],hovertemplate=name+'<br>%{x:.1f}s · nearest defender %{customdata[0]:.2f} yd<extra></extra>'))
        mask = sustained_mask(spacing_candidate(part,config.separation_yards).to_numpy(),part.frameId.to_numpy(),required)
        for a,b in true_runs(mask,part.frameId.to_numpy()):
            fig.add_trace(go.Scatter(x=[part.elapsed.iloc[a],part.elapsed.iloc[b]+1/config.fps],y=[name,name],
                mode='lines',line=dict(color=COLORS[i%len(COLORS)],width=14),showlegend=False,
                hovertemplate=name+f'<br>{(b-a+1)/config.fps:.1f}s sustained separation<extra></extra>'))
    fig.update_layout(title='Who provides an option, and when?',xaxis_title='Seconds after snap',
                      yaxis=dict(categoryorder='array',categoryarray=names[::-1]))
    fig.update_xaxes(range=[config.start_seconds,config.end_seconds])
    return style(fig,max(280,70*len(names)+110))


def player_chart(summary):
    part = summary.head(12).sort_values('unique_seconds_per_route')
    fig = go.Figure(go.Bar(x=part.unique_seconds_per_route,y=part.displayName,orientation='h',
        marker_color=TEAL,customdata=part[['routes','games']],
        hovertemplate='%{y}<br>%{x:.2f} unique seconds/route<br>%{customdata[0]} routes, %{customdata[1]} games<extra></extra>'))
    fig.update_layout(title='Who supplies the only separated option?',xaxis_title='Unique seconds per observed route')
    return style(fig,max(330,26*len(part)+100))


def replay_chart(tracking,feature_play,frame_metrics,quality,fps=10):
    """All 22 players and ball. Coordinate normalization matches the feature engine."""
    snap = int(quality.snap_frame)
    end = int(quality.end_frame_exclusive)
    t = tracking.loc[tracking.frameId.ge(snap)&tracking.frameId.lt(end)].copy()
    left = t.playDirection.eq('left')
    t['x'] = np.where(left,120-t.x,t.x)
    t['y'] = np.where(left,FIELD_WIDTH-t.y,t.y)
    route_ids = set(feature_play.nflId)
    offense = feature_play.team.iloc[0]
    names = feature_play.drop_duplicates('nflId').set_index('nflId').displayName.to_dict()
    open_lookup = {r.frameId:set(int(v) for v in r.open_ids.split(',') if v) for r in frame_metrics.itertuples()}
    frame_ids = np.sort(t.frameId.unique())
    frame_ids = frame_ids[::max(1,int(np.ceil(len(frame_ids)/100)))]

    def traces(frame):
        part = t.loc[t.frameId.eq(frame)]
        categories = [('Defense',part.team.ne(offense)&part.team.ne('football'),RED,'circle',10),
                      ('Offensive teammates',part.team.eq(offense)&~part.nflId.isin(route_ids),'#7689a0','circle',10),
                      ('Route runners',part.nflId.isin(route_ids),BLUE,'circle',15),
                      ('Ball',part.team.eq('football'),'#fff1cd','diamond',9)]
        items = []
        for label,mask,color,symbol,size in categories:
            rows = part.loc[mask]
            texts = [names.get(v,'') for v in rows.nflId] if label == 'Route runners' else ['']*len(rows)
            colors = [TEAL if v in open_lookup.get(frame,set()) else color for v in rows.nflId]
            items.append(go.Scatter(x=rows.x,y=rows.y,mode='markers+text',name=label,
                text=texts,textposition='top center',textfont=dict(size=9),
                marker=dict(color=colors,size=size,symbol=symbol,line=dict(color='#e4edf3',width=0.7)),
                hovertemplate=label+'<br>x=%{x:.1f}, y=%{y:.1f}<extra></extra>'))
        return items

    fig = go.Figure(data=traces(frame_ids[0]))
    for x in range(10,111,10):
        fig.add_shape(type='line',x0=x,x1=x,y0=0,y1=FIELD_WIDTH,line=dict(color='#3c675b',width=1))
    for x in [0,110]:
        fig.add_shape(type='rect',x0=x,x1=x+10,y0=0,y1=FIELD_WIDTH,fillcolor='#183f36',line_width=0,layer='below')
    if pd.notna(quality.get('line_of_scrimmage')):
        fig.add_vline(x=float(quality.line_of_scrimmage),line_color=BLUE,line_dash='dot')
    if pd.notna(quality.get('first_down_line')):
        fig.add_vline(x=float(quality.first_down_line),line_color=AMBER,line_width=2)
    fig.frames = [go.Frame(data=traces(frame),name=str(frame),layout=go.Layout(
        title_text=f'{(frame-snap)/fps:.1f}s after snap · offense moves right')) for frame in frame_ids]
    animation = dict(frame=dict(duration=100,redraw=True),transition=dict(duration=0),mode='immediate')
    fig.update_layout(title='0.0s after snap · offense moves right',
        updatemenus=[dict(type='buttons',direction='left',x=0,y=-0.1,active=-1,showactive=False,
            bgcolor='#214b41',bordercolor='#4f8274',font=dict(color='#e4fff7'),buttons=[
            dict(label='▶ Play',method='animate',args=[None,animation]),
            dict(label='Pause',method='animate',args=[[None],dict(frame=dict(duration=0,redraw=False),mode='immediate')])])],
        sliders=[dict(active=0,x=0.23,len=0.75,y=-0.08,currentvalue=dict(prefix='Frame '),steps=[
            dict(label=f'{(frame-snap)/fps:.1f}s',method='animate',args=[[str(frame)],animation]) for frame in frame_ids])])
    style(fig,500)
    fig.update_xaxes(range=[0,120],title='Field length (yards)',showgrid=False,constrain='domain')
    fig.update_yaxes(range=[0,FIELD_WIDTH],scaleanchor='x',scaleratio=1,title='',showgrid=False,constrain='domain')
    fig.update_layout(plot_bgcolor='#12372e',margin=dict(l=15,r=15,t=70,b=70))
    return fig
