import re
from typing import Optional, Tuple
from PIL import Image


def extract_code_from_text(text: str) -> Optional[str]:
    """Extract likely EAN/SKU from OCR text."""
    if not text:
        return None

    cleaned = text.replace(" ", "").replace("-", "")
    # Prefer EAN/GTIN-like numeric codes: 8, 12, 13, 14 digits.
    for pattern in [r"\b\d{13}\b", r"\b\d{14}\b", r"\b\d{12}\b", r"\b\d{8}\b"]:
        match = re.search(pattern, cleaned)
        if match:
            return match.group(0)

    # Fallback: SKU-like codes with letters/numbers.
    sku_match = re.search(r"\b[A-Z0-9]{3,}[-_/]?[A-Z0-9]{2,}\b", text.upper())
    return sku_match.group(0) if sku_match else None


def read_code_from_image(image: Image.Image) -> Tuple[Optional[str], str]:
    """Run OCR via pytesseract. Requires Tesseract installed on the system."""
    try:
        import pytesseract
    except Exception:
        return None, "Brak biblioteki pytesseract. Wpisz kod ręcznie albo doinstaluj OCR."

    try:
        gray = image.convert("L")
        text = pytesseract.image_to_string(gray, config="--psm 6")
        return extract_code_from_text(text), text
    except Exception as exc:
        return None, f"Nie udało się wykonać OCR: {exc}"
