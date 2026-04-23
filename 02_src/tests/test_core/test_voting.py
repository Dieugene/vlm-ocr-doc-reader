"""Tests for core/voting.py — majority voting logic for Level 2 verify (ADR-002)."""

from vlm_ocr_doc_reader.core.voting import (
    VoteSample,
    majority_vote,
    normalize_for_vote,
)


class TestNormalizeForVote:
    def test_none_is_no_data(self):
        assert normalize_for_vote(None) == "__NO_DATA__"

    def test_empty_is_no_data(self):
        assert normalize_for_vote("") == "__NO_DATA__"
        assert normalize_for_vote("   ") == "__NO_DATA__"

    def test_strip_and_lower(self):
        assert normalize_for_vote("  ABC  ") == "abc"

    def test_collapse_internal_whitespace(self):
        assert normalize_for_vote("1\n2\t3   4") == "1 2 3 4"

    def test_keeps_punctuation(self):
        # Normalization only handles case/whitespace, not punctuation.
        assert normalize_for_vote("7704-123-456") == "7704-123-456"


class TestMajorityVote:
    def test_unanimous(self):
        samples = [
            VoteSample("7704123456", "ИНН:", "ok"),
            VoteSample("7704123456", "ИНН:", "ok"),
            VoteSample("7704123456", "ИНН:", "ok"),
        ]
        value, context, confidence, verified = majority_vote(samples)
        assert value == "7704123456"
        assert context == "ИНН:"
        assert confidence == "3/3"
        assert verified is True

    def test_majority_2_of_3(self):
        samples = [
            VoteSample("7704123456", "a", "ok"),
            VoteSample("7704123456", "b", "ok"),
            VoteSample("7704123457", "c", "ok"),
        ]
        value, _, confidence, verified = majority_vote(samples)
        assert value == "7704123456"
        assert confidence == "2/3"
        assert verified is False

    def test_all_different_picks_first(self):
        samples = [
            VoteSample("a", "c1", "ok"),
            VoteSample("b", "c2", "ok"),
            VoteSample("c", "c3", "ok"),
        ]
        value, context, confidence, verified = majority_vote(samples)
        assert value == "a"
        assert context == "c1"
        assert confidence == "1/3"
        assert verified is False

    def test_no_data_wins(self):
        samples = [
            VoteSample("", None, "no_data"),
            VoteSample(None, None, "no_data"),
            VoteSample("spurious", "ctx", "ok"),
        ]
        value, context, confidence, verified = majority_vote(samples)
        assert value == ""
        assert context is None
        assert confidence == "2/3"
        assert verified is False

    def test_normalization_groups_case_differences(self):
        samples = [
            VoteSample("OOO Rosatom", "c1", "ok"),
            VoteSample("ooo rosatom", "c2", "ok"),
            VoteSample("Other", "c3", "ok"),
        ]
        value, context, confidence, _ = majority_vote(samples)
        # Winner group has 2 votes; first sample keeps its original casing.
        assert value == "OOO Rosatom"
        assert context == "c1"
        assert confidence == "2/3"

    def test_errors_excluded_from_denominator(self):
        samples = [
            VoteSample("x", "ctx", "ok"),
            VoteSample("x", "ctx2", "ok"),
            VoteSample(None, None, "error"),
        ]
        value, _, confidence, verified = majority_vote(samples)
        assert value == "x"
        assert confidence == "2/2"
        # Not verified: one sample errored, so not unanimous across total inputs.
        assert verified is False

    def test_all_errors(self):
        samples = [
            VoteSample(None, None, "error"),
            VoteSample(None, None, "error"),
        ]
        value, context, confidence, verified = majority_vote(samples)
        assert value == ""
        assert context is None
        assert confidence == "0/2"
        assert verified is False

    def test_empty_input(self):
        value, context, confidence, verified = majority_vote([])
        assert value == ""
        assert context is None
        assert confidence == "0/0"
        assert verified is False

    def test_tie_prefers_earlier_axis(self):
        samples = [
            VoteSample("axis1", "c1", "ok"),
            VoteSample("axis2", "c2", "ok"),
        ]
        value, context, confidence, verified = majority_vote(samples)
        assert value == "axis1"
        assert context == "c1"
        assert confidence == "1/2"
        assert verified is False

    def test_original_value_preserved_not_normalized(self):
        # Winner returns the original (pre-normalization) value.
        samples = [
            VoteSample("  Hello\tWorld  ", "ctx", "ok"),
            VoteSample("hello world", "ctx2", "ok"),
        ]
        value, _, confidence, _ = majority_vote(samples)
        # Both normalize to "hello world"; first sample wins; its original is stripped only
        # (we still strip outer whitespace for a clean stored value, but keep inner casing/tabs).
        assert value == "Hello\tWorld"
        assert confidence == "2/2"
