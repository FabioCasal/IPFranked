"""Significance checks for the claims in the "Worlds, 10 years later" carousel
(scripts/social/make_worlds_10_years.py), 2016 vs 2026.

Usage:
    python scripts/worlds_10_years_significance.py

Worlds results are a full population, not a sample, so "significant" here means
"bigger than normal year-to-year variation". Attempt tests resample whole
lifters (cluster bootstrap) because one lifter's 9 attempts aren't independent.
Plain-Python stats (no scipy dependency).
"""
import math
import random
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import CSV_PATH, DB_PATH  # noqa: E402

CSV = CSV_PATH.as_posix()
DB = str(DB_PATH)
random.seed(1)
B = 20000


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def two_prop(x1, n1, x2, n2):
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (x2 / n2 - x1 / n1) / se
    return z, 2 * norm_sf(abs(z))


def fisher_two_sided(a, b, c, d):
    """2x2 [[a,b],[c,d]] Fisher exact, two-sided (sum of tables as or less likely)."""
    r1, c1, n = a + b, a + c, a + b + c + d
    def pr(x):
        return math.comb(r1, x) * math.comb(n - r1, c1 - x) / math.comb(n, c1)
    p0 = pr(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p0 * (1 + 1e-9))


con = duckdb.connect()
con.execute(f"""CREATE TABLE w AS SELECT *, year(CAST(Date AS DATE)) y FROM read_csv_auto('{CSV}', all_varchar=true)
  WHERE Event='SBD' AND Equipment='Raw' AND Federation='IPF' AND MeetName='World Classic Powerlifting Championships' AND Division='Open'""")
kg = lambda c: f"coalesce(try_cast({c} AS DOUBLE),0)"
cols = [f"{l}{n}Kg" for l in ("Squat", "Bench", "Deadlift") for n in (1, 2, 3)]

# Per-lifter attempt records so the bootstrap resamples lifters, not attempts
# (one lifter's 9 attempts aren't independent of each other).
rows = con.execute(f"SELECT y, row_number() OVER () id, {', '.join(kg(c) for c in cols)} FROM w").fetchall()
lifters = {}
for y, _id, *a in rows:
    third = [v for i, v in enumerate(a) if i % 3 == 2 and v != 0]
    taken = [v for v in a if v != 0]
    lifts = [a[i:i + 3] for i in (0, 3, 6)]
    bombed = any(any(v != 0 for v in L) and not any(v > 0 for v in L) for L in lifts)
    lifters.setdefault(y, []).append({
        "t3": (sum(v > 0 for v in third), len(third)),
        "all": (sum(v > 0 for v in taken), len(taken)),
        "nine": sum(v > 0 for v in a) == 9,
        "bomb": bombed,
    })


def rate(group, key):
    m = sum(l[key][0] for l in group); n = sum(l[key][1] for l in group)
    return m / n, m, n


def cluster_boot_diff(key, y1=2016, y2=2026):
    g1, g2 = lifters[y1], lifters[y2]
    obs = rate(g2, key)[0] - rate(g1, key)[0]
    diffs = []
    for _ in range(B):
        s1 = [random.choice(g1) for _ in g1]; s2 = [random.choice(g2) for _ in g2]
        diffs.append(rate(s2, key)[0] - rate(s1, key)[0])
    diffs.sort()
    lo, hi = diffs[int(0.025 * B)], diffs[int(0.975 * B)]
    p = 2 * min(sum(d <= 0 for d in diffs), sum(d >= 0 for d in diffs)) / B
    return obs, lo, hi, max(p, 1 / B)


print("=== 1. Attempt accuracy (2016 vs 2026) ===")
for key, label in (("t3", "3rd attempts"), ("all", "all attempts")):
    r1, m1, n1 = rate(lifters[2016], key); r2, m2, n2 = rate(lifters[2026], key)
    z, p = two_prop(m1, n1, m2, n2)
    obs, lo, hi, pb = cluster_boot_diff(key)
    print(f"{label}: {r1:.1%} (n={n1}) -> {r2:.1%} (n={n2}); naive z={z:.2f} p={p:.2g}; "
          f"lifter-clustered bootstrap diff {obs:+.1%} 95% CI [{lo:+.1%}, {hi:+.1%}] p~{pb:.2g}")
for key, label in (("nine", "9/9 days"), ("bomb", "bomb-outs")):
    a = sum(l[key] for l in lifters[2016]); n1 = len(lifters[2016])
    c = sum(l[key] for l in lifters[2026]); n2 = len(lifters[2026])
    print(f"{label}: {a}/{n1} ({a/n1:.1%}) -> {c}/{n2} ({c/n2:.1%}); Fisher exact p={fisher_two_sided(a, n1 - a, c, n2 - c):.3f}")

# Is 2016 -> 2026 a trend or just two noisy years? Year-level 3rd-attempt rate over every Worlds.
print("\n=== 1b. 3rd-attempt rate, every Worlds year ===")
yr = sorted(lifters)
series = [(y, rate(lifters[y], "t3")[0]) for y in yr]
print(", ".join(f"{y}: {r:.1%}" for y, r in series))
def slope(pts):
    xs, ys = zip(*pts); mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x in xs)
obs = slope(series)
ys = [r for _, r in series]
perm = sum(abs(slope(list(zip(yr, random.sample(ys, len(ys)))))) >= abs(obs) for _ in range(B)) / B
print(f"linear trend {obs*100:+.2f} pts/yr, permutation p={max(perm, 1/B):.4f}")

print("\n=== 2. Winning totals up in 13 of 14 classes ===")
db = duckdb.connect(DB, read_only=True)
W = ("event='SBD' AND equipment='Raw' AND place!='DQ' AND total_kg>0 AND federation='IPF' "
     "AND meet_name='World Classic Powerlifting Championships' AND Division='Open'")
gold = db.execute(f"""SELECT year(meet_date) y, sex, effective_weight_class_kg wc, max(total_kg) FROM entries WHERE {W}
  GROUP BY ALL""").fetchall()
G = {(y, s, c): t for y, s, c, t in gold}
pairs = [(G[(2016, s, c)], G[(2026, s, c)]) for (y, s, c) in G if y == 2016 and (2026, s, c) in G]
k = sum(b > a for a, b in pairs); n = len(pairs)
sign_p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n * 2
ch = [b / a - 1 for a, b in pairs]; m = sum(ch) / n; sd = math.sqrt(sum((x - m) ** 2 for x in ch) / (n - 1))
print(f"{k}/{n} up; two-sided sign test p={sign_p:.4f}; mean change {m:+.1%}, paired t={m/(sd/math.sqrt(n)):.1f} (df={n-1})")

print("\n=== 3. Classes won by 20kg+ ===")
rk = db.execute(f"""SELECT y, sex, wc, max(CASE WHEN r=1 THEN t END) - max(CASE WHEN r=2 THEN t END) FROM (
  SELECT year(meet_date) y, sex, effective_weight_class_kg wc, total_kg t,
         row_number() OVER (PARTITION BY year(meet_date), sex, effective_weight_class_kg ORDER BY total_kg DESC, bodyweight_kg) r
  FROM entries WHERE {W}) GROUP BY y, sex, wc HAVING count(*) >= 2""").fetchall()
by_year = {}
for y, s, c, mg in rk:
    by_year.setdefault(y, []).append(mg)
a = sum(v >= 20 for v in by_year[2016]); n1 = len(by_year[2016])
c = sum(v >= 20 for v in by_year[2026]); n2 = len(by_year[2026])
print(f"2016 {a}/{n1} vs 2026 {c}/{n2}: Fisher exact p={fisher_two_sided(a, n1 - a, c, n2 - c):.3f}")
other = [(y, sum(v >= 20 for v in m), len(m)) for y, m in sorted(by_year.items()) if y != 2026]
oa = sum(x for _, x, _ in other); on = sum(n for _, _, n in other)
print(f"2026 {c}/{n2} vs all other years pooled {oa}/{on} ({oa/on:.0%}): Fisher exact p={fisher_two_sided(oa, on - oa, c, n2 - c):.3f}")
# Median margin 2016 vs 2026 -- permutation test on the median difference
m16, m26 = by_year[2016], by_year[2026]
def med(x):
    s = sorted(x); n = len(s); return (s[n // 2] + s[(n - 1) // 2]) / 2
obs = med(m26) - med(m16); pool = m16 + m26
cnt = 0
for _ in range(B):
    random.shuffle(pool)
    if abs(med(pool[len(m16):]) - med(pool[:len(m16)])) >= abs(obs): cnt += 1
print(f"median margin {med(m16)} -> {med(m26)} kg; permutation p={cnt/B:.3f}")
