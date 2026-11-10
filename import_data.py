"""Import CSVs, a dataset ZIP, or newline-delimited JSON batches safely."""
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import io
import json
import shutil
import sys
import zipfile
import pandas as pd
from pipeline import (TABLES, TRACKING_COLUMNS, DEFAULT_DATA, DataError, dataset_lock,
                      load_metadata, validate_table, validate_tracking, process_game)

MAX_UNPACKED_BYTES = 2_000_000_000


def classify(name):
    path = Path(name.replace('\\','/'))
    if path.name in {f'{n}.csv' for n in TABLES}:
        return path.name
    if path.name.startswith('tracking_') and path.suffix.lower() == '.csv':
        return 'tracking/' + path.name
    return None


def unpack_inputs(inputs):
    """Accept only known CSV filenames; never extract paths or execute ZIP contents."""
    result = {}
    total = 0
    for name,content in inputs:
        if name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    members = [m for m in archive.infolist() if not m.is_dir()]
                    if len(members) > 2000:
                        raise DataError('ZIP contains too many files (maximum 2,000).')
                    for member in members:
                        parts = member.filename.replace('\\','/').split('/')
                        if '..' in parts or member.filename.startswith(('/','\\')) or ':' in parts[0]:
                            raise DataError('ZIP contains an unsafe path.')
                        target = classify(member.filename)
                        if target is None:
                            continue
                        total += member.file_size
                        if total > MAX_UNPACKED_BYTES:
                            raise DataError('Import exceeds the 2 GB uncompressed limit.')
                        if target in result:
                            raise DataError(f'Duplicate imported filename: {target}')
                        result[target] = archive.read(member)
            except zipfile.BadZipFile as exc:
                raise DataError('The supplied ZIP is damaged or is not a ZIP file.') from exc
        else:
            target = classify(name)
            if target is None:
                raise DataError(f'Unsupported input: {name}. Use supporting CSVs, tracking_<gameId>.csv, or a ZIP.')
            total += len(content)
            if total > MAX_UNPACKED_BYTES:
                raise DataError('Import exceeds the 2 GB limit.')
            if target in result:
                raise DataError(f'Duplicate imported filename: {target}')
            result[target] = content
    if not result:
        raise DataError('No supported CSV files were found.')
    return result


def import_inputs(inputs, data_dir=DEFAULT_DATA):
    incoming = unpack_inputs(inputs)
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True,exist_ok=True)
    changed = []
    with dataset_lock(data_dir):
        with TemporaryDirectory(prefix='.import-',dir=data_dir.parent) as temp:
            stage = Path(temp)
            (stage/'tracking').mkdir()
            for name,(key,_) in TABLES.items():
                filename = f'{name}.csv'
                existing = data_dir/filename
                if filename in incoming:
                    fresh = validate_table(name,pd.read_csv(io.BytesIO(incoming[filename])))
                    if existing.exists():
                        old = pd.read_csv(existing)
                        fresh = pd.concat([old,fresh],ignore_index=True).drop_duplicates(key,keep='last')
                    validate_table(name,fresh).to_csv(stage/filename,index=False)
                    changed.append(filename)
                elif existing.exists():
                    shutil.copy2(existing,stage/filename)
                else:
                    raise DataError(f'A complete import needs {filename}.')
            metadata = load_metadata(stage)
            for name,content in incoming.items():
                if not name.startswith('tracking/'):
                    continue
                fresh = validate_tracking(pd.read_csv(io.BytesIO(content)),name)
                game = int(fresh.gameId.iloc[0])
                canonical = f'tracking/tracking_{game}.csv'
                if name != canonical:
                    raise DataError(f'{name} contains game {game}; name it {canonical}.')
                existing = data_dir/canonical
                if existing.exists():
                    old = pd.read_csv(existing)
                    fresh = pd.concat([old,fresh],ignore_index=True).drop_duplicates(['gameId','playId','frameId','nflId'],keep='last')
                fresh = validate_tracking(fresh,name)
                _,quality = process_game(fresh,metadata)
                structural = quality.reason.str.contains('Missing play metadata|participants differ|Expected 11|exactly 22',regex=True)
                if structural.any():
                    raise DataError(f'{name}: {quality.loc[structural,"reason"].iloc[0]}')
                fresh.to_csv(stage/canonical,index=False)
                changed.append(canonical)
            # Validation is complete before any destination file is replaced.
            # Readers use the same dataset lock while this multi-file publication runs.
            for name in changed:
                destination = data_dir/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                staged = destination.with_suffix(destination.suffix+'.importing')
                shutil.copyfile(stage/name,staged)
                staged.replace(destination)
    return changed


def read_json_batches(stream):
    """One JSON object per line: {table: games|plays|players|pffScoutingData|tracking, rows: [...]}.

    A finite batch is committed on EOF; use process_data.py --watch for ongoing feeds.
    """
    tables = {}
    for number,line in enumerate(stream,1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise DataError(f'Invalid JSON on line {number}.') from exc
        if item.get('table') not in {*TABLES,'tracking'} or not isinstance(item.get('rows'),list):
            raise DataError(f'Line {number} needs a supported table name and a rows array.')
        tables.setdefault(item['table'],[]).extend(item['rows'])
    inputs = []
    for table,rows in tables.items():
        df = pd.DataFrame(rows)
        if table == 'tracking':
            if 'gameId' not in df:
                raise DataError('Tracking JSON rows require gameId.')
            for game,part in df.groupby('gameId'):
                inputs.append((f'tracking_{int(game)}.csv',part.to_csv(index=False).encode()))
        else:
            inputs.append((f'{table}.csv',df.to_csv(index=False).encode()))
    return inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files',nargs='*',type=Path)
    parser.add_argument('--data-dir',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--stdin',action='store_true',help='Read finite NDJSON batches from standard input.')
    args = parser.parse_args()
    try:
        inputs = read_json_batches(sys.stdin) if args.stdin else [(p.name,p.read_bytes()) for p in args.files]
        changed = import_inputs(inputs,args.data_dir)
        print(json.dumps({'imported':changed,'next':'Run process_data.py or click Refresh data in the dashboard.'},indent=2))
    except (DataError,OSError,ValueError) as exc:
        print(f'Import failed: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
