"""Tests for OCR normalization utilities."""

import pytest

from vlm_ocr_doc_reader.utils.normalization import normalize_ocr_digits


class TestNormalizeOcrDigits:
    """Test suite for normalize_ocr_digits function."""

    def test_basic_replacements(self) -> None:
        """Test basic OCR error replacements."""
        # O → 0
        assert normalize_ocr_digits("O123") == "0123"

        # o → 0
        assert normalize_ocr_digits("o123") == "0123"

        # l → 1
        assert normalize_ocr_digits("l234") == "1234"

        # I → 1
        assert normalize_ocr_digits("I234") == "1234"

        # S → 5
        assert normalize_ocr_digits("S567") == "5567"

        # B → 8
        assert normalize_ocr_digits("B890") == "8890"

    def test_combined_replacements(self) -> None:
        """Test multiple OCR errors in one string."""
        # O → 0, l → 1, S → 5, B → 8
        assert normalize_ocr_digits("OlSB") == "0158"
        assert normalize_ocr_digits("O1S2B3") == "015283"

    def test_space_removal(self) -> None:
        """Test removal of regular spaces."""
        assert normalize_ocr_digits("1 2 3") == "123"
        assert normalize_ocr_digits("12 34 56") == "123456"

    def test_non_breaking_space_removal(self) -> None:
        """Test removal of non-breaking spaces (\xa0)."""
        # \xa0 is non-breaking space
        assert normalize_ocr_digits("1\xa02\xa03") == "123"

    def test_hyphen_removal(self) -> None:
        """Test removal of hyphens."""
        assert normalize_ocr_digits("123-456") == "123456"
        assert normalize_ocr_digits("1-2-3-4") == "1234"

    def test_combined_separators(self) -> None:
        """Test removal of multiple separator types."""
        assert normalize_ocr_digits("12-34 56") == "123456"
        assert normalize_ocr_digits("1 2-3\xa04") == "1234"

    def test_digit_extraction(self) -> None:
        """Test that only digits are extracted."""
        # Letters should be removed
        assert normalize_ocr_digits("abc123def") == "123"

        # Mixed with OCR errors
        assert normalize_ocr_digits("OlS123xyz") == "015123"

    def test_none_input(self) -> None:
        """Test None input returns None."""
        assert normalize_ocr_digits(None) is None

    def test_empty_string(self) -> None:
        """Test empty string returns None."""
        assert normalize_ocr_digits("") is None

    def test_only_letters(self) -> None:
        """Test string with only non-OCR letters returns None."""
        # Pure letters (not OCR errors) return None
        assert normalize_ocr_digits("abc") is None
        assert normalize_ocr_digits("xyz") is None
        # But OCR error letters become digits
        assert normalize_ocr_digits("OlSB") == "0158"  # O→0, l→1, S→5, B→8

    def test_expected_length_valid(self) -> None:
        """Test expected_length validation when length matches."""
        assert normalize_ocr_digits("123", expected_length=3) == "123"
        assert normalize_ocr_digits("O1S2", expected_length=4) == "0152"

    def test_expected_length_invalid(self) -> None:
        """Test expected_length validation when length doesn't match."""
        assert normalize_ocr_digits("123", expected_length=5) is None
        assert normalize_ocr_digits("12345", expected_length=3) is None

    def test_expected_length_none(self) -> None:
        """Test expected_length=None (default behavior)."""
        # Should not validate length
        assert normalize_ocr_digits("123", expected_length=None) == "123"
        assert normalize_ocr_digits("12345", expected_length=None) == "12345"

    def test_real_world_examples(self) -> None:
        """Test realistic OCR error scenarios."""
        # Russian OGRN pattern (13 digits)
        assert normalize_ocr_digits("O1234567890123") == "01234567890123"

        # Phone number with separators
        assert normalize_ocr_digits("123-456 78 90") == "1234567890"

        # Document number with OCR errors
        assert normalize_ocr_digits("I23-456 789") == "123456789"

        # Mixed case OCR errors
        assert normalize_ocr_digits("O123-l56-S89") == "0123156589"

    def test_only_digits_no_changes(self) -> None:
        """Test that pure digit strings pass through unchanged."""
        assert normalize_ocr_digits("1234567890") == "1234567890"
        assert normalize_ocr_digits("0") == "0"

    def test_multiple_replacements_same_char(self) -> None:
        """Test multiple occurrences of same OCR error."""
        assert normalize_ocr_digits("OOO") == "000"
        assert normalize_ocr_digits("lll") == "111"
        assert normalize_ocr_digits("SSS") == "555"
        assert normalize_ocr_digits("BBB") == "888"

    def test_leading_trailing_separators(self) -> None:
        """Test separators at beginning and end."""
        assert normalize_ocr_digits("-123-") == "123"
        assert normalize_ocr_digits(" 123 ") == "123"
        assert normalize_ocr_digits("\xa0123\xa0") == "123"
