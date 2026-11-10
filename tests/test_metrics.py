import numpy as np
import pandas as pd
import pytest
from metrics import MetricConfig,evaluate,sustained_mask,true_runs
from pipeline import FIELD_WIDTH,process_game,DataError,normalized_line


def test_hand_calculated_complementary_windows(synthetic):
    meta,tracking = synthetic
    features,q = process_game(tracking,meta)
    assert q.status.iloc[0]=='ok'
    assert set(features.frameId)==set(range(2,9))  # release frame 9 is excluded
    plays,people,frames = evaluate(features,MetricConfig(start_seconds=0,end_seconds=2))
    row=plays.iloc[0]
    assert row.observed_seconds==pytest.approx(.7)
    assert row.option_coverage==1
    assert row.longest_gap==0
    assert row.beyond_seconds==pytest.approx(.4)
    assert people.unique_seconds.tolist()==pytest.approx([.3,.3])
    assert people.open_seconds.tolist()==pytest.approx([.4,.4])
    assert frames.options.tolist()==[1,1,1,2,1,1,1]


def test_missing_frames_do_not_bridge_windows():
    assert true_runs([],[])==[]
    assert sustained_mask([True]*4,[1,2,4,5],3).tolist()==[False]*4
    assert sustained_mask([True]*3,[1,2,3],3).tolist()==[True]*3


def test_left_and_right_geometry_are_equivalent(synthetic):
    meta,t = synthetic
    right,_ = process_game(t.copy(),meta)
    left=t.copy()
    left['playDirection']='left'
    left['x']=120-left.x
    left['y']=FIELD_WIDTH-left.y
    lm={k:v.copy() for k,v in meta.items()}
    lm['plays']['absoluteYardlineNumber']=80
    mirrored,q=process_game(left,lm)
    assert q.first_down_line.iloc[0]==50
    np.testing.assert_allclose(right[['x','y','separation','beyond_sticks']],mirrored[['x','y','separation','beyond_sticks']],atol=1e-5)


def test_no_snap_is_excluded_not_assumed(synthetic):
    meta,t=synthetic
    t.loc[t.event.eq('ball_snap'),'event']='None'
    features,q=process_game(t,meta)
    assert features.empty
    assert q.status.iloc[0]=='excluded'
    assert 'No observed snap' in q.reason.iloc[0]


def test_automated_snap_fallback_and_cutoff(synthetic):
    meta,t=synthetic
    t.loc[t.event.eq('ball_snap'),'event']='autoevent_ballsnap'
    t.loc[t.event.eq('pass_forward'),'event']='None'
    features,q=process_game(t,meta)
    assert q.snap_source.iloc[0]=='autoevent_ballsnap'
    assert q.censored.iloc[0]
    assert features.frameId.max()==10


def test_incomplete_frame_excluded(synthetic):
    meta,t=synthetic
    t=t.loc[~(t.team.eq('football')&t.frameId.eq(5))]
    f,q=process_game(t,meta)
    assert q.invalid_frames.iloc[0]==1
    assert 5 not in set(f.frameId)
    plays,_,_=evaluate(f,MetricConfig(start_seconds=0,end_seconds=2))
    assert plays.observed_seconds.iloc[0]==pytest.approx(.6)


def test_duplicate_entity_rejected(synthetic):
    meta,t=synthetic
    with pytest.raises(DataError,match='duplicate'):
        process_game(pd.concat([t,t.iloc[[0]]]),meta)


def test_unknown_first_down_line_is_not_zero(synthetic):
    meta,t=synthetic
    meta['plays']['absoluteYardlineNumber']=np.nan
    meta['plays']['yardlineNumber']=np.nan
    f,_=process_game(t,meta)
    p,_,_=evaluate(f,MetricConfig(start_seconds=0,end_seconds=2))
    assert np.isnan(p.beyond_seconds.iloc[0])
    assert p.line_known_seconds.iloc[0]==0


def test_threshold_changes_results(synthetic):
    meta,t=synthetic
    f,_=process_game(t,meta)
    p,_,_=evaluate(f,MetricConfig(separation_yards=4,start_seconds=0,end_seconds=2))
    assert p.option_coverage.iloc[0]==0
    assert p.longest_gap.iloc[0]==pytest.approx(.7)


def test_invalid_config():
    for values in [{'fps':0},{'separation_yards':-1},{'start_seconds':3,'end_seconds':2},{'fps':float('nan')}]:
        with pytest.raises(ValueError):
            MetricConfig(**values)
