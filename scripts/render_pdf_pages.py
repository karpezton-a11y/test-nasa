#!/usr/bin/env python
"""QA helper: render every page of a PDF to PNG for a visual layout check.

    python scripts/render_pdf_pages.py reports/<id>.pdf --out reports/pages

Needs pypdfium2 (in requirements-dev.txt only; not used by the app).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pypdfium2 as pdfium


def main() -> None:
    parser = argparse.ArgumentParser(description="Render PDF pages to PNG")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/pages"))
    parser.add_argument("--scale", type=float, default=1.3)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(args.pdf))
    for index in range(len(document)):
        target = args.out / f"page_{index + 1:02d}.png"
        document[index].render(scale=args.scale).to_pil().save(target)
        print(target)


if __name__ == "__main__":
    main()
