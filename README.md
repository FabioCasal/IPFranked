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
  their **most recent** Raw/SBD meet in the **last 2 years** (relative to today), not
  their career-best total — so the leaderboard reflects current form, and a lifter drops
  off entirely once their last qualifying meet is more than 2 years old. A meet with no
  reported weight class is skipped in favor of the lifter's next most recent one that has
  one.
- There is no stable lifter ID in the OpenIPF export — lifters are identified by name
  (OpenIPF already appends `#2`, `#3`, etc. to disambiguate known duplicate names), so two
  different people sharing an undetected identical name could be merged into one profile.
- Data is a snapshot (`openipf-2026-08-29`); rebuild the DB from a newer export to refresh.
