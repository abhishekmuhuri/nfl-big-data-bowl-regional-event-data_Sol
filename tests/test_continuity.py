import pytest
from metrics import MetricConfig,evaluate
from pipeline import process_game


def test_entire_missing_frame_is_reported(synthetic):
    metadata,tracking=synthetic
    features,quality=process_game(tracking.loc[tracking.frameId.ne(5)],metadata)
    assert quality.invalid_frames.iloc[0]==1
    assert quality.status.iloc[0]=='partial'
    metrics,_,_=evaluate(features,MetricConfig(start_seconds=0,end_seconds=2))
    assert metrics.observed_seconds.iloc[0]==pytest.approx(.6)


def test_off_field_receiver_does_not_supply_an_option(synthetic):
    metadata,tracking=synthetic
    features,_=process_game(tracking,metadata)
    features.loc[features.nflId.eq(100),'y']=-1
    plays,people,_=evaluate(features,MetricConfig(start_seconds=0,end_seconds=2))
    assert plays.observed_seconds.iloc[0]==pytest.approx(.7)
    assert plays.option_coverage.iloc[0]==pytest.approx(4/7)
    assert people.loc[people.nflId.eq(100),'open_seconds'].iloc[0]==0
