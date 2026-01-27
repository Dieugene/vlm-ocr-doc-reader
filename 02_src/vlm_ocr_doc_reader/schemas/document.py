"""Document data schemas - contract with project 07_agentic-doc-processing."""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class HeaderInfo:
    """Information about a document header.

    Attributes:
        level: Header level (1 for main, 2 for subheaders, etc.)
        title: Header text
        page: Page number (1-based)
    """
    level: int
    title: str
    page: int


@dataclass
class TableInfo:
    """Information about a table in the document.

    Attributes:
        id: Table identifier (e.g., "table_1", "table_2")
        type: Table type - "NUMERIC" or "TEXT_MATRIX" (future implementation)
        page: Page number (1-based)
        location: Bounding box and page info {"bbox": [x1, y1, x2, y2], "page": int}
        preview: Brief description of table content
        cell_flattened: Flattened cell list for TEXT_MATRIX tables (future)
    """
    id: str
    type: str  # "NUMERIC" or "TEXT_MATRIX"
    page: int
    location: Dict[str, Any]
    preview: str
    cell_flattened: List[str] = None


@dataclass
class DocumentData:
    """Result of full document analysis - contract with project 07.

    Attributes:
        text: Full document text
        structure: Hierarchical structure {"headers": [HeaderInfo, ...]}
        tables: List of tables (empty in v0.1.0, will be implemented in future versions)
    """
    text: str
    structure: Dict[str, Any]
    tables: List[Dict[str, Any]] = field(default_factory=list)
