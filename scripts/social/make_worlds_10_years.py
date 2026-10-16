"""Generates the "Worlds, 10 years later" carousel: how IPF Classic Worlds (Open
division) changed between two editions -- by default 2016 vs 2026.

Slides (sorted by filename):
    0_title_10_years.png   hook title ("2016 -> 2026")
    1_stronger.png         winning total per weight class, then vs now
    2_smarter.png          attempt success: 3rd attempts, overall, 9/9 days, bomb-outs
    3_landslides.png       classes won by 20kg+, then vs now, plus the biggest win
    z_outro_follow.png     CTA

Usage:
    python scripts/social/make_worlds_10_years.py [--out-dir PATH] [--then 2016] [--now 2026]

Totals and margins come from data/openipf.duckdb. Individual attempts aren't
stored there, so the attempt slide reads the raw CSV export (build_db.CSV_PATH)
directly -- in OpenIPF a negative attempt weight is a miss.

See STYLE_GUIDE.md for the full visual spec.
"""
import argparse
import sys
from pathlib import Path

import duckdb
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_db import CSV_PATH  # noqa: E402

from make_title_slide import build_cta_slide  # noqa: E402
from shared import (  # noqa: E402
    ACCENT, BG, BORDER, DB_PATH, DEFAULT_OUT_DIR, FONT_BOLD, FONT_REG,
    FONT_SEMIBOLD, H, PANEL_2, TEXT, TEXT_DIM, W, centered_text,
    draw_inline_wordmark, draw_wordmark, font, save,
)

WORLDS_MEET = "World Classic Powerlifting Championships"
# Muted colour for the "then" year so the "now" figure stays the one headline.
MUTED = "#3a4150"
MARGIN_X = 40
LANDSLIDE_KG = 20

WORLDS_DB = (
    "event = 'SBD' AND equipment = 'Raw' AND place != 'DQ' AND total_kg > 0"
    f" AND federation = 'IPF' AND meet_name = '{WORLDS_MEET}' AND Division = 'Open'"
)
# Same filter against the raw CSV's column names. DQ entries are kept here:
# a bomb-out's missed attempts are part of the attempt record.
WORLDS_CSV = (
    "Event = 'SBD' AND Equipment = 'Raw' AND Federation = 'IPF'"
    f" AND MeetName = '{WORLDS_MEET}' AND Division = 'Open'"
)
LIFTS = ("Squat", "Bench", "Deadlift")


# ---------- Data ----------

def class_sort_key(wc):
    return float(wc.replace("+", ".5"))


def fetch_class_results(years):
    """{year: {(sex, class): (winner_name, gold_total, silver_total or None)}}."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute(
        f"""
        WITH ranked AS (
            SELECT year(meet_date) AS y, sex, effective_weight_class_kg AS wc, Name, total_kg,
                   row_number() OVER (
                       PARTITION BY year(meet_date), sex, effective_weight_class_kg
                       ORDER BY total_kg DESC, bodyweight_kg ASC
                   ) AS rk
            FROM entries
            WHERE {WORLDS_DB} AND year(meet_date) IN ({",".join("?" * len(years))})
        )
        SELECT y, sex, wc,
               max(CASE WHEN rk = 1 THEN Name END),
               max(CASE WHEN rk = 1 THEN total_kg END),
               max(CASE WHEN rk = 2 THEN total_kg END)
        FROM ranked GROUP BY y, sex, wc
        """,
        list(years),
    ).fetchall()
    con.close()
    out = {y: {} for y in years}
    for y, sex, wc, name, gold, silver in rows:
        out[y][(sex, wc)] = (name, gold, silver)
    return out


def count_beating(then_year, now_year):
    """How many lifters at the later Worlds beat the earlier winning total in their class."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    n = con.execute(
        f"""
        WITH gold AS (
            SELECT sex, effective_weight_class_kg AS wc, max(total_kg) AS t
            FROM entries WHERE {WORLDS_DB} AND year(meet_date) = ? GROUP BY ALL
        )
        SELECT count(*) FROM entries e JOIN gold g
          ON e.sex = g.sex AND e.effective_weight_class_kg = g.wc
        WHERE {WORLDS_DB} AND year(e.meet_date) = ? AND e.total_kg > g.t
        """,
        [then_year, now_year],
    ).fetchone()[0]
    con.close()
    return n


def fetch_attempt_stats(years):
    """Per year: make rate by attempt number and overall, 9/9 share, bomb-out share."""
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TABLE w AS
        SELECT *, year(CAST(Date AS DATE)) AS y
        FROM read_csv_auto(?, all_varchar = true)
        WHERE {WORLDS_CSV} AND year(CAST(Date AS DATE)) IN ({",".join("?" * len(years))})
        """,
        [str(CSV_PATH), *years],
    )

    def kg(col):
        return f"coalesce(try_cast({col} AS DOUBLE), 0)"

    # One row per attempt actually taken (blank / 0 = not attempted).
    union = " UNION ALL ".join(
        f"SELECT y, {n} AS n, {kg(f'{lift}{n}Kg')} > 0 AS good FROM w WHERE {kg(f'{lift}{n}Kg')} != 0"
        for lift in LIFTS for n in (1, 2, 3)
    )
    by_attempt = con.execute(
        f"SELECT y, n, avg(good::INT), count(*) FROM ({union}) GROUP BY y, n"
    ).fetchall()
    overall = con.execute(f"SELECT y, avg(good::INT), count(*) FROM ({union}) GROUP BY y").fetchall()

    made = " + ".join(f"({kg(f'{l}{n}Kg')} > 0)::INT" for l in LIFTS for n in (1, 2, 3))
    # Bombed = took at least one attempt on a lift and made none of them.
    bombed = " OR ".join(
        f"(({' OR '.join(f'{kg(f"{l}{n}Kg")} != 0' for n in (1, 2, 3))})"
        f" AND NOT ({' OR '.join(f'{kg(f"{l}{n}Kg")} > 0' for n in (1, 2, 3))}))"
        for l in LIFTS
    )
    lifters = con.execute(
        f"SELECT y, avg(({made} = 9)::INT), avg(({bombed})::INT), count(*) FROM w GROUP BY y"
    ).fetchall()
    con.close()

    stats = {y: {"by_attempt": {}} for y in years}
    for y, n, rate, cnt in by_attempt:
        stats[y]["by_attempt"][n] = rate
    for y, rate, cnt in overall:
        stats[y]["overall"], stats[y]["attempts"] = rate, cnt
    for y, nine, bomb, cnt in lifters:
        stats[y]["nine_for_nine"], stats[y]["bomb_out"], stats[y]["lifters"] = nine, bomb, cnt
    return stats


# ---------- Drawing helpers ----------

def new_slide(subtitle):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    wm_y = 62
    draw_inline_wordmark(draw, (MARGIN_X, wm_y), size=50)
    draw.text((MARGIN_X, wm_y + 54), subtitle.upper(), font=font(FONT_SEMIBOLD, 28), fill=TEXT_DIM, anchor="lm")
    header_bottom = wm_y + 92
    draw.line([(MARGIN_X, header_bottom), (W - MARGIN_X, header_bottom)], fill=BORDER, width=2)
    return img, draw, header_bottom


def wrap(draw, text, fnt, max_w):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def draw_footer(draw, note):
    """Methodology note + the standard 'data provided by Open IPF' credit."""
    f_note = font(FONT_REG, 18)
    lines = wrap(draw, note, f_note, W - 2 * MARGIN_X)
    y = H - 50 - 28 * len(lines) - 8
    for line in lines:
        draw.text((MARGIN_X, y), line, font=f_note, fill=TEXT_DIM, anchor="lm")
        y += 28
    draw.text((MARGIN_X, H - 50), "data provided by Open IPF", font=font(FONT_REG, 19), fill=TEXT_DIM, anchor="lm")


def draw_legend(draw, y, then_year, now_year):
    f_leg = font(FONT_SEMIBOLD, 26)
    x = MARGIN_X
    for label, color in ((str(then_year), MUTED), (str(now_year), ACCENT)):
        draw.ellipse([(x, y - 12), (x + 24, y + 12)], fill=color)
        draw.text((x + 36, y), label, font=f_leg, fill=TEXT, anchor="lm")
        x += 36 + draw.textlength(label, font=f_leg) + 44


def pct(rate):
    return f"{100 * rate:.1f}%"


def display_name(name):
    """Strip OpenIPF's duplicate-name suffix (' #1', ' #2', ...) for display."""
    return name.split(" #")[0]


# ---------- Slides ----------

def build_title(then_year, now_year, out_path):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw_wordmark(draw, H * 0.20, size=64)

    centered_text(draw, H * 0.37, "WORLDS,", font(FONT_BOLD, 104), TEXT)
    centered_text(draw, H * 0.37 + 118, "10 YEARS LATER", font(FONT_BOLD, 104), TEXT)

    f_year = font(FONT_BOLD, 150)
    f_arrow = font(FONT_BOLD, 110)
    cy = H * 0.62
    then_s, now_s, arrow = str(then_year), str(now_year), "→"
    gap = 36
    widths = [draw.textlength(s, font=f) for s, f in ((then_s, f_year), (arrow, f_arrow), (now_s, f_year))]
    x = (W - sum(widths) - 2 * gap) / 2
    for (s, f, color), w in zip(((then_s, f_year, TEXT_DIM), (arrow, f_arrow, TEXT_DIM), (now_s, f_year, ACCENT)), widths):
        draw.text((x, cy), s, font=f, fill=color, anchor="lm")
        x += w + gap

    centered_text(draw, H * 0.80, "Swipe to see how the sport changed  →", font(FONT_SEMIBOLD, 36), TEXT)
    centered_text(draw, H * 0.85, "IPF Classic Worlds · Raw · Open", font(FONT_REG, 24), TEXT_DIM)

    draw.text((MARGIN_X, H - 50), "data provided by Open IPF", font=font(FONT_REG, 19), fill=TEXT_DIM, anchor="lm")
    save(img, out_path)


def build_stronger(results, then_year, now_year, n_beating, out_path):
    """Dumbbell chart: winning total per class, then vs now, % change as the headline."""
    then, now = results[then_year], results[now_year]
    shared_classes = sorted(set(then) & set(now), key=lambda k: (k[0] != "F", class_sort_key(k[1])))
    changes = {k: now[k][1] / then[k][1] - 1 for k in shared_classes}
    n_up = sum(c > 0 for c in changes.values())

    img, draw, top = new_slide(f"Winning totals — {then_year} vs {now_year}")
    draw.text((W / 2, top + 70), "STRONGER", font=font(FONT_BOLD, 84), fill=TEXT, anchor="mm")
    draw.text((W / 2, top + 138), f"Winning totals went up in {n_up} of {len(shared_classes)} classes",
              font=font(FONT_SEMIBOLD, 34), fill=ACCENT, anchor="mm")
    draw_legend(draw, top + 205, then_year, now_year)

    label_w, pct_w = 120, 120
    px0, px1 = MARGIN_X + label_w, W - MARGIN_X - pct_w
    totals = [then[k][1] for k in shared_classes] + [now[k][1] for k in shared_classes]
    lo = (min(totals) // 100) * 100
    hi = (max(totals) // 100 + 1) * 100

    def sx(v):
        return px0 + (px1 - px0) * (v - lo) / (hi - lo)

    f_group = font(FONT_BOLD, 26)
    f_label = font(FONT_SEMIBOLD, 24)
    f_pct = font(FONT_BOLD, 28)
    groups = [("WOMEN", [k for k in shared_classes if k[0] == "F"]),
              ("MEN", [k for k in shared_classes if k[0] == "M"])]
    y = top + 250
    row_h, group_h = 40, 38
    chart_top = y
    for title, keys in groups:
        draw.text((MARGIN_X, y + group_h / 2), title, font=f_group, fill=TEXT_DIM, anchor="lm")
        y += group_h
        for k in keys:
            cy = y + row_h / 2
            draw.line([(px0, cy), (px1, cy)], fill=BORDER, width=1)
            x_then, x_now = sx(then[k][1]), sx(now[k][1])
            draw.line([(x_then, cy), (x_now, cy)], fill=ACCENT if x_now >= x_then else TEXT_DIM, width=6)
            draw.ellipse([(x_then - 11, cy - 11), (x_then + 11, cy + 11)], fill=MUTED, outline=BG, width=2)
            draw.ellipse([(x_now - 13, cy - 13), (x_now + 13, cy + 13)], fill=ACCENT, outline=BG, width=2)
            draw.text((MARGIN_X, cy), f"{k[1]}kg", font=f_label, fill=TEXT, anchor="lm")
            c = changes[k]
            draw.text((W - MARGIN_X, cy), f"{'+' if c >= 0 else '−'}{abs(100 * c):.0f}%", font=f_pct,
                      fill=ACCENT if c > 0 else TEXT_DIM, anchor="rm")
            y += row_h

    f_tick = font(FONT_REG, 20)
    for v in range(int(lo), int(hi) + 1, 200):
        draw.line([(sx(v), chart_top + group_h - 4), (sx(v), y)], fill=BORDER, width=1)
        draw.text((sx(v), y + 20), f"{v}kg", font=f_tick, fill=TEXT_DIM, anchor="mm")

    py0 = y + 46
    draw.rounded_rectangle([(MARGIN_X, py0), (W - MARGIN_X, py0 + 90)], radius=12, fill=PANEL_2)
    draw.text((W / 2, py0 + 45), f"{n_beating} lifters in {now_year} beat the {then_year} winning total in their class",
              font=font(FONT_SEMIBOLD, 30), fill=TEXT, anchor="mm")

    draw_footer(draw, f"Winning total per weight class at IPF Classic Worlds, Open division, raw full power. "
                      f"Only classes held in both {then_year} and {now_year} are shown (women's classes "
                      f"changed in 2019, adding 69kg and 76kg and dropping 72kg).")
    save(img, out_path)


def build_smarter(stats, then_year, now_year, out_path):
    t, n = stats[then_year], stats[now_year]
    img, draw, top = new_slide(f"Attempts made — {then_year} vs {now_year}")

    draw.text((W / 2, top + 70), "SMARTER", font=font(FONT_BOLD, 84), fill=TEXT, anchor="mm")
    draw.text((W / 2, top + 138), "Third attempts went from a coin flip to 3 in 5",
              font=font(FONT_SEMIBOLD, 34), fill=ACCENT, anchor="mm")

    # Headline figure: 3rd-attempt make rate, then -> now
    cy = top + 268
    f_then, f_arrow, f_now = font(FONT_BOLD, 96), font(FONT_BOLD, 72), font(FONT_BOLD, 120)
    parts = ((pct(t["by_attempt"][3]), f_then, TEXT_DIM), ("→", f_arrow, TEXT_DIM), (pct(n["by_attempt"][3]), f_now, ACCENT))
    gap = 28
    widths = [draw.textlength(s, font=f) for s, f, _ in parts]
    x = (W - sum(widths) - 2 * gap) / 2
    for (s, f, color), w in zip(parts, widths):
        draw.text((x, cy), s, font=f, fill=color, anchor="lm")
        x += w + gap
    draw.text((W / 2, cy + 86), "of third attempts made", font=font(FONT_SEMIBOLD, 30), fill=TEXT, anchor="mm")

    # Make rate by attempt number: 1st and 2nd barely move, the 3rd is the story.
    draw_legend(draw, cy + 160, then_year, now_year)
    bx0, bx1 = MARGIN_X + 150, W - MARGIN_X - 130
    bar_h, bar_gap = 30, 8
    y = cy + 205
    f_lab = font(FONT_SEMIBOLD, 26)
    f_val = font(FONT_SEMIBOLD, 24)
    for k, label in ((1, "1st"), (2, "2nd"), (3, "3rd")):
        draw.text((MARGIN_X, y + bar_h + bar_gap / 2), f"{label} attempt", font=f_lab, fill=TEXT, anchor="lm")
        for rate, color, vcolor, bold in ((t["by_attempt"][k], MUTED, TEXT_DIM, False),
                                          (n["by_attempt"][k], ACCENT, ACCENT, k == 3)):
            x1 = bx0 + (bx1 - bx0) * rate
            draw.rounded_rectangle([(bx0, y), (x1, y + bar_h)], radius=6, fill=color)
            draw.text((x1 + 12, y + bar_h / 2), pct(rate), font=font(FONT_BOLD, 26) if bold else f_val,
                      fill=vcolor, anchor="lm")
            y += bar_h + bar_gap
        y += 26

    # Supporting tiles
    tiles = (
        ("All attempts", pct(t["overall"]), pct(n["overall"])),
        ("9 for 9 days", pct(t["nine_for_nine"]), pct(n["nine_for_nine"])),
        ("Bomb-outs", pct(t["bomb_out"]), pct(n["bomb_out"])),
    )
    ty0, tile_h, tgap = y + 14, 150, 20
    tile_w = (W - 2 * MARGIN_X - 2 * tgap) / 3
    for i, (label, a, b) in enumerate(tiles):
        tx0 = MARGIN_X + i * (tile_w + tgap)
        draw.rounded_rectangle([(tx0, ty0), (tx0 + tile_w, ty0 + tile_h)], radius=12, fill=PANEL_2)
        mx = tx0 + tile_w / 2
        draw.text((mx, ty0 + 38), label.upper(), font=font(FONT_SEMIBOLD, 22), fill=TEXT_DIM, anchor="mm")
        draw.text((mx, ty0 + 98), f"{a} → {b}", font=font(FONT_BOLD, 34), fill=TEXT, anchor="mm")

    draw_footer(draw, f"Every 1st–3rd attempt by every Open lifter at IPF Classic Worlds, raw full power "
                      f"({t['attempts']:,} attempts in {then_year}, {n['attempts']:,} in {now_year}; "
                      f"4th record attempts excluded). Bomb-out = no good attempt on at least one lift.")
    save(img, out_path)


def build_landslides(results, then_year, now_year, out_path):
    def margins(year):
        return {k: g - s for k, (_, g, s) in results[year].items() if s is not None}

    m_then, m_now = margins(then_year), margins(now_year)
    big_then = sum(v >= LANDSLIDE_KG for v in m_then.values())
    big_now = sum(v >= LANDSLIDE_KG for v in m_now.values())
    top_key = max(m_now, key=m_now.get)
    top_name = display_name(results[now_year][top_key][0])
    top_margin = m_now[top_key]

    img, draw, top = new_slide(f"Winning margins — {then_year} vs {now_year}")
    draw.text((W / 2, top + 70), "LANDSLIDES", font=font(FONT_BOLD, 84), fill=TEXT, anchor="mm")
    draw.text((W / 2, top + 138), f"Classes won by {LANDSLIDE_KG}kg or more",
              font=font(FONT_SEMIBOLD, 34), fill=ACCENT, anchor="mm")

    # One square per class, filled when it was won by LANDSLIDE_KG+.
    y = top + 230
    sq, sq_gap = 46, 12
    for year, m, big, is_now in ((then_year, m_then, big_then, False), (now_year, m_now, big_now, True)):
        color = ACCENT if is_now else TEXT_DIM
        draw.text((MARGIN_X, y), str(year), font=font(FONT_BOLD, 40), fill=color, anchor="lm")
        draw.text((W - MARGIN_X, y), f"{big} of {len(m)}", font=font(FONT_BOLD, 64 if is_now else 52),
                  fill=color, anchor="rm")
        row_y = y + 52
        ordered = sorted(m.values(), reverse=True)
        for i, v in enumerate(ordered):
            x0 = MARGIN_X + i * (sq + sq_gap)
            if v >= LANDSLIDE_KG:
                draw.rounded_rectangle([(x0, row_y), (x0 + sq, row_y + sq)], radius=8,
                                       fill=ACCENT if is_now else MUTED)
            else:
                draw.rounded_rectangle([(x0, row_y), (x0 + sq, row_y + sq)], radius=8, outline=BORDER, width=3)
        y = row_y + sq + 90

    # Legend for the squares
    f_leg = font(FONT_REG, 24)
    draw.rounded_rectangle([(MARGIN_X, y - 50), (MARGIN_X + 24, y - 26)], radius=5, fill=ACCENT)
    draw.text((MARGIN_X + 36, y - 38), f"won by {LANDSLIDE_KG}kg+", font=f_leg, fill=TEXT_DIM, anchor="lm")
    lx = MARGIN_X + 36 + draw.textlength(f"won by {LANDSLIDE_KG}kg+", font=f_leg) + 40
    draw.rounded_rectangle([(lx, y - 50), (lx + 24, y - 26)], radius=5, outline=BORDER, width=3)
    draw.text((lx + 36, y - 38), "closer than that", font=f_leg, fill=TEXT_DIM, anchor="lm")

    # Biggest win of the later year
    py0 = y + 20
    panel_h = 300
    draw.rounded_rectangle([(MARGIN_X, py0), (W - MARGIN_X, py0 + panel_h)], radius=12, fill=PANEL_2)
    sex_word = "men's" if top_key[0] == "M" else "women's"
    draw.text((W / 2, py0 + 60), f"BIGGEST WIN OF {now_year}", font=font(FONT_SEMIBOLD, 26), fill=TEXT_DIM, anchor="mm")
    draw.text((W / 2, py0 + 140), f"{int(top_margin // 10 * 10)}kg+", font=font(FONT_BOLD, 110), fill=ACCENT, anchor="mm")
    draw.text((W / 2, py0 + 236), f"{top_name} · {sex_word.capitalize()} {top_key[1]}kg",
              font=font(FONT_SEMIBOLD, 32), fill=TEXT, anchor="mm")

    draw_footer(draw, f"Margin = winner's total minus runner-up's, per weight class, IPF Classic Worlds, "
                      f"Open division, raw full power ({len(m_then)} classes in {then_year}, "
                      f"{len(m_now)} in {now_year}).")
    save(img, out_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR / "worlds_10_years"))
    parser.add_argument("--then", type=int, default=2016)
    parser.add_argument("--now", type=int, default=2026)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    years = (args.then, args.now)
    results = fetch_class_results(years)
    build_title(args.then, args.now, out_dir / "0_title_10_years.png")
    build_stronger(results, args.then, args.now, count_beating(args.then, args.now), out_dir / "1_stronger.png")
    build_smarter(fetch_attempt_stats(years), args.then, args.now, out_dir / "2_smarter.png")
    build_landslides(results, args.then, args.now, out_dir / "3_landslides.png")
    build_cta_slide(out_dir / "z_outro_follow.png")


if __name__ == "__main__":
    main()
