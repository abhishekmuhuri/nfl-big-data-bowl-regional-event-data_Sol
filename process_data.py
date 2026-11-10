"""Build or refresh the Route Relay feature cache, optionally watching a data feed."""
import argparse
import json
import sys
import time
from pathlib import Path
from pipeline import DEFAULT_DATA, DEFAULT_CACHE, DataError, build_dataset, inventory_signature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=DEFAULT_DATA)
    parser.add_argument('--cache-dir',type=Path,default=DEFAULT_CACHE)
    parser.add_argument('--fps',type=float,default=10.0)
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval',type=float,default=10.0)
    args = parser.parse_args()
    last = None
    try:
        while True:
            signature = inventory_signature(args.data_dir)
            if signature != last:
                result = build_dataset(args.data_dir,args.cache_dir,args.fps,args.force,
                    lambda i,n,name: print(f'[{i}/{n}] {name}',flush=True) if i % 10 == 0 or i == n else None)
                print(json.dumps({k:result[k] for k in ['built_at','rebuilt','reused','errors']},indent=2),flush=True)
                last = signature
                if result['errors'] and not args.watch:
                    return 1
            if not args.watch:
                break
            time.sleep(max(1,args.interval))
    except KeyboardInterrupt:
        print('Stopped watching.')
    except (DataError,OSError,ValueError) as exc:
        print(f'Cannot process dataset: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
