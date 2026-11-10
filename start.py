"""One-command setup and launch; no virtual-environment commands needed."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3,12):
        print('Route Relay needs Python 3.12 or newer. Install it from https://www.python.org/downloads/.')
        return 1
    parser = argparse.ArgumentParser(description='Set up and launch Route Relay.')
    parser.add_argument('--port',type=int,default=8501)
    parser.add_argument('--headless',action='store_true',help='Do not open a browser automatically.')
    args = parser.parse_args()
    environment = ROOT/'.venv'
    python = environment/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('First run: creating an isolated Python environment…',flush=True)
        venv.create(environment,with_pip=True)
    digest = hashlib.sha256((ROOT/'requirements.txt').read_bytes()).hexdigest()
    stamp = ROOT/'.bootstrap.json'
    installed = json.loads(stamp.read_text()) if stamp.exists() else {}
    if installed.get('requirements') != digest:
        print('Installing dependencies. This step needs an internet connection…',flush=True)
        subprocess.run([str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True,cwd=ROOT)
        stamp.write_text(json.dumps({'requirements':digest}),encoding='utf-8')
    print(f'Opening Route Relay at http://localhost:{args.port}. Keep this window open; press Ctrl+C to stop.',flush=True)
    return subprocess.call([str(python),'-m','streamlit','run',str(ROOT/'app.py'),
                            '--server.address','127.0.0.1','--server.port',str(args.port),
                            '--server.headless',str(args.headless).lower()],cwd=ROOT)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'Could not start Route Relay: {exc}\nCheck your internet connection and see docs/GETTING_STARTED.md.')
        raise SystemExit(1)
