"""Majority voting for Level 2 verify (ADR-002).

Pure logic: given N OCR samples for the same entity across different axes,
produce (value, context, confidence, verified).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

_NO_DATA_KEY = "__NO_DATA__"


@dataclass(frozen=True)
class VoteSample:
    """Single OCR sample for voting.

    Attributes:
        value: Raw OCR value (or None/empty for no_data).
        context: Context snippet (may be None).
        status: 'ok' | 'no_data' | 'error'. Error samples do not vote.
    """

    value: Optional[str]
    context: Optional[str]
    status: str = "ok"


def normalize_for_vote(value: Optional[str]) -> str:
    """Normalize OCR value for equality comparison.

    Rules: None/whitespace → _NO_DATA_KEY; otherwise strip, collapse internal
    whitespace to single spaces, lowercase. Leaves the original value untouched.
    """
    if value is None:
        return _NO_DATA_KEY
    s = value.strip()
    if not s:
        return _NO_DATA_KEY
    return " ".join(s.split()).lower()


def majority_vote(
    samples: Iterable[VoteSample],
) -> Tuple[str, Optional[str], str, bool]:
    """Pick winner across samples.

    Voting:
      - Only samples with status in ('ok', 'no_data') vote. Errors are skipped.
      - Votes are grouped by normalize_for_vote(value).
      - Winner = group with most votes; ties broken by earliest position in input.
      - If no samples voted: returns ("", None, "0/0", False).

    Output:
      value     — original (un-normalized) value of the first sample in the winning
                  group; empty string if winner is NO_DATA.
      context   — context from the same sample.
      confidence — "k/N" where k = winner votes, N = number of valid voters.
      verified  — True iff k == N AND N == total input samples (no errors at all).
    """
    samples_list: List[VoteSample] = list(samples)
    total = len(samples_list)

    valid: List[VoteSample] = [s for s in samples_list if s.status in ("ok", "no_data")]
    n = len(valid)
    if n == 0:
        return ("", None, f"0/{total}", False)

    groups: dict[str, List[VoteSample]] = {}
    order: List[str] = []
    for s in valid:
        key = normalize_for_vote(s.value)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(s)

    winner_key = max(order, key=lambda k: (len(groups[k]), -order.index(k)))
    winner_samples = groups[winner_key]
    k = len(winner_samples)

    first = winner_samples[0]
    value = "" if winner_key == _NO_DATA_KEY else (first.value or "").strip()
    context = first.context

    confidence = f"{k}/{n}"
    verified = (k == n) and (n == total)
    return (value, context, confidence, verified)
