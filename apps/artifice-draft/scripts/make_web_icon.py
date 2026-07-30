# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Generate the icon for the web frontend's desktop shortcut.

Run with:  py -3.12 scripts/make_web_icon.py

Same construction as `make_icon.py` (the desktop build's icon) — same indigo
field, cream page, struck-through red line, green insertion caret — plus a
small globe badge in the corner. Deliberately a variant, not a distinct icon:
this is the same tool, not a different one, so it should look like family
(exactly the reasoning the OCR Pipeline tool's own web icon script gives for
doing this the same way).

Badge colour: gold. The desktop icon already uses indigo (field), cream
(page), red (delete) and green (insert) — every other token in the shared
palette. Gold is the one colour left in the shared design system that isn't
already spoken for in this icon, so it reads as a deliberate addition rather
than a clash. (Reusing indigo itself, the way the OCR tool's web badge does,
isn't available here — it's already the whole field.)
"""

from pathlib import Path

from PIL import Image, ImageDraw

FIELD = (61, 90, 128)          # indigo
FIELD_DEEP = (44, 66, 96)
PAPER = (246, 243, 234)
PAPER_SHADE = (223, 217, 202)
INK = (75, 70, 61)
DELETE = (154, 51, 36)         # struck-out text
INSERT = (47, 125, 69)         # inserted text
GOLD = (191, 155, 48)          # badge — the one shared token unused elsewhere here

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "assets" / "artifice_draft_web.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]

SS = 4  # supersample factor


def draw_icon(size: int) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    radius = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=FIELD)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius,
                        outline=FIELD_DEEP, width=max(int(s * 0.012), 1))

    left, right = int(s * 0.26), int(s * 0.74)
    top, bottom = int(s * 0.17), int(s * 0.83)
    fold = int(s * 0.17)

    d.polygon([(left, top), (right - fold, top), (right, top + fold),
               (right, bottom), (left, bottom)], fill=PAPER)
    d.polygon([(right - fold, top), (right, top + fold), (right - fold, top + fold)],
              fill=PAPER_SHADE)

    if size < 24:
        margin = int(s * 0.08)
        y = int((top + bottom) / 2)
        weight = max(int(s * 0.06), SS)
        d.rounded_rectangle([left + margin, y, right - margin, y + weight],
                            radius=weight // 2, fill=INK)
        return img.resize((size, size), Image.LANCZOS)

    margin = int(s * 0.07)
    line_top = top + fold + int(s * 0.05)
    n_lines = 3 if size < 48 else 4
    gap = (bottom - line_top - margin) / n_lines
    weight = max(int(s * 0.035), SS)

    for i in range(n_lines):
        y = int(line_top + gap * i)
        end = right - margin - (int(s * 0.16) if i == n_lines - 1 else 0)
        if i == 1:
            d.rounded_rectangle([left + margin, y, end, y + weight],
                                radius=weight // 2, fill=DELETE)
            strike = max(int(s * 0.018), 2)
            mid = y + weight // 2
            d.rectangle([left + margin - int(s * 0.02), mid - strike // 2,
                         end + int(s * 0.02), mid + strike // 2], fill=DELETE)
        else:
            d.rounded_rectangle([left + margin, y, end, y + weight],
                                radius=weight // 2, fill=INK)

    caret_y = int(line_top + gap * 1 + weight + int(s * 0.012))
    caret_x = left + margin + int(s * 0.14)
    span = int(s * 0.05)
    d.polygon([(caret_x, caret_y + span), (caret_x + span, caret_y),
               (caret_x + span * 2, caret_y + span)], fill=INSERT)

    # Globe badge, bottom-right corner — "this is the web version," the same
    # small filled circle + equator/meridian glyph the OCR Pipeline tool's
    # web icon uses, kept small enough not to compete with the page itself.
    badge_r = s * 0.19
    cx, cy = s * 0.83, s * 0.83
    bbox = [cx - badge_r, cy - badge_r, cx + badge_r, cy + badge_r]
    d.ellipse(bbox, fill=GOLD, outline=PAPER, width=max(int(s * 0.013), 1))

    if size >= 32:
        line_w = max(int(badge_r * 0.11), 1)
        d.line([(cx - badge_r * 0.7, cy), (cx + badge_r * 0.7, cy)],
              fill=PAPER, width=line_w)
        merid_bbox = [cx - badge_r * 0.35, cy - badge_r * 0.82,
                     cx + badge_r * 0.35, cy + badge_r * 0.82]
        d.ellipse(merid_bbox, outline=PAPER, width=line_w)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw_icon(n) for n in SIZES]
    frames[-1].save(TARGET, format="ICO",
                    sizes=[(n, n) for n in SIZES],
                    append_images=frames[:-1])
    print(f"Wrote {TARGET}  ({', '.join(f'{n}x{n}' for n in SIZES)})")

    preview = ROOT / "assets" / "artifice_draft_web_preview.png"
    draw_icon(256).save(preview)
    print(f"Wrote {preview}")


if __name__ == "__main__":
    main()
