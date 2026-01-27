"""OCR normalization utilities for fixing common OCR errors."""

from typing import Optional


def normalize_ocr_digits(
    raw: str,
    expected_length: Optional[int] = None,
) -> Optional[str]:
    """Normalize OCR digits by fixing common errors.

    Replaces:
    - O, o → 0
    - l, I → 1
    - S → 5
    - B → 8

    Also removes spaces, non-breaking spaces (\xa0), and hyphens.

    Args:
        raw: Raw text from OCR output
        expected_length: Expected length of normalized string (optional).
                        If provided, returns None if length doesn't match.

    Returns:
        Normalized digit string or None if:
        - Input is None
        - No digits found after normalization
        - Length doesn't match expected_length

    Examples:
        >>> normalize_ocr_digits("O123")
        '0123'
        >>> normalize_ocr_digits("l23-456")
        '123456'
        >>> normalize_ocr_digits("SB123")
        '58123'
        >>> normalize_ocr_digits("123", expected_length=3)
        '123'
        >>> normalize_ocr_digits("123", expected_length=5)
        None
    """
    if raw is None:
        return None

    # Convert to string and remove common separators
    cleaned = (
        str(raw)
        .replace(" ", "")
        .replace("\xa0", "")  # Non-breaking space
        .replace("-", "")
    )

    # Replace common OCR errors
    cleaned = (
        cleaned.replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("I", "1")
        .replace("S", "5")
        .replace("B", "8")
    )

    # Extract only digits
    digits = "".join(ch for ch in cleaned if ch.isdigit())

    # Check expected length if provided
    if expected_length is not None and len(digits) != expected_length:
        return None

    # Return None if no digits found
    return digits or None
