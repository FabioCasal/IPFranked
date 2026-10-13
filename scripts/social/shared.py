"""Shared palette, fonts, and drawing helpers for the IPFranked social graphics.

Canvas and palette intentionally mirror frontend/index.html's :root vars so
every graphic reads as the same brand as the live site.
"""
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "openipf.duckdb"
DEFAULT_OUT_DIR = ROOT / "social" / "output"

W, H = 1080, 1350  # Instagram portrait (4:5)

# ---------- Palette (matches frontend/index.html :root vars) ----------
BG = "#0f1115"
PANEL = "#171a21"
PANEL_2 = "#1e2229"
BORDER = "#2a2f3a"
TEXT = "#e8eaed"
TEXT_DIM = "#9aa1ac"
ACCENT = "#4f8cff"
GOLD = "#d4af37"
SILVER = "#b0b8c1"
BRONZE = "#c17a4a"
BADGE_DARK_TEXT = "#1a1a1a"

# ---------- Fonts (Windows system fonts -- matches site's font-stack) ----------
FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"
FONT_SEMIBOLD = r"C:\Windows\Fonts\seguisb.ttf"

# Segoe UI has no CJK/Hangul/Kana glyphs (OpenIPF names include e.g. Chinese
# lifters) -- fall back to Microsoft YaHei per-character for those ranges so
# names don't render as tofu boxes.
CJK_FALLBACK = r"C:\Windows\Fonts\msyh.ttc"

_CJK_RANGES = [
    (0x3040, 0x30FF),   # Hiragana + Katakana
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xAC00, 0xD7A3),   # Hangul syllables
    (0xF900, 0xFAFF),   # CJK compatibility ideographs
]


def _is_cjk(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def font(path, size):
    return ImageFont.truetype(path, size)


def _font_for_char(ch, base_path, size):
    return font(CJK_FALLBACK, size) if _is_cjk(ch) else font(base_path, size)


def mixed_textlength(draw, text, base_path, size):
    return sum(draw.textlength(ch, font=_font_for_char(ch, base_path, size)) for ch in text)


def draw_mixed_text(draw, xy, text, base_path, size, fill, anchor="lm"):
    """Draw text letter-by-letter, swapping in a CJK fallback font per-char.
    Only single-line 'lm'/'rm'/'mm' anchors are supported."""
    total_w = mixed_textlength(draw, text, base_path, size)
    x, y = xy
    h_anchor, v_anchor = anchor[0], anchor[1]
    if h_anchor == "r":
        x -= total_w
    elif h_anchor == "m":
        x -= total_w / 2
    cur_x = x
    for ch in text:
        f = _font_for_char(ch, base_path, size)
        draw.text((cur_x, y), ch, font=f, fill=fill, anchor="l" + v_anchor)
        cur_x += draw.textlength(ch, font=f)


def fit_size(draw, text, fnt_path, max_size, min_size, max_width):
    size = max_size
    while mixed_textlength(draw, text, fnt_path, size) > max_width and size > min_size:
        size -= 1
    return size


def fmt1(value):
    """One-decimal number for a table cell, or a dash when the export left it
    blank (e.g. no recorded bodyweight, and therefore no Dots either)."""
    return "-" if value is None else f"{value:.1f}"


def centered_text(draw, cy, text, fnt, fill):
    """Draw single-line text horizontally centered on the canvas, vertically
    centered on cy. Returns the rendered text height."""
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (W - w) / 2 - bbox[0]
    y = cy - h / 2 - bbox[1]
    draw.text((x, y), text, font=fnt, fill=fill)
    return h


def draw_wordmark(draw, cy, size=80):
    """Draw the centered 'IPFranked' wordmark used on title/outro slides."""
    f_word = font(FONT_BOLD, size)
    ipf_w = draw.textlength("IPF", font=f_word)
    ranked_w = draw.textlength("ranked", font=f_word)
    total_w = ipf_w + ranked_w
    bbox = draw.textbbox((0, 0), "IPFranked", font=f_word)
    h = bbox[3] - bbox[1]
    x0 = (W - total_w) / 2
    y0 = cy - h / 2 - bbox[1]
    draw.text((x0, y0), "IPF", font=f_word, fill=ACCENT)
    draw.text((x0 + ipf_w, y0), "ranked", font=f_word, fill=TEXT)

    rule_y = cy + 70
    rule_w = 90
    draw.line(
        [(W / 2 - rule_w / 2, rule_y), (W / 2 + rule_w / 2, rule_y)],
        fill=ACCENT, width=4,
    )


def draw_inline_wordmark(draw, xy, size=50):
    """Draw the left-aligned 'IPFranked' wordmark used atop leaderboard slides."""
    x, y = xy
    f_word = font(FONT_BOLD, size)
    draw.text((x, y), "IPF", font=f_word, fill=ACCENT, anchor="lm")
    ipf_w = draw.textlength("IPF", font=f_word)
    draw.text((x + ipf_w, y), "ranked", font=f_word, fill=TEXT, anchor="lm")
