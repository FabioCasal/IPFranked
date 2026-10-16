from pathlib import Path
from typing import Optional

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "openipf.duckdb"
FRONTEND_DIR = ROOT / "frontend"

WEIGHT_CLASSES = {
    "F": ["43", "47", "52", "57", "63", "69", "76", "84", "84+"],
    "M": ["53", "59", "66", "74", "83", "93", "105", "120", "120+"],
}

app = FastAPI(title="IPFranked")


def db():
    return duckdb.connect(str(DB_PATH), read_only=True)


def population_percentile(sex, weight_class_kg, field, value, equipment="Raw", event=None):
    """Percentile of `value` among each lifter's personal best for `field`
    within the same sex + weight class (e.g. "beats 82% of 93kg lifters")."""
    if weight_class_kg is None or value is None:
        return None
    con = db()
    try:
        event_clause = "AND event = ?" if event else ""
        params = [sex, weight_class_kg, equipment]
        if event:
            params.append(event)
        rows = con.execute(
            f"""
            SELECT max({field}) AS best
            FROM entries
            WHERE sex = ? AND effective_weight_class_kg = ? AND equipment = ? AND place != 'DQ'
              AND {field} IS NOT NULL
              {event_clause}
            GROUP BY lifter_key
            """,
            params,
        ).fetchall()
    finally:
        con.close()
    bests = [r[0] for r in rows]
    n_total = len(bests)
    if n_total == 0:
        return None
    n_below = sum(1 for b in bests if b < value)
    # Truncate (not round) to 1 decimal so a near-the-top-but-not-#1 lifter
    # (e.g. 99.99%) never misleadingly displays as a flat 100.0%.
    percentile = int(1000 * n_below / n_total) / 10
    return {
        "percentile": percentile,
        "weight_class_kg": weight_class_kg,
        "n_lifters": n_total,
    }


def current_ranks_for(lifter_key):
    """Each lift's rank in the app's own current ranking system (best
    qualifying meet in the last 2 years), not an all-time historical rank.

    A lifter can have one rankings_raw row per weight class they've qualified
    in within the window, and the four lifts' bests don't have to all come
    from the same one -- e.g. their best-ranked squat and best-ranked total
    could be from different meets in different classes. So each lift picks
    its own best rank independently across all of that lifter's rows,
    rather than reading all four off a single arbitrarily-chosen row."""
    con = db()
    try:
        rows = con.execute(
            """
            SELECT weight_class_kg, rank, rank_squat, rank_bench, rank_deadlift,
                   total_kg, best_squat_kg, best_bench_kg, best_deadlift_kg
            FROM rankings_raw
            WHERE lifter_key = ?
            """,
            [lifter_key],
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return {"total": None, "squat": None, "bench": None, "deadlift": None}

    def badge(rank_idx, value_idx):
        candidates = [
            {"rank": r[rank_idx], "weight_class_kg": r[0]}
            for r in rows
            if r[rank_idx] is not None and r[value_idx] is not None and r[rank_idx] <= 100
        ]
        return min(candidates, key=lambda b: b["rank"]) if candidates else None

    return {
        "total": badge(1, 5),
        "squat": badge(2, 6),
        "bench": badge(3, 7),
        "deadlift": badge(4, 8),
    }


@app.get("/api/weight-classes")
def weight_classes(sex: str = Query(..., pattern="^[MF]$")):
    return {"sex": sex, "weight_classes": WEIGHT_CLASSES[sex]}


@app.get("/api/champions")
def champions():
    con = db()
    try:
        rows = con.execute(
            """
            SELECT sex AS sex, weight_class_kg, name, lifter_key, total_kg, best_squat_kg,
                   best_bench_kg, best_deadlift_kg, bodyweight_kg, goodlift, federation,
                   meet_date, meet_name
            FROM rankings_raw
            WHERE rank = 1
            """
        ).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()

    by_class = {(r["sex"], r["weight_class_kg"]): r for r in (dict(zip(cols, row)) for row in rows)}
    result = {
        sex: [by_class[(sex, wc)] for wc in classes if (sex, wc) in by_class]
        for sex, classes in WEIGHT_CLASSES.items()
    }
    return result


@app.get("/api/rankings")
def rankings(sex: str = Query(..., pattern="^[MF]$"), weight_class: str = Query(...)):
    if weight_class not in WEIGHT_CLASSES.get(sex, []):
        raise HTTPException(400, f"Invalid weight class '{weight_class}' for sex '{sex}'")
    con = db()
    try:
        rows = con.execute(
            """
            SELECT rank, name, lifter_key, total_kg, best_squat_kg, best_bench_kg,
                   best_deadlift_kg, bodyweight_kg, goodlift, wilks, federation,
                   meet_date, meet_name
            FROM rankings_raw
            WHERE sex = ? AND weight_class_kg = ? AND rank <= 15
            ORDER BY rank
            """,
            [sex, weight_class],
        ).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()
    return {"sex": sex, "weight_class": weight_class, "lifters": [dict(zip(cols, r)) for r in rows]}


@app.get("/api/lifters/search")
def search_lifters(q: str = Query(..., min_length=2), limit: int = 20):
    con = db()
    try:
        rows = con.execute(
            """
            SELECT any_value(Name) AS name, lifter_key, count(*) AS meet_count,
                   max(total_kg) AS best_total_kg, any_value(sex) AS sex
            FROM entries
            WHERE lifter_key LIKE '%' || lower(trim(?)) || '%'
            GROUP BY lifter_key
            ORDER BY meet_count DESC
            LIMIT ?
            """,
            [q, limit],
        ).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()
    return {"query": q, "results": [dict(zip(cols, r)) for r in rows]}


@app.get("/api/lifters/{lifter_key}")
def lifter_profile(lifter_key: str):
    con = db()
    try:
        meets = con.execute(
            """
            SELECT Name AS name, Sex AS sex, Event AS event, Equipment AS equipment,
                   age, age_class, Division AS division,
                   bodyweight_kg, weight_class_kg, effective_weight_class_kg, best_squat_kg, best_bench_kg,
                   best_deadlift_kg, total_kg, place, dots, wilks, glossbrenner,
                   goodlift, tested, federation, meet_date, meet_country, meet_state,
                   meet_town, meet_name
            FROM entries
            WHERE lifter_key = ?
            ORDER BY meet_date
            """,
            [lifter_key],
        ).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()

    if not meets:
        raise HTTPException(404, "Lifter not found")

    meets = [dict(zip(cols, r)) for r in meets]
    name = meets[-1]["name"]
    sex = meets[-1]["sex"]

    def best(field, equipment=None, event=None):
        vals = [
            m[field]
            for m in meets
            if m[field] is not None
            and (equipment is None or m["equipment"] == equipment)
            and (event is None or m["event"] == event)
        ]
        return max(vals) if vals else None

    def best_with_class(field, equipment=None, event=None):
        candidates = [
            m
            for m in meets
            if m[field] is not None
            and (equipment is None or m["equipment"] == equipment)
            and (event is None or m["event"] == event)
        ]
        if not candidates:
            return None, None
        top = max(candidates, key=lambda m: m[field])
        return top[field], top["effective_weight_class_kg"]

    total_val, total_wc = best_with_class("total_kg", equipment="Raw", event="SBD")
    squat_val, squat_wc = best_with_class("best_squat_kg", equipment="Raw")
    bench_val, bench_wc = best_with_class("best_bench_kg", equipment="Raw")
    deadlift_val, deadlift_wc = best_with_class("best_deadlift_kg", equipment="Raw")

    percentiles = {
        "total": population_percentile(sex, total_wc, "total_kg", total_val, event="SBD"),
        "squat": population_percentile(sex, squat_wc, "best_squat_kg", squat_val),
        "bench": population_percentile(sex, bench_wc, "best_bench_kg", bench_val),
        "deadlift": population_percentile(sex, deadlift_wc, "best_deadlift_kg", deadlift_val),
    }

    current_ranks = current_ranks_for(lifter_key)

    progression = [
        {
            "date": str(m["meet_date"]),
            "total_kg": m["total_kg"],
            "best_squat_kg": m["best_squat_kg"],
            "best_bench_kg": m["best_bench_kg"],
            "best_deadlift_kg": m["best_deadlift_kg"],
            "bodyweight_kg": m["bodyweight_kg"],
            "equipment": m["equipment"],
            "event": m["event"],
        }
        for m in meets
        if m["event"] == "SBD"
    ]

    weight_classes_seen = sorted(
        {m["effective_weight_class_kg"] for m in meets if m["effective_weight_class_kg"]}
    )
    federations = sorted({m["federation"] for m in meets if m["federation"]})

    return {
        "name": name,
        "sex": sex,
        "lifter_key": lifter_key,
        "meet_count": len(meets),
        "first_meet_date": str(meets[0]["meet_date"]),
        "last_meet_date": str(meets[-1]["meet_date"]),
        "weight_classes": weight_classes_seen,
        "federations": federations,
        "bests": {
            "total_kg_raw": total_val,
            "squat_kg_raw": squat_val,
            "bench_kg_raw": bench_val,
            "deadlift_kg_raw": deadlift_val,
            "total_kg_any": best("total_kg", event="SBD"),
            "squat_kg_any": best("best_squat_kg"),
            "bench_kg_any": best("best_bench_kg"),
            "deadlift_kg_any": best("best_deadlift_kg"),
            "goodlift": best("goodlift"),
            "dots": best("dots"),
        },
        "percentiles": percentiles,
        "current_ranks": current_ranks,
        "progression": progression,
        "meets": meets,
    }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
