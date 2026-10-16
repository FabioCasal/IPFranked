# IPFranked

Personal project built on the [OpenIPF](https://www.openipf.org/data) data export: a
top-15-per-weight-class leaderboard (Raw, full power meets) plus a per-lifter dashboard
with career progression and full meet history.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Drop a fresh OpenIPF CSV export into `data/raw/` and update the `CSV_PATH` filename in
`scripts/build_db.py` if the export date/hash changes, then rebuild the database:

```
python scripts/build_db.py
```

This produces `data/openipf.duckdb`, which the API reads at request time.

## Run

```
.venv\Scripts\activate
uvicorn backend.main:app --reload --app-dir .
```

Open http://127.0.0.1:8000

## Notes / caveats

- Rankings are restricted to `Equipment = Raw`, `Event = SBD` (full power meets), and the
  current standard IPF weight classes. Other equipment categories (Single-ply, Wraps) and
  partial meets (bench-only, deadlift-only) are excluded from the leaderboard but still
  show up on a lifter's full meet history.
- Ranking metric is competition Total (kg), not IPF GL points. Each lifter is ranked by
  their **best** Raw/SBD total in the **last 2 years** (relative to today), not whichever
  meet happens to be most recent — so a lifter can't get bumped down in the standings by
  competing again and doing worse, but still ages out entirely once their best qualifying
  meet is more than 2 years old. This is computed **independently per weight class**: a
  lifter who competed at more than one class within the window shows up on every class's
  board they qualify for, rather than being locked into a single "best overall" class
  (which in practice was almost always whichever class they were heaviest in, since total
  scales with bodyweight — hiding real results in any lighter class they also competed at).
  Some meets (e.g. Sheffield Powerlifting Championships) don't record a weight class at
  all — for those, the class is inferred from the recorded bodyweight against the standard
  IPF thresholds, so real (including record-setting) totals aren't silently dropped for
  lacking that field.
- There is no stable lifter ID in the OpenIPF export — lifters are identified by name
  (OpenIPF already appends `#2`, `#3`, etc. to disambiguate known duplicate names), so two
  different people sharing an undetected identical name could be merged into one profile.
- Data is a snapshot (`openipf-2026-10-10`); rebuild the DB from a newer export to refresh.
