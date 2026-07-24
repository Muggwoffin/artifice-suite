"""Generate the application icon.

Run with:  py -3.12 scripts/make_icon.py

A page carrying a tracked change: a struck-out line and an insertion caret, in
the red/blue Word uses for revisions. Deliberately the same construction as the
OCR Pipeline tool's icon (rounded tile, cream page, folded corner) so the two
shortcuts read as a set, but on an indigo field rather than green so they are
never confused on a desktop.

Each size is drawn natively at 4x and downsampled — a 256px drawing squeezed
to 16px turns to mush, so the small sizes drop detail instead.
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

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "assets" / "personaeedit.ico"
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

    # Page with a turned corner
    left, right = int(s * 0.26), int(s * 0.74)
    top, bottom = int(s * 0.17), int(s * 0.83)
    fold = int(s * 0.17)

    d.polygon([(left, top), (right - fold, top), (right, top + fold),
               (right, bottom), (left, bottom)], fill=PAPER)
    d.polygon([(right - fold, top), (right, top + fold), (right - fold, top + fold)],
              fill=PAPER_SHADE)

    if size < 24:
        # At 16px a strike-through is a smudge; a single ink line reads better.
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
        # Second line is the "edit": struck through in red.
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

    # Insertion caret beneath the struck line
    caret_y = int(line_top + gap * 1 + weight + int(s * 0.012))
    caret_x = left + margin + int(s * 0.14)
    span = int(s * 0.05)
    d.polygon([(caret_x, caret_y + span), (caret_x + span, caret_y),
               (caret_x + span * 2, caret_y + span)], fill=INSERT)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw_icon(n) for n in SIZES]
    frames[-1].save(TARGET, format="ICO",
                    sizes=[(n, n) for n in SIZES],
                    append_images=frames[:-1])
    print(f"Wrote {TARGET}  ({', '.join(f'{n}x{n}' for n in SIZES)})")

    preview = ROOT / "assets" / "personaeedit_preview.png"
    draw_icon(256).save(preview)
    print(f"Wrote {preview}")


if __name__ == "__main__":
    main()
