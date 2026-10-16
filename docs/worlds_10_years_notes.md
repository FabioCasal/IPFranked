# "Worlds, 10 years later" post — working notes

Status as of 2026-10-16: **draft slides rendered, two open decisions** (see bottom).

## Files

- `scripts/social/make_worlds_10_years.py` — generates the carousel into
  `social/output/worlds_10_years/` (gitignored, so regenerate on each machine).
- `scripts/worlds_10_years_significance.py` — re-runs the significance checks below.

## Regenerating on a new machine

`data/raw/` and `data/openipf.duckdb` are gitignored, so:

1. Download the OpenIPF export into `data/raw/` and point `CSV_PATH` in
   `scripts/build_db.py` at it (current: `openipf-2026-10-10-408a4d50.csv`).
2. `python scripts/build_db.py`
3. `python scripts/social/make_worlds_10_years.py` (optional `--then 2016 --now 2026`)
4. `python scripts/worlds_10_years_significance.py`

Attempt stats read the raw CSV directly (individual attempts aren't stored in
the DB); a negative attempt weight = a miss.

## Current slides

0. **Title** — "WORLDS, 10 YEARS LATER", 2016 → 2026.
1. **Stronger** — winning total per class, 2016 vs 2026 (dumbbell chart), %
   change per class. Up in 13 of 14 shared classes (men's 59kg −1%).
   Callout: 93 lifters in 2026 beat the 2016 winning total in their class.
   Only classes held in both years (women's classes changed in 2019).
2. **Smarter** — 3rd attempts made 47.6% → 59.7%; bars for 1st/2nd/3rd
   attempts; tiles: all attempts 75.1% → 79.1%, 9/9 days 9.6% → 13.7%,
   bomb-outs 4.1% → 1.1%.
3. **Landslides** — classes won by 20kg+: 8 of 15 (2016) → 12 of 16 (2026);
   "Biggest win of 2026: 80kg+ — Austin Perkins, men's 74kg" (actual margin
   86.5kg; "80kg+" wording chosen deliberately).
4. **Outro** — standard follow CTA.

No photos yet — STYLE_GUIDE.md says solid background only. Adding a photo to
the title slide would need a new photo rule in the style guide (placement,
darkening for legibility, photographer credit) and permission from the
photographer/federation (no published IPF photo-usage policy found).

## Fact checks already done

- Perkins' 86.5kg is the biggest margin in **74kg** Worlds history (2013–2026)
  and the biggest of 2026, but **not** the biggest overall: Ray Williams 2018
  (98.5), Jesus Olivares 2023 (97.5) and 2021 (92.5), Bonica Brown 2016 (91)
  all won by more. Don't call it "biggest win ever".
- In 2016, men's 74kg was decided by 7.5kg (possible contrast line).
- 12 of 16 (75%) is the highest share of 20kg+ wins at any Classic Worlds in
  the data.

## Significance (from worlds_10_years_significance.py)

| Claim | Result | Verdict |
|---|---|---|
| Winning totals up 13/14 classes, mean +13% | sign test p=0.002, paired t=6.6 | solid |
| 3rd attempts 47.6% → 59.7% | +12 pts, 95% CI [+7, +17], p<0.001 | solid |
| All attempts 75% → 79% | +4 pts, CI [+1.4, +6.7], p≈0.002 | solid |
| Bomb-outs 4.1% → 1.1% | Fisher p=0.03 (only 8 vs 4 lifters) | marginal |
| 9/9 days 9.6% → 13.7% | Fisher p=0.18 | not significant |
| Landslides 8/15 → 12/16 | Fisher p=0.27; median margin p=0.37 | not significant |
| 2026 vs all other years pooled | 75% vs 48%, p=0.07 | borderline |

The 3rd-attempt rise is a **step change, not a steady climb**: ~45–51% every
year 2013–2023, then 57–60% in 2024–2026.

## Open decisions

1. **9/9 tile on the Smarter slide** — not significant. Suggested swap:
   "1st attempts: unchanged at 93%" (shows lifters aren't opening lighter;
   the gain is on the hard attempts).
2. **Landslides slide** — the 2016 → 2026 change could be chance. Suggested
   reframe: "2026: THE YEAR OF THE LANDSLIDE" (12 of 16 + Perkins) as a 2026
   highlight rather than evidence of a 10-year trend; drop or demote the
   2016 row.
