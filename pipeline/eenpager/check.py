"""Check the one-pager PDF: exactly one A4 page, and render PNGs to look at.

Usage: python check.py <pdf> <out-prefix> [dpi]
Writes <out-prefix>.png (colour) and <out-prefix>-grijs.png (greyscale, to check
that the page still reads when printed in black and white).
"""

import sys

import pymupdf

A4_PT = (595.28, 841.89)


def main() -> int:
    pdf, prefix = sys.argv[1], sys.argv[2]
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 110
    doc = pymupdf.open(pdf)
    ok = True
    if doc.page_count != 1:
        print(f"FOUT: {doc.page_count} pagina's, verwacht precies 1")
        ok = False
    page = doc[0]
    w, h = page.rect.width, page.rect.height
    if abs(w - A4_PT[0]) > 1 or abs(h - A4_PT[1]) > 1:
        print(f"FOUT: paginaformaat {w:.1f} x {h:.1f} pt is geen A4")
        ok = False
    page.get_pixmap(dpi=dpi).save(f"{prefix}.png")
    page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY).save(f"{prefix}-grijs.png")
    fonts = sorted({f[3] for f in page.get_fonts()})
    print(f"pagina's: {doc.page_count}, formaat: {w:.1f} x {h:.1f} pt, fonts: {', '.join(fonts)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
