"""Generates the carousel bookend slides: a title slide per category, and the
closing follow/CTA slide.

Usage:
    python scripts/social/make_title_slide.py [--out-dir PATH] [--date "October 10, 2026"]

See STYLE_GUIDE.md for the full visual spec.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from shared import (
    ACCENT, BG, DEFAULT_OUT_DIR, FONT_BOLD, FONT_REG, FONT_SEMIBOLD, H, TEXT,
    TEXT_DIM, W, centered_text, draw_wordmark, font, save,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_db import CSV_PATH  # noqa: E402

HANDLE = "@ipf_ranked"


def _default_date_label():
    """Derive the human-readable snapshot date from build_db.py's CSV_PATH
    (e.g. openipf-2026-10-10-<hash>.csv) so this never drifts out of sync."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", CSV_PATH.stem)
    if not m:
        return None
    return datetime.strptime(m.group(0), "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")


def build_title_slide(category_label, out_path, subtitle="TOP 15 LEADERBOARDS", data_date_label=None):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw_wordmark(draw, H * 0.34, size=80)

    f_cat = font(FONT_BOLD, 64)
    f_sub = font(FONT_SEMIBOLD, 40)
    cat_cy = H * 0.52
    centered_text(draw, cat_cy, category_label.upper(), f_cat, TEXT)

    sub_cy = cat_cy + 64
    centered_text(draw, sub_cy, subtitle, f_sub, ACCENT)

    if data_date_label:
        f_meta = font(FONT_REG, 26)
        meta_cy = H * 0.64
        centered_text(draw, meta_cy, f"Data as of {data_date_label}", f_meta, TEXT_DIM)

    f_footer = font(FONT_REG, 19)
    draw.text((40, H - 50), "data provided by Open IPF", font=f_footer, fill=TEXT_DIM, anchor="lm")

    save(img, out_path)


def build_cta_slide(out_path):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw_wordmark(draw, H * 0.34, size=80)

    f_cat = font(FONT_BOLD, 54)
    f_sub = font(FONT_SEMIBOLD, 34)
    cat_cy = H * 0.50
    centered_text(draw, cat_cy, "IF YOU LIKE CONTENT LIKE THIS", f_cat, TEXT)

    sub_cy = cat_cy + 58
    centered_text(draw, sub_cy, "FOLLOW ALONG FOR MORE", f_sub, ACCENT)

    f_handle = font(FONT_BOLD, 46)
    handle_cy = H * 0.63
    centered_text(draw, handle_cy, HANDLE, f_handle, TEXT)

    save(img, out_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--date", default=_default_date_label(),
        help='Data snapshot label, e.g. "October 10, 2026". '
             "Defaults to the date embedded in build_db.py's CSV_PATH.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    build_title_slide("Men's", out_dir / "0_title_men.png", data_date_label=args.date)
    build_title_slide("Women's", out_dir / "0_title_women.png", data_date_label=args.date)
    build_title_slide(
        "Pound-for-Pound", out_dir / "0_title_p4p.png",
        subtitle="TOP 15 BY DOTS", data_date_label=args.date,
    )
    build_cta_slide(out_dir / "z_outro_follow.png")


if __name__ == "__main__":
    main()
