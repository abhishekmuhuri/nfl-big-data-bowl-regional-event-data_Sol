import io
import json
import zipfile
import pandas as pd
import pytest
from pipeline import build_dataset,load_features,load_metadata,DataError
from import_data import import_inputs,read_json_batches,unpack_inputs


def test_incremental_cache_and_content_change(data_folder,tmp_path):
    cache=tmp_path/'cache'
    first=build_dataset(data_folder,cache)
    assert first['rebuilt']==1 and not first['errors']
    second=build_dataset(data_folder,cache)
    assert second['reused']==1 and second['rebuilt']==0
    path=data_folder/'tracking/tracking_1.csv'
    t=pd.read_csv(path)
    t.loc[t.nflId.eq(100),'x']+=1
    t.to_csv(path,index=False)
    third=build_dataset(data_folder,cache)
    assert third['rebuilt']==1 and third['reused']==0
    assert not load_features(data_folder,cache)[0].empty


def test_metadata_change_invalidates_features(data_folder,tmp_path):
    cache=tmp_path/'cache'
    build_dataset(data_folder,cache)
    p=data_folder/'players.csv'
    df=pd.read_csv(p)
    df.loc[df.nflId.eq(100),'displayName']='Updated Name'
    df.to_csv(p,index=False)
    assert build_dataset(data_folder,cache)['rebuilt']==1
    f,_=load_features(data_folder,cache)
    assert 'Updated Name' in set(f.displayName)


def test_failed_file_never_reuses_stale_cache(data_folder,tmp_path):
    cache=tmp_path/'cache'
    build_dataset(data_folder,cache)
    path=data_folder/'tracking/tracking_1.csv'
    path.write_text('invalid\n1\n')
    manifest=build_dataset(data_folder,cache)
    assert manifest['errors'] and not manifest['files']
    assert load_features(data_folder,cache)[0].empty


def test_new_game_can_be_piped_in(data_folder,tmp_path,synthetic):
    meta,t=synthetic
    batches=[]
    for name in ['games','plays','pffScoutingData']:
        table=meta[name].copy()
        table['gameId']=2
        batches.append(json.dumps({'table':name,'rows':table.to_dict('records')}))
    t=t.copy()
    t['gameId']=2
    batches.append(json.dumps({'table':'tracking','rows':json.loads(t.to_json(orient='records'))}))
    imported=import_inputs(read_json_batches(io.StringIO('\n'.join(batches))),data_folder)
    assert 'tracking/tracking_2.csv' in imported
    assert len(load_metadata(data_folder)['games'])==2
    manifest=build_dataset(data_folder,tmp_path/'cache')
    assert len(manifest['files'])==2 and not manifest['errors']
    f,_=load_features(data_folder,tmp_path/'cache')
    assert set(f.gameId)=={1,2}


def test_rejected_batch_leaves_data_unchanged(data_folder):
    path=data_folder/'players.csv'
    original=path.read_bytes()
    invalid=b'gameId,playId,nflId\n1,10,100\n'
    with pytest.raises(DataError):
        import_inputs([('players.csv',original),('tracking_1.csv',invalid)],data_folder)
    assert path.read_bytes()==original


def test_zip_traversal_rejected():
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('../games.csv','gameId\n1')
    with pytest.raises(DataError,match='unsafe'):
        unpack_inputs([('bad.zip',buffer.getvalue())])


def test_missing_schema_and_duplicate_metadata_fail(data_folder):
    path=data_folder/'games.csv'
    df=pd.read_csv(path)
    pd.concat([df,df]).to_csv(path,index=False)
    with pytest.raises(DataError,match='duplicate'):
        load_metadata(data_folder)


def test_wrong_tracking_filename_is_rejected(data_folder,tmp_path):
    path=data_folder/'tracking/tracking_1.csv'
    path.rename(path.with_name('tracking_2.csv'))
    manifest=build_dataset(data_folder,tmp_path/'cache')
    assert not manifest['files']
    assert 'Filename' in manifest['errors'][0]['message']
