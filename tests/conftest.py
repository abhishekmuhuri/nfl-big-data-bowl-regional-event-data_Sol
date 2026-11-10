from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def synthetic():
    """A hand-specified play with two overlapping, complementary route windows."""
    offense = np.arange(100,111)
    defense = np.arange(200,211)
    games = pd.DataFrame([dict(gameId=1,season=2021,week=1,homeTeamAbbr='A',visitorTeamAbbr='B')])
    plays = pd.DataFrame([dict(gameId=1,playId=10,possessionTeam='A',defensiveTeam='B',down=3,yardsToGo=10,
        passResult='C',absoluteYardlineNumber=40,yardlineNumber=30,yardlineSide='A',
        pff_passCoverage='Cover-3',pff_passCoverageType='Zone',offenseFormation='SHOTGUN',playDescription='Test play')])
    players = pd.DataFrame([dict(nflId=int(n),displayName=f'Player {n}',officialPosition='WR' if n==100 else 'RB' if n==101 else 'T')
                            for n in np.r_[offense,defense]])
    scouting = pd.DataFrame([dict(gameId=1,playId=10,nflId=int(n),
        pff_role='Pass Route' if n in [100,101] else 'Pass' if n==102 else 'Pass Block' if n<200 else 'Coverage')
        for n in np.r_[offense,defense]])
    rows = []
    for frame in range(1,11):
        event = 'ball_snap' if frame==2 else 'pass_forward' if frame==9 else 'None'
        for i,n in enumerate(offense):
            x,y = (50,10) if n==100 else (48,20) if n==101 else (38+i*.1,30+i*.1)
            rows.append(dict(gameId=1,playId=10,nflId=int(n),frameId=frame,team='A',playDirection='right',x=x,y=y,event=event))
        for i,n in enumerate(defense):
            x,y = (50,10+(3 if frame>=5 else 1)) if i==0 else (48,20+(3 if frame<=5 else 1)) if i==1 else (85+i,40)
            rows.append(dict(gameId=1,playId=10,nflId=int(n),frameId=frame,team='B',playDirection='right',x=x,y=y,event=event))
        rows.append(dict(gameId=1,playId=10,nflId=np.nan,frameId=frame,team='football',playDirection='right',x=40,y=26,event=event))
    metadata = dict(games=games,plays=plays,players=players,pffScoutingData=scouting)
    return metadata,pd.DataFrame(rows)


@pytest.fixture
def data_folder(tmp_path,synthetic):
    metadata,tracking = synthetic
    root = tmp_path/'data'
    (root/'tracking').mkdir(parents=True)
    for name,table in metadata.items():
        table.to_csv(root/f'{name}.csv',index=False)
    tracking.to_csv(root/'tracking/tracking_1.csv',index=False)
    return root
