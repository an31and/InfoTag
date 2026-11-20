"""Vector text for PDFs, including correctly shaped Hindi (Devanagari).

ReportLab's built-in fonts cannot render Devanagari, and drawing a TTF with
plain ``drawString`` breaks conjuncts and matras (स्कैन comes out wrong).  We
shape Devanagari runs with HarfBuzz and draw the glyph *outlines* as vector
paths; Latin runs use Helvetica.  Each distinct (text, size) is stored once
per PDF as a Form XObject and stamped wherever it is needed, so a caption
repeated on 250 stickers adds its outline data to the file only once.

Font: Noto Sans Devanagari Bold (SIL Open Font License, see fonts/OFL.txt).
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

FONT_PATH = Path(__file__).parent / "fonts" / "NotoSansDevanagari-Bold.ttf"
LATIN_FONT = "Helvetica-Bold"


def _is_deva(ch: str) -> bool:
    o = ord(ch)
    return 0x0900 <= o <= 0x097F or 0xA8E0 <= o <= 0xA8FF or o in (0x200C, 0x200D)


def split_runs(text: str) -> list[tuple[bool, str]]:
    """[(is_devanagari, run_text)], spaces stick to the preceding run."""
    runs: list[tuple[bool, str]] = []
    for ch in text:
        deva = _is_deva(ch)
        if ch == " " and runs:
            deva = runs[-1][0]
        if runs and runs[-1][0] == deva:
            runs[-1] = (deva, runs[-1][1] + ch)
        else:
            runs.append((deva, ch))
    return runs


@lru_cache(maxsize=1)
def _font():
    data = FONT_PATH.read_bytes()
    face = hb.Face(data)
    hbfont = hb.Font(face)
    tt = TTFont(str(FONT_PATH))
    return hbfont, tt, tt.getGlyphSet(), tt["head"].unitsPerEm, tt.getGlyphOrder()


@lru_cache(maxsize=512)
def _shape(text: str):
    hbfont, _tt, _gs, _upem, order = _font()
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {})
    out = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((order[info.codepoint], pos.x_advance, pos.x_offset, pos.y_offset))
    return out


class _PathPen(BasePen):
    def __init__(self, glyphset, path, x0: float, y0: float, scale: float):
        super().__init__(glyphset)
        self.p, self.x0, self.y0, self.s = path, x0, y0, scale

    def _t(self, pt):
        return self.x0 + pt[0] * self.s, self.y0 + pt[1] * self.s

    def _moveTo(self, pt):
        self.p.moveTo(*self._t(pt))

    def _lineTo(self, pt):
        self.p.lineTo(*self._t(pt))

    def _curveToOne(self, p1, p2, p3):
        self.p.curveTo(*self._t(p1), *self._t(p2), *self._t(p3))

    def _closePath(self):
        self.p.close()


def text_width(c, text: str, size: float) -> float:
    _hb, _tt, _gs, upem, _o = _font()
    w = 0.0
    for deva, run in split_runs(text):
        if deva:
            w += sum(g[1] for g in _shape(run)) * size / upem
        else:
            w += c.stringWidth(run, LATIN_FONT, size)
    return w


def _draw_at_origin(c, text: str, size: float) -> None:
    _hb, _tt, glyphset, upem, _o = _font()
    scale = size / upem
    x = 0.0
    for deva, run in split_runs(text):
        if not deva:
            c.setFont(LATIN_FONT, size)
            c.drawString(x, 0, run)
            x += c.stringWidth(run, LATIN_FONT, size)
            continue
        path = c.beginPath()
        for name, adv, xo, yo in _shape(run):
            pen = _PathPen(glyphset, path, x + xo * scale, yo * scale, scale)
            glyphset[name].draw(pen)
            x += adv * scale
        c.drawPath(path, stroke=0, fill=1)


def draw_text(c, text: str, x: float, y: float, size: float, align: str = "left") -> float:
    """Draw mixed Hindi/English text at baseline (x, y).  Returns its width."""
    if not text:
        return 0.0
    w = text_width(c, text, size)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    if not any(_is_deva(ch) for ch in text):
        c.setFont(LATIN_FONT, size)
        c.drawString(x, y, text)
        return w
    forms = getattr(c, "_it_forms", None)
    if forms is None:
        forms = c._it_forms = set()
    name = "T" + hashlib.sha1(f"{size}|{text}".encode()).hexdigest()[:12]
    if name not in forms:
        c.beginForm(name, lowerx=-10, lowery=-size, upperx=w + 10, uppery=size * 1.5)
        _draw_at_origin(c, text, size)
        c.endForm()
        forms.add(name)
    c.saveState()
    c.translate(x, y)
    c.doForm(name)
    c.restoreState()
    return w


def fit_size(c, text: str, max_width: float, size: float, min_size: float = 5.0) -> float:
    """Largest font size ≤ ``size`` that fits ``max_width``."""
    w = text_width(c, text, size)
    if w <= max_width or w == 0:
        return size
    return max(min_size, size * max_width / w)
