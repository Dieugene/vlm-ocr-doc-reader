"""Common data schemas."""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class PageInfo:
    """Information about a document page.

    Attributes:
        index: Page number (1-based)
        image: Page image as PNG bytes
    """
    index: int
    image: bytes


@dataclass
class ClusterInfo:
    """Information about a page cluster.

    Attributes:
        cluster_id: Cluster identifier
        page_indices: List of page indices in this cluster
        description: Semantic description of cluster content
    """
    cluster_id: int
    page_indices: List[int]
    description: str


@dataclass
class TriageResult:
    """Result of triage operation.

    Attributes:
        matching_pages: List of page indices matching criteria
        reason: Explanation of why these pages match
    """
    matching_pages: List[int]
    reason: str
