import re

import pytest

import print_engine as pe
import tokens

KEY = b"k" * 32


def _items(n, start=0):
    return [
        {"url": tokens.qr_url("https://info-tag.in", tokens.encode_token(KEY, 1, s)), "code": tokens.short_code(KEY, "PK24", s)}
        for s in range(start, start + n)
    ]


@pytest.mark.parametrize("preset", list(pe.PRESETS))
def test_presets_fit_the_page(preset):
    lay = pe.build_layout(preset)
    for slot in range(lay.per_page):
        x, y, w, h = pe.cell_rect(lay, slot)
        assert x >= 0 and y >= 0
        assert x + w <= lay.page_w * pe.mm + 0.01
        assert y + h <= lay.page_h * pe.mm + 0.01


def test_preset_counts():
    assert pe.build_layout("a4_12").per_page == 12
    assert pe.build_layout("a4_24").per_page == 24
    assert pe.build_layout("a4_35").per_page == 35
    assert pe.build_layout("guest_pack").per_page == 8


def test_validation_rejects_bad_layouts():
    with pytest.raises(ValueError, match="at least 20"):
        pe.build_layout("a4_24", qr_mm=15)
    with pytest.raises(ValueError, match="does not fit the page"):
        pe.build_layout("a4_24", rows=12)
    with pytest.raises(ValueError, match="start_slot"):
        pe.build_layout("a4_24", start_slot=25)


def test_start_slot_and_offsets_move_cells():
    a = pe.build_layout("a4_24")
    b = pe.build_layout("a4_24", offset_x=1.5, offset_y=-2)
    xa, ya, *_ = pe.cell_rect(a, 0)
    xb, yb, *_ = pe.cell_rect(b, 0)
    assert round((xb - xa) / pe.mm, 3) == 1.5
    assert round((yb - ya) / pe.mm, 3) == 2.0  # -2 mm down-offset = 2 mm up


def test_max_250_tags_per_pdf():
    lay = pe.build_layout("a4_35")
    with pytest.raises(ValueError, match="250"):
        pe.render_sheet(lay, _items(251))


def test_pdf_is_vector_and_has_no_personal_data():
    lay = pe.build_layout("a4_24", start_slot=5)
    pdf = pe.render_sheet(lay, _items(30), domain="info-tag.in", event_name="Test")
    assert pdf.startswith(b"%PDF")
    assert b"/Subtype /Image" not in pdf  # QR + Hindi are vector paths
    # No phone-number-like digit runs in any text the PDF draws
    texts = re.findall(rb"\((.*?)\) Tj", pdf)
    for t in texts:
        assert not re.search(rb"\d{8,}", t), t


def test_guest_pack_and_badges_render():
    gp = pe.build_layout("guest_pack")
    items = _items(8)
    pdf = pe.render_sheet(gp, [{"items": items[:4], "name": "Asha", "group": "Bus 2"}, {"items": items[4:], "name": "", "group": ""}])
    assert pdf.startswith(b"%PDF")
    bd = pe.build_layout("badge")
    assert pe.render_sheet(bd, _items(9), event_name="प्रथ्वी परिक्रमा").startswith(b"%PDF")


def test_qr_is_small_version_with_high_ec():
    m = pe.qr_matrix(_items(1)[0]["url"])
    assert len(m) <= 37  # version ≤ 5 → big modules on a 2 cm sticker


def test_calibration_and_poster():
    assert pe.render_calibration(pe.build_layout("a4_35")).startswith(b"%PDF")
    assert pe.render_poster(event_name="Prathivi Parikrma", url="HTTPS://INFO-TAG.IN/E/PK24", code="PK24").startswith(b"%PDF")
