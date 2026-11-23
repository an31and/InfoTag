"""Print layout engine for Event Mode — vector PDFs, every size in millimetres.

Modes
-----
* ``sticker_sheet`` – one tag per cell on a label sheet (presets 12/24/35 per
  A4, or custom to match a purchased sheet).
* ``badge_cards``   – ID-card sized (54 × 85.6 mm portrait) with a lanyard
  slot mark and a hand-write name line.
* ``guest_pack``    – one row per guest: a name card + 3 stickers that all
  belong to the same owner (8 guests per A4).

Every QR is drawn as vector rectangles with a 4-module quiet zone, black on
white, never smaller than 20 mm.  Nothing personal is printed on a tag: only
the QR, the short code and "मिला? स्कैन करें / Found? Scan".  (A guest-pack
name card may carry the guest's *name* when the organiser imported one.)
"""
from __future__ import annotations

import io
from functools import lru_cache
from dataclasses import asdict, dataclass
from typing import Optional

import qrcode
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from pdf_text import draw_text, fit_size

CAPTION_HI = "मिला? स्कैन करें"
CAPTION_EN = "Found? Scan"
CAPTION = f"{CAPTION_HI} / {CAPTION_EN}"
MIN_QR_MM = 20.0
MAX_TAGS_PER_PDF = 250
QUIET_MODULES = 4
GREY = HexColor("#9CA3AF")

MODES = ("sticker_sheet", "badge_cards", "guest_pack")


@dataclass
class Layout:
    mode: str = "sticker_sheet"
    page_w: float = 210.0
    page_h: float = 297.0
    rows: int = 4
    cols: int = 3
    margin_top: float = 10.0
    margin_left: float = 10.0
    cell_w: float = 61.3
    cell_h: float = 67.0
    gap_x: float = 3.0
    gap_y: float = 3.0
    qr_mm: float = 30.0
    offset_x: float = 0.0  # calibration: + moves everything right
    offset_y: float = 0.0  # calibration: + moves everything down
    cut_marks: bool = False
    border: bool = True  # dashed outline — handy on plain paper
    start_slot: int = 1  # 1-based, first page only (reuse part-used sheets)
    show_domain: bool = True

    @property
    def per_page(self) -> int:
        return self.rows * self.cols

    def to_dict(self) -> dict:
        return asdict(self)


# name → (description, Layout kwargs).  Real label sheets vary by brand —
# start from a preset, print the calibration page, then fine-tune.
PRESETS: dict[str, tuple[str, dict]] = {
    "a4_12": ("12 per A4 (3×4, ~61×67 mm)", dict(mode="sticker_sheet", rows=4, cols=3, margin_top=10, margin_left=10, cell_w=61.3, cell_h=67, gap_x=3, gap_y=3, qr_mm=34)),
    "a4_24": ("24 per A4 (3×8, 63.5×33.9 mm)", dict(mode="sticker_sheet", rows=8, cols=3, margin_top=12.9, margin_left=7.25, cell_w=63.5, cell_h=33.9, gap_x=2.5, gap_y=0, qr_mm=22)),
    "a4_35": ("35 per A4 (5×7, 38×38 mm)", dict(mode="sticker_sheet", rows=7, cols=5, margin_top=6.5, margin_left=5, cell_w=38, cell_h=38, gap_x=2.5, gap_y=3, qr_mm=21)),
    "badge": ("ID badges (3×3, 54×85.6 mm)", dict(mode="badge_cards", rows=3, cols=3, margin_top=12.2, margin_left=14, cell_w=54, cell_h=85.6, gap_x=8, gap_y=6, qr_mm=32)),
    "guest_pack": ("Guest packs (8 per A4: name card + 3 stickers)", dict(mode="guest_pack", rows=8, cols=1, margin_top=8.5, margin_left=8, cell_w=194, cell_h=34, gap_x=0, gap_y=1.5, qr_mm=21)),
}

DEFAULT_PRESET_FOR_MODE = {"sticker_sheet": "a4_24", "badge_cards": "badge", "guest_pack": "guest_pack"}
GUEST_PACK_SIZE = 4  # name card + 3 stickers


def build_layout(preset: Optional[str] = None, **overrides) -> Layout:
    """Preset (or the default for ``mode``) + any explicit mm overrides."""
    mode = overrides.get("mode")
    name = preset or DEFAULT_PRESET_FOR_MODE.get(mode or "sticker_sheet", "a4_24")
    if name not in PRESETS:
        raise ValueError(f"Unknown preset '{name}'")
    base = dict(PRESETS[name][1])
    for k, v in overrides.items():
        if v is not None and k in Layout.__dataclass_fields__:
            base[k] = v
    lay = Layout(**base)
    validate_layout(lay)
    return lay


def validate_layout(lay: Layout) -> None:
    if lay.mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    if lay.rows < 1 or lay.cols < 1 or lay.rows * lay.cols > 200:
        raise ValueError("rows × cols must be between 1 and 200")
    if lay.qr_mm < MIN_QR_MM:
        raise ValueError(f"QR must be at least {MIN_QR_MM:.0f} mm for reliable scanning")
    if min(lay.cell_w, lay.cell_h) <= 0 or min(lay.page_w, lay.page_h) <= 0:
        raise ValueError("sizes must be positive")
    used_w = lay.margin_left + lay.cols * lay.cell_w + (lay.cols - 1) * lay.gap_x
    used_h = lay.margin_top + lay.rows * lay.cell_h + (lay.rows - 1) * lay.gap_y
    if used_w > lay.page_w + 0.01 or used_h > lay.page_h + 0.01:
        raise ValueError(
            f"Grid ({used_w:.1f} × {used_h:.1f} mm incl. margin) does not fit the page "
            f"({lay.page_w:.0f} × {lay.page_h:.0f} mm)"
        )
    if lay.mode == "sticker_sheet":
        # vertical needs QR+quiet+~8 mm text; horizontal needs QR+quiet+~16 mm text
        q = lay.qr_mm * 1.25
        if not ((q + 7 <= lay.cell_h and q <= lay.cell_w) or (q + 16 <= lay.cell_w and q <= lay.cell_h + 0.01)):
            raise ValueError("QR (with quiet zone) plus its text does not fit in the cell — reduce qr_mm or enlarge the cell")
    if lay.mode == "guest_pack" and lay.qr_mm * 1.25 > lay.cell_h:
        raise ValueError("QR does not fit the guest-pack row height")
    if lay.mode == "badge_cards" and lay.qr_mm * 1.25 > lay.cell_w:
        raise ValueError("QR does not fit the badge width")
    if lay.start_slot < 1 or lay.start_slot > lay.per_page:
        raise ValueError(f"start_slot must be between 1 and {lay.per_page}")


# ---------------------------------------------------------------------------
# Geometry helpers (mm in, points out; origin bottom-left as in PDF)
# ---------------------------------------------------------------------------
def cell_rect(lay: Layout, slot: int) -> tuple[float, float, float, float]:
    """0-based slot on a page → (x, y, w, h) in points."""
    r, col = divmod(slot, lay.cols)
    x_mm = lay.margin_left + col * (lay.cell_w + lay.gap_x) + lay.offset_x
    top_mm = lay.margin_top + r * (lay.cell_h + lay.gap_y) + lay.offset_y
    y_mm = lay.page_h - top_mm - lay.cell_h
    return x_mm * mm, y_mm * mm, lay.cell_w * mm, lay.cell_h * mm


@lru_cache(maxsize=1024)
def qr_matrix(data: str) -> tuple[tuple[bool, ...], ...]:
    """Highest error correction that keeps the symbol at version ≤ 5."""
    for ec in (qrcode.constants.ERROR_CORRECT_H, qrcode.constants.ERROR_CORRECT_Q):
        qr = qrcode.QRCode(error_correction=ec, border=0)
        qr.add_data(data)
        qr.make(fit=True)
        if qr.version <= 5 or ec == qrcode.constants.ERROR_CORRECT_Q:
            return tuple(tuple(r) for r in qr.get_matrix())
    raise AssertionError("unreachable")


def draw_qr(c: canvas.Canvas, data: str, x: float, y: float, size: float) -> None:
    """Vector QR, ``size`` = symbol edge (quiet zone is *outside* it)."""
    m = qr_matrix(data)
    n = len(m)
    mod = size / n
    quiet = QUIET_MODULES * mod
    c.setFillColor(white)
    c.rect(x - quiet, y - quiet, size + 2 * quiet, size + 2 * quiet, stroke=0, fill=1)
    c.setFillColor(black)
    # Draw in module units (integer coordinates → compact, fast PDF ops).
    c.saveState()
    c.translate(x, y + size)
    c.scale(mod, -mod)
    ops = []
    for r, row in enumerate(m):
        col = 0
        while col < n:
            if row[col]:
                start = col
                while col < n and row[col]:
                    col += 1
                # 0.04-module overlap hides anti-aliasing seams between rows
                ops.append(f"{start} {r - 0.02:.2f} {col - start + 0.02:.2f} 1.04 re")
            else:
                col += 1
    # Raw path operators: ~10x faster than PathObject.rect for 1000+ runs.
    c._code.append(" ".join(ops) + " f")
    c.restoreState()


def _outline(c, lay: Layout, x, y, w, h, radius: float = 2 * mm) -> None:
    if lay.border:
        c.setStrokeColor(GREY)
        c.setLineWidth(0.3)
        c.setDash(2, 2)
        c.roundRect(x, y, w, h, radius, stroke=1, fill=0)
        c.setDash()
    if lay.cut_marks:
        c.setStrokeColor(black)
        c.setLineWidth(0.25)
        L, g = 3 * mm, 1 * mm
        for cx, cy, dx, dy in ((x, y, -1, -1), (x + w, y, 1, -1), (x, y + h, -1, 1), (x + w, y + h, 1, 1)):
            c.line(cx + dx * g, cy, cx + dx * (g + L), cy)
            c.line(cx, cy + dy * g, cx, cy + dy * (g + L))


# ---------------------------------------------------------------------------
# Cell renderers
# ---------------------------------------------------------------------------
def _text_block(c, cx: float, top: float, width: float, code: str, domain: str, show_domain: bool, scale: float = 1.0) -> None:
    """Code + caption (+ domain) centred on cx, first baseline below ``top``."""
    c.setFillColor(black)
    code_size = fit_size(c, code, width, 8.5 * scale, 5)
    y = top - code_size
    draw_text(c, code, cx, y, code_size, "center")
    cap = fit_size(c, CAPTION, width, 6.8 * scale, 4.2)
    y -= cap + 1.6
    draw_text(c, CAPTION, cx, y, cap, "center")
    if show_domain and domain:
        ds = fit_size(c, domain, width, 5.2 * scale, 3.8)
        y -= ds + 1.2
        draw_text(c, domain, cx, y, ds, "center")


def _sticker(c, lay: Layout, rect, item: dict, domain: str) -> None:
    x, y, w, h = rect
    _outline(c, lay, x, y, w, h)
    q = lay.qr_mm * mm
    n = len(qr_matrix(item["url"]))
    quiet = QUIET_MODULES * q / n
    total = q + 2 * quiet
    if total + 7 * mm <= h and total <= w:  # vertical: QR on top, text below
        qx = x + (w - q) / 2
        qy = y + h - quiet - q - max(0, (h - total - 9 * mm) / 2)
        draw_qr(c, item["url"], qx, qy, q)
        _text_block(c, x + w / 2, qy - quiet + 0.5 * mm, w - 2 * mm, item["code"], domain, lay.show_domain)
    else:  # horizontal: QR left, text right
        qx = x + quiet
        qy = y + (h - q) / 2
        draw_qr(c, item["url"], qx, qy, q)
        tx0 = qx + q + quiet
        tw = x + w - tx0 - 1 * mm
        _text_block(c, tx0 + tw / 2, y + h / 2 + 5.5 * mm, tw, item["code"], domain, lay.show_domain, 1.05)


def _badge(c, lay: Layout, rect, item: dict, domain: str, event_name: str) -> None:
    x, y, w, h = rect
    _outline(c, lay, x, y, w, h, 3 * mm)
    band = 16 * mm
    c.setFillColor(black)
    c.roundRect(x, y + h - band, w, band, 3 * mm, stroke=0, fill=1)
    c.rect(x, y + h - band, w, band / 2, stroke=0, fill=1)
    # lanyard slot mark
    c.setFillColor(white)
    c.setStrokeColor(GREY)
    c.setDash(1.5, 1.5)
    c.roundRect(x + w / 2 - 7 * mm, y + h - 6.5 * mm, 14 * mm, 3.5 * mm, 1.7 * mm, stroke=1, fill=1)
    c.setDash()
    c.setFillColor(white)
    name = event_name or "Info-Tag"
    draw_text(c, name, x + w / 2, y + h - band + 3.5 * mm, fit_size(c, name, w - 6 * mm, 10, 5), "center")
    q = lay.qr_mm * mm
    qy = y + h - band - 6 * mm - q
    draw_qr(c, item["url"], x + (w - q) / 2, qy, q)
    _text_block(c, x + w / 2, qy - 2.5 * mm, w - 4 * mm, item["code"], domain, lay.show_domain, 1.1)
    # write-in name line (nothing personal is printed)
    c.setFillColor(black)
    draw_text(c, "नाम / Name:", x + 4 * mm, y + 7 * mm, 7)
    c.setStrokeColor(black)
    c.setLineWidth(0.4)
    c.line(x + 20 * mm, y + 6.5 * mm, x + w - 4 * mm, y + 6.5 * mm)


def _guest_row(c, lay: Layout, rect, pack: dict, domain: str, event_name: str) -> None:
    x, y, w, h = rect
    items = pack["items"]
    q = lay.qr_mm * mm
    card_w = 70 * mm
    sticker_w = (w - card_w - 3 * 2 * mm) / 3
    # name card
    _outline(c, lay, x, y, card_w, h)
    n = len(qr_matrix(items[0]["url"]))
    quiet = QUIET_MODULES * q / n
    qx = x + card_w - quiet - q
    draw_qr(c, items[0]["url"], qx, y + (h - q) / 2, q)
    tx = x + 3 * mm
    tw = qx - quiet - tx
    c.setFillColor(black)
    ev = event_name or "Info-Tag"
    draw_text(c, ev, tx, y + h - 6 * mm, fit_size(c, ev, tw, 7, 4.5))
    guest = (pack.get("name") or "").strip()
    if guest:
        draw_text(c, guest, tx, y + h / 2, fit_size(c, guest, tw, 11, 6))
        if pack.get("group"):
            draw_text(c, pack["group"], tx, y + h / 2 - 4.5 * mm, fit_size(c, pack["group"], tw, 7, 4.5))
    else:
        draw_text(c, "नाम / Name:", tx, y + h / 2 + 1 * mm, 6.5)
        c.setStrokeColor(black)
        c.setLineWidth(0.4)
        c.line(tx, y + h / 2 - 4 * mm, tx + tw, y + h / 2 - 4 * mm)
    draw_text(c, items[0]["code"], tx, y + 4 * mm, fit_size(c, items[0]["code"], tw, 7, 4.5))
    # three stickers
    for i, item in enumerate(items[1:4]):
        sx = x + card_w + 2 * mm + i * (sticker_w + 2 * mm)
        _outline(c, lay, sx, y, sticker_w, h)
        draw_qr(c, item["url"], sx + (sticker_w - q) / 2, y + h - quiet - q, q)
        _text_block(c, sx + sticker_w / 2, y + h - 2 * quiet - q + 0.6 * mm, sticker_w - 2 * mm, item["code"], "", False, 0.95)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
def render_sheet(lay: Layout, units: list[dict], *, domain: str = "", event_name: str = "", title: str = "Info-Tag") -> bytes:
    """``units`` = stickers/badges ({url, code}) or guest packs ({items, name, group}).

    The first page starts at ``lay.start_slot``; later pages start at slot 1.
    """
    tag_count = sum(len(u.get("items", [u])) for u in units)
    if tag_count > MAX_TAGS_PER_PDF:
        raise ValueError(f"At most {MAX_TAGS_PER_PDF} tags per PDF — download in chunks")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(lay.page_w * mm, lay.page_h * mm))
    c.setTitle(title)
    c.setAuthor("Info-Tag")
    slot = lay.start_slot - 1
    for unit in units:
        if slot >= lay.per_page:
            c.showPage()
            slot = 0
        rect = cell_rect(lay, slot)
        if lay.mode == "sticker_sheet":
            _sticker(c, lay, rect, unit, domain)
        elif lay.mode == "badge_cards":
            _badge(c, lay, rect, unit, domain, event_name)
        else:
            _guest_row(c, lay, rect, unit, domain, event_name)
        slot += 1
    c.showPage()
    c.save()
    return buf.getvalue()


def render_calibration(lay: Layout) -> bytes:
    """Outline of every slot + rulers, to check alignment on a real sheet."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(lay.page_w * mm, lay.page_h * mm))
    c.setTitle("Info-Tag calibration")
    c.setStrokeColor(black)
    for s in range(lay.per_page):
        x, y, w, h = cell_rect(lay, s)
        c.setLineWidth(0.3)
        c.rect(x, y, w, h, stroke=1, fill=0)
        cx, cy = x + w / 2, y + h / 2
        c.line(cx - 3 * mm, cy, cx + 3 * mm, cy)
        c.line(cx, cy - 3 * mm, cx, cy + 3 * mm)
        c.setFillColor(black)
        draw_text(c, f"{s + 1}", x + 1.5 * mm, y + h - 4 * mm, 6)
    # 100 mm rulers to verify the printer is not scaling ("Actual size")
    x0, y0 = 15 * mm, 4 * mm
    c.setLineWidth(0.4)
    c.line(x0, y0, x0 + 100 * mm, y0)
    for i in range(11):
        c.line(x0 + i * 10 * mm, y0, x0 + i * 10 * mm, y0 + (2.5 if i % 5 else 4) * mm)
    draw_text(c, "100 mm — print at Actual size / 100%", x0 + 102 * mm, y0, 6)
    info = (
        f"Info-Tag calibration · {lay.rows}×{lay.cols} · cell {lay.cell_w}×{lay.cell_h} mm · "
        f"margins top {lay.margin_top} left {lay.margin_left} · offset X {lay.offset_x:+} Y {lay.offset_y:+}"
    )
    draw_text(c, info, lay.page_w * mm / 2, lay.page_h * mm - 4 * mm, 6, "center")
    c.showPage()
    c.save()
    return buf.getvalue()


def render_poster(*, event_name: str, url: str, code: str, venue: str = "", help_note: str = "", domain: str = "") -> bytes:
    """A4 event poster: one shared QR that opens the event page."""
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pw, ph = A4
    c.setTitle(f"{event_name} — Lost & Found")
    c.setFillColor(black)
    c.rect(0, ph - 46 * mm, pw, 46 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    draw_text(c, "खोया / मिला?", pw / 2, ph - 22 * mm, 30, "center")
    draw_text(c, "LOST OR FOUND SOMETHING?", pw / 2, ph - 36 * mm, 18, "center")
    c.setFillColor(black)
    draw_text(c, event_name, pw / 2, ph - 62 * mm, fit_size(c, event_name, pw - 30 * mm, 26, 12), "center")
    if venue:
        draw_text(c, venue, pw / 2, ph - 72 * mm, fit_size(c, venue, pw - 30 * mm, 13, 8), "center")
    q = 110 * mm
    qy = ph - 82 * mm - q
    draw_qr(c, url, (pw - q) / 2, qy, q)
    y = qy - 20 * mm
    draw_text(c, "फ़ोन कैमरा से स्कैन करें — कोई ऐप नहीं चाहिए", pw / 2, y, 15, "center")
    draw_text(c, "Scan with your phone camera — no app needed", pw / 2, y - 9 * mm, 13, "center")
    hint = f"{domain}/e/{code}" if domain else f"/e/{code}"
    draw_text(c, hint, pw / 2, y - 18 * mm, 12, "center")
    if help_note:
        draw_text(c, help_note, pw / 2, y - 30 * mm, fit_size(c, help_note, pw - 30 * mm, 14, 8), "center")
    draw_text(c, "Info-Tag · Privacy-first · Made in India", pw / 2, 12 * mm, 9, "center")
    c.showPage()
    c.save()
    return buf.getvalue()


def presets_public() -> list[dict]:
    return [{"id": k, "label": v[0], "layout": Layout(**v[1]).to_dict()} for k, v in PRESETS.items()]


__all__ = [
    "Layout", "PRESETS", "MODES", "build_layout", "validate_layout", "render_sheet",
    "render_calibration", "render_poster", "presets_public", "MAX_TAGS_PER_PDF",
    "GUEST_PACK_SIZE", "CAPTION", "cell_rect", "qr_matrix",
]
