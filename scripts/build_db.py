"""
Builds openipf.duckdb from the raw OpenIPF CSV export.

Run once after downloading a new export:
    python scripts/build_db.py

Creates/overwrites data/openipf.duckdb with:
  - entries        : full raw dataset, lightly typed
  - rankings_raw   : precomputed top-15-per-weight-class leaderboard (Raw, SBD meets,
                     each lifter's best total per weight class in the last 2 years)
"""
import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "raw" / "openipf-2026-10-10-408a4d50.csv"
DB_PATH = ROOT / "data" / "openipf.duckdb"

# Current-day IPF senior/junior/sub-junior weight classes. Other values in the
# data are legacy classes, youth categories, or one-off data errors and are
# excluded from the leaderboard (they remain visible on individual lifter profiles).
WEIGHT_CLASSES = {
    "F": ["43", "47", "52", "57", "63", "69", "76", "84", "84+"],
    "M": ["53", "59", "66", "74", "83", "93", "105", "120", "120+"],
}


def inferred_class_sql(bodyweight_expr, sex_expr):
    """Some meets (e.g. Sheffield Powerlifting Championships) don't record a
    WeightClassKg at all, which would otherwise silently exclude real
    qualifying totals (including record-setting ones) from the leaderboard.
    Fall back to the IPF class implied by recorded bodyweight.

    When bodyweight is ALSO missing, there is nothing to infer from -- return
    NULL (excluding the row entirely via the valid_classes join) rather than
    falling through a bare CASE's ELSE, which would silently default every
    such row into the heaviest "+" class regardless of their actual size."""
    sex_cases = []
    for sex, classes in WEIGHT_CLASSES.items():
        thresholds, plus_label = classes[:-1], classes[-1]
        when_clauses = "\n".join(
            f"WHEN {bodyweight_expr} <= {t} THEN '{t}'" for t in thresholds
        )
        sex_cases.append(
            f"""WHEN {sex_expr} = '{sex}' THEN
                CASE WHEN {bodyweight_expr} IS NULL THEN NULL
                     {when_clauses}
                     ELSE '{plus_label}'
                END"""
        )
    return "CASE " + " ".join(sex_cases) + " END"


def main():
    DB_PATH.unlink(missing_ok=True)
    con = duckdb.connect(str(DB_PATH))

    print("Loading CSV into 'entries' table...")
    con.execute(f"""
        CREATE TABLE entries AS
        SELECT
            Name,
            trim(lower(Name))                      AS lifter_key,
            Sex,
            Event,
            Equipment,
            try_cast(Age AS DOUBLE)                AS age,
            AgeClass                                AS age_class,
            Division,
            try_cast(BodyweightKg AS DOUBLE)        AS bodyweight_kg,
            WeightClassKg                           AS weight_class_kg,
            try_cast(Best3SquatKg AS DOUBLE)        AS best_squat_kg,
            try_cast(Best3BenchKg AS DOUBLE)        AS best_bench_kg,
            try_cast(Best3DeadliftKg AS DOUBLE)     AS best_deadlift_kg,
            try_cast(TotalKg AS DOUBLE)             AS total_kg,
            Place                                   AS place,
            try_cast(Dots AS DOUBLE)                AS dots,
            try_cast(Wilks AS DOUBLE)                AS wilks,
            try_cast(Glossbrenner AS DOUBLE)        AS glossbrenner,
            try_cast(Goodlift AS DOUBLE)             AS goodlift,
            Tested                                   AS tested,
            Country                                  AS country,
            State                                    AS state,
            Federation                                AS federation,
            ParentFederation                          AS parent_federation,
            try_cast(Date AS DATE)                   AS meet_date,
            MeetCountry                               AS meet_country,
            MeetState                                 AS meet_state,
            MeetTown                                  AS meet_town,
            MeetName                                  AS meet_name
        FROM read_csv_auto(?, all_varchar=true)
    """, [str(CSV_PATH)])

    n = con.execute("select count(*) from entries").fetchone()[0]
    print(f"Loaded {n:,} rows.")

    print("Indexing...")
    con.execute("CREATE INDEX idx_entries_lifter ON entries(lifter_key)")
    con.execute("CREATE INDEX idx_entries_class ON entries(sex, weight_class_kg)")

    print("Building rankings_raw (each lifter's best Raw SBD meet in the last 2 years)...")
    classes_sql = " UNION ALL ".join(
        f"SELECT '{sex}' AS sex, '{wc}' AS weight_class_kg"
        for sex, classes in WEIGHT_CLASSES.items()
        for wc in classes
    )
    con.execute(f"""
        CREATE TABLE valid_classes AS {classes_sql}
    """)

    # Each lifter's best qualifying total in the last 2 years is what gets
    # ranked, computed independently PER WEIGHT CLASS -- not one single best
    # meet per lifter across all classes. A lifter who competes at more than
    # one class in the window legitimately shows up on each class's board
    # they qualify for; collapsing to one global-best meet previously locked
    # a lifter into whichever class they happened to be heaviest in, hiding
    # strong results in any other class they also competed at (most totals
    # scale with bodyweight, so the "global best" was almost always their
    # heaviest class). Ties on total fall back to the most recent of the
    # tied meets.
    effective_class = inferred_class_sql("e.bodyweight_kg", "e.sex")
    con.execute(f"""
        CREATE TABLE latest_per_lifter AS
        SELECT e.* EXCLUDE (weight_class_kg),
               COALESCE(NULLIF(trim(e.weight_class_kg), ''), {effective_class}) AS weight_class_kg
        FROM entries e
        JOIN valid_classes vc
          ON e.sex = vc.sex
         AND COALESCE(NULLIF(trim(e.weight_class_kg), ''), {effective_class}) = vc.weight_class_kg
        WHERE e.equipment = 'Raw'
          AND e.event = 'SBD'
          AND e.place != 'DQ'
          AND e.total_kg IS NOT NULL
          AND e.meet_date >= CURRENT_DATE - INTERVAL 2 YEAR
        QUALIFY row_number() OVER (
            PARTITION BY e.lifter_key, e.sex,
                         COALESCE(NULLIF(trim(e.weight_class_kg), ''), {effective_class})
            ORDER BY e.total_kg DESC, e.meet_date DESC
        ) = 1
    """)

    # No top-N cutoff here: the full "current" (most-recent-qualifying-meet)
    # ranking is kept for every lift so a lifter's rank can be looked up even
    # outside the top 15 shown on the public leaderboard (e.g. for the
    # in-app "#N current rank" badges, up to rank 100). The /api/rankings
    # endpoint applies the rank <= 15 cutoff itself when serving the leaderboard.
    con.execute("""
        CREATE TABLE rankings_raw AS
        SELECT
            sex,
            weight_class_kg,
            -- lifter_key as a final tiebreak makes every rank fully
            -- deterministic even for lifters tied on all of total/bodyweight
            -- /date (otherwise genuinely ambiguous ties could rank
            -- differently -- arbitrarily -- on every rebuild).
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY total_kg DESC, bodyweight_kg ASC, meet_date ASC, lifter_key ASC
            ) AS rank,
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY best_squat_kg DESC NULLS LAST, bodyweight_kg ASC, meet_date ASC, lifter_key ASC
            ) AS rank_squat,
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY best_bench_kg DESC NULLS LAST, bodyweight_kg ASC, meet_date ASC, lifter_key ASC
            ) AS rank_bench,
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY best_deadlift_kg DESC NULLS LAST, bodyweight_kg ASC, meet_date ASC, lifter_key ASC
            ) AS rank_deadlift,
            Name AS name,
            lifter_key,
            total_kg,
            best_squat_kg,
            best_bench_kg,
            best_deadlift_kg,
            bodyweight_kg,
            goodlift,
            wilks,
            federation,
            meet_date,
            meet_name
        FROM latest_per_lifter
        ORDER BY sex, weight_class_kg, rank
    """)

    con.execute("DROP TABLE valid_classes")
    con.execute("DROP TABLE latest_per_lifter")

    n_rank = con.execute("select count(*) from rankings_raw").fetchone()[0]
    print(f"rankings_raw built: {n_rank:,} rows.")

    con.close()
    print(f"Done. Database at {DB_PATH}")


if __name__ == "__main__":
    main()
