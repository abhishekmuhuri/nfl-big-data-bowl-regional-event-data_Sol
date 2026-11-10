"""Verify the included source CSV bytes and optionally compare with an original folder."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--write-manifest',action='store_true')
    args=parser.parse_args()
    data=ROOT/'data'
    files=sorted(data.rglob('*.csv'))
    records=[]
    for path in files:
        relative=path.relative_to(data).as_posix()
        sha=digest(path)
        if args.source:
            original=args.source/relative
            if not original.exists() or digest(original)!=sha:
                raise ValueError(f'Source mismatch: {relative}')
        records.append({'path':relative,'bytes':path.stat().st_size,'sha256':sha})
    payload={'description':'Bundled source CSV snapshot; new imports intentionally change this dataset.',
             'source':'https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data',
             'file_count':len(records),'bytes':sum(r['bytes'] for r in records),'files':records}
    manifest=data/'SOURCE_MANIFEST.json'
    if args.write_manifest:
        manifest.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    elif manifest.exists():
        expected=json.loads(manifest.read_text())
        if expected['files']!=records:
            raise ValueError('Dataset differs from the bundled snapshot. This is expected after importing new data.')
    print(json.dumps({'verified_csv_files':len(records),'bytes':payload['bytes'],'source_compared':bool(args.source)}))


if __name__=='__main__':
    main()
