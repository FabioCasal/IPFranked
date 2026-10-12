"""Generates the per-weight-class Top 15 leaderboard graphics.

Usage:
    python scripts/social/make_leaderboard.py [--out-dir PATH]

See STYLE_GUIDE.md for the full visual spec.
"""
import argparse
from pathlib import Path

import duckdb
from PIL import Image, ImageDraw

from shared import (
    ACCENT, BADGE_DARK_TEXT, BG, BORDER, BRONZE, DB_PATH, DEFAULT_OUT_DIR,
    FONT_BOLD, FONT_REG, FONT_SEMIBOLD, GOLD, H, PANEL, PANEL_2, SILVER,
    TEXT, TEXT_DIM, W, draw_inline_wordmark, draw_mixed_text, fit_size, font,
)

WEIGHT_CLASSES = {
    "F": ["43", "47", "52", "57", "63", "69", "76", "84", "84+"],
    "M": ["53", "59", "66", "74", "83", "93", "105", "120", "120+"],
}

SEX_LABEL = {"M": "Men's", "F": "Women's"}


def fetch_rows(sex, weight_class, limit=15):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute(
        """
        select r.rank, r.name, r.bodyweight_kg, r.meet_date, r.total_kg, e.dots
        from rankings_raw r
        join entries e
          on e.lifter_key = r.lifter_key
         and e.sex = r.sex
         and e.meet_date = r.meet_date
         and e.total_kg = r.total_kg
         and e.equipment = 'Raw' and e.event = 'SBD'
        where r.sex = ? and r.weight_class_kg = ? and r.rank <= ?
        qualify row_number() over (partition by r.rank order by e.dots desc) = 1
        order by r.rank
        """,
        [sex, weight_class, limit],
    ).fetchall()
    con.close()
    return rows


def build_graphic(sex, weight_class, label, out_path):
    rows = fetch_rows(sex, weight_class)
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

    # ---------- Column layout (right edges for numeric cols, right-aligned) ----------
    rank_col_x = margin_x + 22        # badge center
    name_col_x = margin_x + 58        # name left edge

    gap = 30
    dots_x = W - margin_x
    total_x = dots_x - 110 - gap
    date_x = total_x - 150 - gap
    bw_x = date_x - 190 - gap

    name_right_limit = bw_x - 110 - gap  # left boundary where name text must stop

    # ---------- Table ----------
    table_top = header_bottom + 28
    col_header_h = 44
    available_h = H - table_top - col_header_h - 70  # leave room for footer
    row_h = available_h / n

    f_colhead = font(FONT_SEMIBOLD, 17)
    y = table_top + col_header_h / 2
    draw.text((rank_col_x, y), "#", font=f_colhead, fill=TEXT_DIM, anchor="mm")
    draw.text((name_col_x, y), "LIFTER", font=f_colhead, fill=TEXT_DIM, anchor="lm")
    draw.text((bw_x, y), "BW", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((date_x, y), "DATE", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((total_x, y), "TOTAL", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.text((dots_x, y), "DOTS", font=f_colhead, fill=TEXT_DIM, anchor="rm")
    draw.line(
        [(0, table_top + col_header_h), (W, table_top + col_header_h)],
        fill=BORDER, width=2,
    )

    f_total = font(FONT_BOLD, 26)
    f_dots = font(FONT_SEMIBOLD, 24)
    f_num = font(FONT_REG, 22)
    f_badge = font(FONT_BOLD, 20)

    badge_r = 20
    badge_colors = {1: (GOLD, BADGE_DARK_TEXT), 2: (SILVER, BADGE_DARK_TEXT), 3: (BRONZE, BADGE_DARK_TEXT)}

    row_top = table_top + col_header_h
    for i, (rank, name, bw_kg, meet_date, total_kg, dots) in enumerate(rows):
        y0 = row_top + i * row_h
        y1 = y0 + row_h
        row_fill = PANEL if i % 2 == 0 else PANEL_2
        draw.rectangle([(0, y0), (W, y1)], fill=row_fill)

        cy = (y0 + y1) / 2

        # rank badge
        bg_color, fg_color = badge_colors.get(rank, (PANEL_2, TEXT_DIM))
        draw.ellipse(
            [(rank_col_x - badge_r, cy - badge_r), (rank_col_x + badge_r, cy + badge_r)],
            fill=bg_color,
        )
        draw.text((rank_col_x, cy), str(rank), font=f_badge, fill=fg_color, anchor="mm")

        # name (strip OpenIPF duplicate-name suffix like " #2"; shrink to fit column)
        display_name = name.split(" #")[0] if " #" in name else name
        max_name_w = name_right_limit - name_col_x
        name_size = fit_size(draw, display_name, FONT_SEMIBOLD, 25, 16, max_name_w)
        draw_mixed_text(draw, (name_col_x, cy), display_name, FONT_SEMIBOLD, name_size, TEXT, anchor="lm")

        # bw / date
        draw.text((bw_x, cy), f"{bw_kg:.1f}", font=f_num, fill=TEXT_DIM, anchor="rm")
        date_str = f"{meet_date:%b} {meet_date.day}, {meet_date.year}"
        draw.text((date_x, cy), date_str, font=f_num, fill=TEXT_DIM, anchor="rm")

        # total (headline, accent)
        draw.text((total_x, cy), f"{total_kg:.1f}", font=f_total, fill=ACCENT, anchor="rm")

        # dots
        draw.text((dots_x, cy), f"{dots:.1f}", font=f_dots, fill=TEXT, anchor="rm")

        if i < n - 1:
            draw.line([(0, y1), (W, y1)], fill=BORDER, width=1)

    table_bottom = row_top + n * row_h

    # ---------- Footer ----------
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

    for sex, classes in WEIGHT_CLASSES.items():
        for wc in classes:
            label = f"{SEX_LABEL[sex]} {wc}kg — Top 15"
            out_path = out_dir / f"{sex}_{wc.replace('+', 'plus')}_top15.png"
            build_graphic(sex, wc, label, out_path)


if __name__ == "__main__":
    main()
