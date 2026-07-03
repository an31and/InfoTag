"""Sticker PDF generator — A4 multi-sticker, ID card and keyring layouts."""
from __future__ import annotations

import io
from typing import Literal

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from auth import get_current_user
from db import get_db
from urls import resolve_site_url, site_domain

router = APIRouter(prefix="/api/tags/{tag_id}/pdf", tags=["pdf"])

Layout = Literal["a4_stickers", "id_card", "keyring"]


async def _current_user_dep(request: Request) -> dict:
    return await get_current_user(request, get_db())


def _qr_image(url: str) -> qrcode.image.pil.PilImage:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _draw_qr(c: canvas.Canvas, pil_img, x: float, y: float, size: float) -> None:
    from reportlab.lib.utils import ImageReader

    c.drawImage(ImageReader(pil_img), x, y, width=size, height=size, mask=None)


CONTEXT_CAPTIONS = {
    "vehicle": "Scan if this vehicle needs the owner",
    "pet": "I'm lost — please scan to help",
    "luggage": "Scan if found — return to owner",
    "keys": "Scan if found — return to owner",
    "medical": "MEDICAL ID — scan in emergency",
    "special": "PLEASE HELP — scan to reach my guardian",
    "general": "Scan if found",
}


@router.get("")
async def generate_pdf(
    tag_id: str,
    request: Request,
    layout: Layout = Query("a4_stickers"),
    user: dict = Depends(_current_user_dep),
) -> StreamingResponse:
    db = get_db()
    doc = await db.tags.find_one({"id": tag_id, "owner_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Absolute URL derived from SITE_URL or the request origin — a QR with a
    # relative path cannot be opened by phone cameras.
    url = f"{resolve_site_url(request)}/api/finder/{doc['slug']}"
    domain = site_domain(request)
    pil = _qr_image(url)
    caption = CONTEXT_CAPTIONS.get(doc.get("type", "general"), "Scan if found")
    label = doc.get("display_name") or doc.get("label") or "Info-Tag"

    buf = io.BytesIO()
    if layout == "a4_stickers":
        _draw_a4_stickers(buf, pil, doc["slug"], label, caption, doc.get("type", "general"), domain)
    elif layout == "id_card":
        _draw_id_card(buf, pil, doc["slug"], label, caption, doc.get("type", "general"), domain)
    elif layout == "keyring":
        _draw_keyring(buf, pil, doc["slug"], label, caption, doc.get("type", "general"), domain)
    else:
        raise HTTPException(status_code=400, detail="Unknown layout")
    buf.seek(0)
    filename = f"info-tag-{doc['slug']}-{layout}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Layout draw routines
# ---------------------------------------------------------------------------
ASHOKA_NAVY = HexColor("#0F172A")
ACCENT = HexColor("#E25822")
EMERGENCY_RED = HexColor("#DC2626")


def _draw_a4_stickers(buf, pil, slug, label, caption, tag_type, domain) -> None:
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    cols, rows = 3, 4
    margin_x, margin_y = 12 * mm, 12 * mm
    gap = 4 * mm
    avail_w = page_w - 2 * margin_x - (cols - 1) * gap
    avail_h = page_h - 2 * margin_y - (rows - 1) * gap
    cell_w = avail_w / cols
    cell_h = avail_h / rows

    for r in range(rows):
        for col in range(cols):
            x = margin_x + col * (cell_w + gap)
            y = page_h - margin_y - (r + 1) * cell_h - r * gap
            # Cut-mark border (dashed)
            c.setStrokeColor(HexColor("#888888"))
            c.setDash(2, 2)
            c.rect(x, y, cell_w, cell_h, stroke=1, fill=0)
            c.setDash()
            # QR
            qr_size = min(cell_w, cell_h) - 22 * mm
            qr_x = x + (cell_w - qr_size) / 2
            qr_y = y + cell_h - qr_size - 14 * mm
            _draw_qr(c, pil, qr_x, qr_y, qr_size)
            # Header
            c.setFillColor(EMERGENCY_RED if tag_type == "medical" else ASHOKA_NAVY)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(x + cell_w / 2, y + cell_h - 8 * mm, f"Info-Tag · {domain}")
            # Caption
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x + cell_w / 2, y + 10 * mm, caption.upper()[:38])
            c.setFont("Helvetica", 6.5)
            c.drawCentredString(x + cell_w / 2, y + 6.5 * mm, f"or visit {domain}/api/finder/{slug}")
            c.setFont("Helvetica-Oblique", 6)
            c.setFillColor(HexColor("#666666"))
            c.drawCentredString(x + cell_w / 2, y + 3.5 * mm, "Privacy-first • Made in India")
    c.showPage()
    c.save()


def _draw_id_card(buf, pil, slug, label, caption, tag_type, domain) -> None:
    """Credit-card-sized layout (85.6 x 54 mm) centred on an A4 page."""
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    card_w, card_h = 85.6 * mm, 54 * mm
    x = (page_w - card_w) / 2
    y = (page_h - card_h) / 2

    # Border + outline
    c.setStrokeColor(HexColor("#888888"))
    c.setDash(2, 2)
    c.rect(x, y, card_w, card_h, stroke=1, fill=0)
    c.setDash()

    # Left band
    band_w = 22 * mm
    c.setFillColor(EMERGENCY_RED if tag_type == "medical" else ASHOKA_NAVY)
    c.rect(x, y, band_w, card_h, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.saveState()
    c.translate(x + band_w / 2, y + card_h / 2)
    c.rotate(90)
    c.drawCentredString(0, -3, "Info-Tag · MADE IN INDIA")
    c.restoreState()

    # QR
    qr_size = card_h - 10 * mm
    qr_x = x + band_w + 5 * mm
    qr_y = y + (card_h - qr_size) / 2
    _draw_qr(c, pil, qr_x, qr_y, qr_size)

    # Text area
    text_x = qr_x + qr_size + 4 * mm
    c.setFillColor(ASHOKA_NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(text_x, y + card_h - 10 * mm, label[:24])
    c.setFillColor(black)
    c.setFont("Helvetica", 7.5)
    c.drawString(text_x, y + card_h - 16 * mm, caption[:32])
    c.setFont("Helvetica", 6.5)
    c.drawString(text_x, y + 14 * mm, "Scan the QR with any phone camera.")
    c.drawString(text_x, y + 10 * mm, f"or visit {domain}/api/finder/{slug}")
    c.setFillColor(HexColor("#666666"))
    c.setFont("Helvetica-Oblique", 6)
    c.drawString(text_x, y + 6 * mm, "No app needed for the finder.")

    c.showPage()
    c.save()


def _draw_keyring(buf, pil, slug, label, caption, tag_type, domain) -> None:
    """Small ~35mm round-ish keyring layout, 6 per A4."""
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    size = 38 * mm  # square sticker that can be cut round
    cols, rows = 4, 6
    margin_x = (page_w - cols * size - (cols - 1) * 4 * mm) / 2
    margin_y = (page_h - rows * size - (rows - 1) * 4 * mm) / 2
    for r in range(rows):
        for col in range(cols):
            x = margin_x + col * (size + 4 * mm)
            y = page_h - margin_y - (r + 1) * size - r * 4 * mm
            c.setStrokeColor(HexColor("#888888"))
            c.setDash(2, 2)
            c.circle(x + size / 2, y + size / 2, size / 2 - 0.5 * mm, stroke=1, fill=0)
            c.setDash()
            qr_size = size - 14 * mm
            _draw_qr(c, pil, x + (size - qr_size) / 2, y + (size - qr_size) / 2 + 2 * mm, qr_size)
            c.setFillColor(EMERGENCY_RED if tag_type == "medical" else ASHOKA_NAVY)
            c.setFont("Helvetica-Bold", 6)
            c.drawCentredString(x + size / 2, y + 3.5 * mm, f"Info-Tag · {domain}")
    c.showPage()
    c.save()
