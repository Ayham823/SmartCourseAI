from pathlib import Path
from io import BytesIO

from pypdf import PdfReader


def load_pdf(file_path, content=None):
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"PDF file not found: {file_path}"
        )

    # Ingestion reads once so the hash and extracted pages describe the same PDF.
    reader = PdfReader(BytesIO(content)) if content is not None else PdfReader(str(path))

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):
        text = page.extract_text() or ""

        text = text.strip()

        if not text:
            continue

        pages.append({
            "page_number": page_number,
            "text": text
        })

    return pages
