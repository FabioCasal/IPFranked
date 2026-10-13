"""Independently re-derives rankings_raw from entries and diffs the result,
to catch ranking-logic regressions (e.g. the tiebreak, most-recent-vs-best,
missing-weight-class, and global-vs-per-class bugs fixed in this project's
history) automatically instead of relying on manually spotting them.

Deliberately does NOT reuse build_db.py's SQL (same window-function logic
re-run would just reproduce the same bug if one exists there) -- this
recomputes everything in plain Python from the raw `entries` table.

Run after every `python scripts/build_db.py`:
    python scripts/validate_rankings.py

Exits 0 if everything matches, 1 (with a diff report) otherwise.
"""
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

# Lifter names can contain characters outside the Windows console's default
# codepage (e.g. CJK, accented Latin) -- never let a print() crash the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "openipf.duckdb"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import WEIGHT_CLASSES  # noqa: E402

MAX_EXAMPLES = 15


def classify(sex, bodyweight_kg):
    """Independent reimplementation of build_db.py's inferred_class_sql, in
    plain Python, for bodyweight-based class fallback."""
    classes = WEIGHT_CLASSES[sex]
    thresholds, plus_label = classes[:-1], classes[-1]
    for t in thresholds:
        if bodyweight_kg <= float(t):
            return t
    return plus_label


def effective_class(sex, raw_class, bodyweight_kg):
    raw_class = (raw_class or "").strip()
    if raw_class:
        return raw_class
    if bodyweight_kg is None:
        return None
    return classify(sex, bodyweight_kg)


def load_qualifying_entries(con):
    rows = con.execute(
        """
        SELECT lifter_key, Sex AS sex, weight_class_kg, bodyweight_kg, total_kg,
               best_squat_kg, best_bench_kg, best_deadlift_kg, meet_date
        FROM entries
        WHERE Equipment = 'Raw' AND Event = 'SBD' AND place != 'DQ'
          AND total_kg IS NOT NULL
          AND meet_date >= CURRENT_DATE - INTERVAL 2 YEAR
        """
    ).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def representative_row_per_lifter_class(entries):
    """build_db.py's latest_per_lifter keeps exactly ONE row per
    (lifter_key, sex, class) -- the one with the best total_kg (ties: most
    recent date) -- and ALL FOUR lift rank columns (rank, rank_squat,
    rank_bench, rank_deadlift) are computed from that SAME row. It is not
    each lift's own independently-best meet. Mirror that here exactly."""
    groups = defaultdict(list)
    for e in entries:
        cls = effective_class(e["sex"], e["weight_class_kg"], e["bodyweight_kg"])
        if cls is None or cls not in WEIGHT_CLASSES[e["sex"]]:
            continue
        groups[(e["lifter_key"], e["sex"], cls)].append(e)

    best = {}
    for key, rows in groups.items():
        rows.sort(key=lambda e: (-e["total_kg"], -e["meet_date"].toordinal()))
        best[key] = rows[0]
    return best


def expected_best_per_lifter_class(entries, lift_field):
    rep_rows = representative_row_per_lifter_class(entries)
    return {key: row for key, row in rep_rows.items() if row[lift_field] is not None}


def expected_ranks(best_by_key, lift_field):
    """rank per (sex, class), 1-indexed, ties broken by bodyweight asc then
    meet_date asc -- same tiebreak build_db.py applies. DuckDB's default ASC
    ordering puts NULL last, not first -- a missing bodyweight must sort as
    "heaviest", not as a 0kg tiebreak winner."""
    by_class = defaultdict(list)
    for (lifter_key, sex, cls), row in best_by_key.items():
        by_class[(sex, cls)].append((lifter_key, row))

    def bw_key(row):
        bw = row["bodyweight_kg"]
        return float("inf") if bw is None else bw

    ranks = {}
    for (sex, cls), lifters in by_class.items():
        lifters.sort(key=lambda lr: (-lr[1][lift_field], bw_key(lr[1]), lr[1]["meet_date"], lr[0]))
        for i, (lifter_key, row) in enumerate(lifters, start=1):
            ranks[(lifter_key, sex, cls)] = i
    return ranks


def check_lift(con, entries, lift_field, rank_col, label, failures):
    expected_best = expected_best_per_lifter_class(entries, lift_field)
    expected_rank = expected_ranks(expected_best, lift_field)

    actual = con.execute(
        f"""
        SELECT lifter_key, sex, weight_class_kg, {lift_field}, {rank_col}
        FROM rankings_raw
        WHERE {lift_field} IS NOT NULL
        """
    ).fetchall()
    actual_by_key = {(r[0], r[1], r[2]): (r[3], r[4]) for r in actual}

    expected_keys = set(expected_best.keys())
    actual_keys = set(actual_by_key.keys())

    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    mismatched_value = []
    mismatched_rank = []
    for key in expected_keys & actual_keys:
        exp_value = expected_best[key][lift_field]
        act_value, act_rank = actual_by_key[key]
        if abs(exp_value - act_value) > 1e-6:
            mismatched_value.append((key, exp_value, act_value))
        elif expected_rank[key] != act_rank:
            mismatched_rank.append((key, expected_rank[key], act_rank))

    ok = not (missing or extra or mismatched_value or mismatched_rank)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}: {len(expected_keys)} expected (lifter, sex, class) entries")

    if not ok:
        failures.append(label)
        if missing:
            print(f"  {len(missing)} missing from rankings_raw (present in entries, absent from output). Examples:")
            for key in list(missing)[:MAX_EXAMPLES]:
                print(f"    {key} -> expected {lift_field}={expected_best[key][lift_field]}")
        if extra:
            print(f"  {len(extra)} extra in rankings_raw (not independently derivable from entries). Examples:")
            for key in list(extra)[:MAX_EXAMPLES]:
                print(f"    {key} -> actual {lift_field}={actual_by_key[key][0]}")
        if mismatched_value:
            print(f"  {len(mismatched_value)} value mismatches. Examples:")
            for key, exp, act in mismatched_value[:MAX_EXAMPLES]:
                print(f"    {key}: expected {exp}, got {act}")
        if mismatched_rank:
            print(f"  {len(mismatched_rank)} rank mismatches. Examples:")
            for key, exp, act in mismatched_rank[:MAX_EXAMPLES]:
                print(f"    {key}: expected rank {exp}, got {act}")

    return ok


def check_no_duplicates(con, failures):
    rows = con.execute(
        """
        SELECT sex, weight_class_kg, lifter_key, count(*) as n
        FROM rankings_raw
        GROUP BY sex, weight_class_kg, lifter_key
        HAVING count(*) > 1
        """
    ).fetchall()
    ok = not rows
    print(f"[{'PASS' if ok else 'FAIL'}] no duplicate (sex, weight_class, lifter) rows")
    if not ok:
        failures.append("no_duplicates")
        for r in rows[:MAX_EXAMPLES]:
            print(f"    {r}")
    return ok


def check_valid_classes(con, failures):
    rows = con.execute("SELECT DISTINCT sex, weight_class_kg FROM rankings_raw").fetchall()
    bad = [r for r in rows if r[1] not in WEIGHT_CLASSES.get(r[0], [])]
    ok = not bad
    print(f"[{'PASS' if ok else 'FAIL'}] every weight_class_kg in rankings_raw is a recognized IPF class")
    if not ok:
        failures.append("valid_classes")
        for r in bad:
            print(f"    unrecognized: {r}")
    return ok


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    entries = load_qualifying_entries(con)
    print(f"Loaded {len(entries):,} qualifying entries (Raw, SBD, non-DQ, last 2 years).\n")

    failures = []
    check_no_duplicates(con, failures)
    check_valid_classes(con, failures)
    check_lift(con, entries, "total_kg", "rank", "Total", failures)
    check_lift(con, entries, "best_squat_kg", "rank_squat", "Squat", failures)
    check_lift(con, entries, "best_bench_kg", "rank_bench", "Bench", failures)
    check_lift(con, entries, "best_deadlift_kg", "rank_deadlift", "Deadlift", failures)

    con.close()

    print()
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
