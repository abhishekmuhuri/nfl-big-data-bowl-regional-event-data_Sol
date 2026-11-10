# Start Route Relay

## Windows: the simplest way

1. Download the repository: **Code → Download ZIP**, then extract the entire ZIP to a folder you can write to.
2. Install **Python 3.12 or newer** from [python.org](https://www.python.org/downloads/) if you do not have it. Select **Add Python to PATH** during installation.
3. Double-click **START_WINDOWS.bat** inside the extracted folder.
4. Leave its window open. Your browser will open at **http://localhost:8501**.

The launcher creates a private `.venv` environment and installs the required packages automatically. The first launch needs internet access and processes the supplied games once, which can take a few minutes. Subsequent launches reuse the processed data. The data folder is already included, so there is nothing else to download.

If the browser does not open automatically, enter `http://localhost:8501` yourself. Stop the application by pressing **Ctrl+C** in its launch window.

## macOS or Linux

Install Python 3.12 or newer, open a terminal in the extracted project folder, and run:

```sh
python3 start.py
```

On macOS, `START_MAC_LINUX.command` runs the same launcher when executable permissions are available. The terminal command works without changing those permissions.

## What to try first

The dashboard starts with Kansas City against Cover-1 and Cover-3. In **Team overview**, compare option coverage with beyond-sticks coverage: space somewhere on the field is much more common than separation beyond the first-down line. Read the player table to see which TEs and RBs supply a complementary option, then open **Play explorer** and inspect the same play's timeline and animated replay.

Change the team, week, coverage, down, distance, or formation in the sidebar. Leave formation empty to include every formation. In **Measurement settings**, change the separation threshold or minimum duration to see whether the interpretation survives a different definition. Each later time point uses only plays still observed at that time; a quick throw does not become a failed late window.

**Data & help** lets you import CSVs or ZIPs and download data-quality details. See [the pipeline guide](DATA_PIPELINE.md) for new games and automated feeds.

## Common problems

| Message or symptom | What to do |
| --- | --- |
| Python is not recognized / Microsoft Store opens | Install Python from python.org, enable Add Python to PATH, then reopen the launcher. |
| Package installation fails | Check internet access, your organization's Python package access, and the error in the launch window. Run `python start.py` again. |
| Port 8501 is already in use | Close the previous launch window or run `python start.py --port 8502`. |
| No analyzable plays | Broaden the filters and inspect data-quality details. Plays without a snap tag cannot be timed reliably. |
| Dataset changed | Use **Refresh data** if the dashboard has not already detected and processed the completed delivery. |
| Another import or rebuild is running | Let the other process finish. If a process crashed, close all Route Relay processing jobs before removing the leftover `data/.route-relay.lock` file. |
| Cannot write cache or virtual environment | Extract the ZIP to a writable folder in your user directory. |

## Reproduce the analysis directly

For users already comfortable with Python environments:

```sh
python -m pip install -r requirements.txt
python process_data.py
python -m streamlit run app.py
```

To produce a standalone interactive HTML snapshot and CSV evidence:

```sh
python export_report.py
```

Open `docs/index.html` in a browser. The same file powers the hosted demonstration. It is a reproducible snapshot; the Streamlit dashboard provides live filtering and imports.

## Testing and hosting

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
python scripts/verify_app.py
```

The tests cover hand-calculated windows, mirrored geometry, missing observations, terminal-event cutoffs, incremental rebuilding, rejected imports, and a new game supplied through JSON input. GitHub Actions runs the unit and pipeline tests on pushes and pull requests.

The hosted demonstration is served from `docs/` using GitHub Pages. To host the full Python dashboard, deploy `app.py` with `requirements.txt` to a Python/Streamlit host and provide writable cache storage. GitHub Pages serves static HTML and cannot run the Python application or retain new uploads.
