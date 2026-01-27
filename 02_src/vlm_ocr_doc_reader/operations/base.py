"""Base operation class."""

from abc import ABC, abstractmethod
from typing import Any


class BaseOperation(ABC):
    """Abstract base class for all document operations.

    All operations must inherit from this class and implement the execute() method.
    Operations receive a DocumentProcessor instance during initialization.
    """

    def __init__(self, processor: Any):
        """Initialize operation with a document processor.

        Args:
            processor: DocumentProcessor instance (will be properly typed when available)
        """
        self.processor = processor

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the operation.

        Returns:
            Operation-specific result
        """
        pass
