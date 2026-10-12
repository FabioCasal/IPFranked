"""
Builds openipf.duckdb from the raw OpenIPF CSV export.

Run once after downloading a new export:
    python scripts/build_db.py

Creates/overwrites data/openipf.duckdb with:
  - entries        : full raw dataset, lightly typed
  - rankings_raw   : precomputed top-15-per-weight-class leaderboard (Raw, SBD meets,
                     each lifter's most recent meet in the last 2 years only)
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

    print("Building rankings_raw (each lifter's most recent Raw SBD meet in the last 2 years)...")
    classes_sql = " UNION ALL ".join(
        f"SELECT '{sex}' AS sex, '{wc}' AS weight_class_kg"
        for sex, classes in WEIGHT_CLASSES.items()
        for wc in classes
    )
    con.execute(f"""
        CREATE TABLE valid_classes AS {classes_sql}
    """)

    # Each lifter's single most recent qualifying meet in the last 2 years
    # (not their career-best total) is what gets ranked.
    con.execute("""
        CREATE TABLE latest_per_lifter AS
        SELECT e.*
        FROM entries e
        JOIN valid_classes vc
          ON e.sex = vc.sex AND e.weight_class_kg = vc.weight_class_kg
        WHERE e.equipment = 'Raw'
          AND e.event = 'SBD'
          AND e.place != 'DQ'
          AND e.total_kg IS NOT NULL
          AND e.meet_date >= CURRENT_DATE - INTERVAL 2 YEAR
        QUALIFY row_number() OVER (
            PARTITION BY e.lifter_key, e.sex
            ORDER BY e.meet_date DESC
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
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY total_kg DESC, bodyweight_kg ASC, meet_date ASC
            ) AS rank,
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY best_squat_kg DESC NULLS LAST, bodyweight_kg ASC, meet_date ASC
            ) AS rank_squat,
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY best_bench_kg DESC NULLS LAST, bodyweight_kg ASC, meet_date ASC
            ) AS rank_bench,
            row_number() OVER (
                PARTITION BY sex, weight_class_kg
                ORDER BY best_deadlift_kg DESC NULLS LAST, bodyweight_kg ASC, meet_date ASC
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
