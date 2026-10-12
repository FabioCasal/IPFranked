"""Generates the Pound-for-Pound Top 15 (ranked by Dots) graphics for men
and women.

Usage:
    python scripts/social/make_p4p.py [--out-dir PATH]

See STYLE_GUIDE.md for the full visual spec.
"""
import argparse
import sys
from pathlib import Path

import duckdb
from PIL import Image, ImageDraw

from shared import (
    ACCENT, BADGE_DARK_TEXT, BG, BORDER, BRONZE, DB_PATH, DEFAULT_OUT_DIR,
    FONT_BOLD, FONT_REG, FONT_SEMIBOLD, GOLD, H, PANEL, PANEL_2, SILVER,
    TEXT, TEXT_DIM, W, draw_inline_wordmark, draw_mixed_text, fit_size, font,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_db import inferred_class_sql  # noqa: E402


def fetch_p4p_rows(sex, limit=15):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    effective_class = inferred_class_sql("e.bodyweight_kg", "e.sex")
    rows = con.execute(
        f"""
        with best_dots_per_lifter as (
            select e.*,
                   COALESCE(NULLIF(trim(e.weight_class_kg), ''), {effective_class}) AS effective_class
            from entries e
            where e.sex = ?
              and e.equipment = 'Raw'
              and e.event = 'SBD'
              and e.place != 'DQ'
              and e.dots is not null
              and e.meet_date >= current_date - interval 2 year
            qualify row_number() over (
                partition by e.lifter_key
                order by e.dots desc, e.meet_date asc
            ) = 1
        ),
        ranked as (
            select
                row_number() over (order by dots desc, meet_date asc) as rank,
                name, effective_class as weight_class_kg, bodyweight_kg, meet_date, total_kg, dots
            from best_dots_per_lifter
        )
        select * from ranked where rank <= ? order by rank
        """,
        [sex, limit],
    ).fetchall()
    con.close()
    return rows


def build_p4p_graphic(sex, label, out_path):
    rows = fetch_p4p_rows(sex)
    n = len(rows)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    margin_x = 40

    # ---------- Header ----------
    f_sub = font(FONT_SEMIBOLD, 28)
    wm_y = 62
    draw_inline_wordmark(draw, (margin_x, wm_y), size=50)
    draw.text((margin_x, wm_y + 54), label.upper(), font=f_sub, fill=TEXT_DIM, anchor="lm")

    header_bottom = wm_y + 92
    draw.line([(margin_x, header_bottom), (W - margin_x, header_bottom)], fill=BORDER, width=2)

    # ---------- Column layout ----------
    rank_col_x = margin_x + 22
    name_col_x = margin_x + 58

    gap = 26
    dots_x = W - margin_x
    total_x = dots_x - 120 - gap
    date_x = total_x - 110 - gap
    bw_x = date_x - 150 - gap
    class_x = bw_x - 85 - gap

    name_right_limit = class_x - 90 - gap

    # ---------- Table ----------
    table_top = header_bottom + 28
    col_header_h = 44
    available_h = H - table_top - col_header_h - 70
    row_h = available_h / n

    f_colhead = font(FONT_SEMIBOLD, 17)
    y = table_top + col_header_h / 2
    draw.text((rank_col_x, y), "#", font=f_colhead, fill=TEXT_DIM, anchor="mm")
    draw.text((name_col_x, y), "LIFTER", font=f_colhead, fill=TEXT_DIM, anchor="lm")
    draw.text((class_x, y), "CLASS", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((bw_x, y), "BW", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((date_x, y), "DATE", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((total_x, y), "TOTAL", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((dots_x, y), "DOTS", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.line(
        [(0, table_top + col_header_h), (W, table_top + col_header_h)],
        fill=BORDER, width=2,
    )

    f_dots = font(FONT_BOLD, 26)        # headline metric for P4P
    f_total = font(FONT_SEMIBOLD, 22)   # secondary metric
    f_num = font(FONT_REG, 22)
    f_badge = font(FONT_BOLD, 20)

    badge_r = 20
    badge_colors = {1: (GOLD, BADGE_DARK_TEXT), 2: (SILVER, BADGE_DARK_TEXT), 3: (BRONZE, BADGE_DARK_TEXT)}

    row_top = table_top + col_header_h
    for i, (rank, name, weight_class_kg, bw_kg, meet_date, total_kg, dots) in enumerate(rows):
        y0 = row_top + i * row_h
        y1 = y0 + row_h
        row_fill = PANEL if i % 2 == 0 else PANEL_2
        draw.rectangle([(0, y0), (W, y1)], fill=row_fill)

        cy = (y0 + y1) / 2

        bg_color, fg_color = badge_colors.get(rank, (PANEL_2, TEXT_DIM))
        draw.ellipse(
            [(rank_col_x - badge_r, cy - badge_r), (rank_col_x + badge_r, cy + badge_r)],
            fill=bg_color,
        )
        draw.text((rank_col_x, cy), str(rank), font=f_badge, fill=fg_color, anchor="mm")

        display_name = name.split(" #")[0] if " #" in name else name
        max_name_w = name_right_limit - name_col_x
        name_size = fit_size(draw, display_name, FONT_SEMIBOLD, 25, 16, max_name_w)
        draw_mixed_text(draw, (name_col_x, cy), display_name, FONT_SEMIBOLD, name_size, TEXT, anchor="lm")

        draw.text((class_x, cy), f"{weight_class_kg}kg", font=f_num, fill=TEXT_DIM, anchor="rm")
        draw.text((bw_x, cy), f"{bw_kg:.1f}", font=f_num, fill=TEXT_DIM, anchor="rm")
        date_str = f"{meet_date:%b} {meet_date.day}, {meet_date.year}"
        draw.text((date_x, cy), date_str, font=f_num, fill=TEXT_DIM, anchor="rm")

        draw.text((total_x, cy), f"{total_kg:.1f}", font=f_total, fill=TEXT, anchor="rm")
        draw.text((dots_x, cy), f"{dots:.1f}", font=f_dots, fill=ACCENT, anchor="rm")

        if i < n - 1:
            draw.line([(0, y1), (W, y1)], fill=BORDER, width=1)

    table_bottom = row_top + n * row_h

    f_footer = font(FONT_REG, 19)
    footer_y = table_bottom + 34
    draw.text(
        (margin_x, footer_y),
        "data provided by Open IPF",
        font=f_footer, fill=TEXT_DIM, anchor="lm",
    )

    img.save(out_path)
    print("saved", out_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    build_p4p_graphic("M", "Men's Pound-for-Pound — Top 15 by Dots", out_dir / "p4p_men_top15.png")
    build_p4p_graphic("F", "Women's Pound-for-Pound — Top 15 by Dots", out_dir / "p4p_women_top15.png")


if __name__ == "__main__":
    main()
