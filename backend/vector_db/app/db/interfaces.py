"""Vector store interfaces for chunk-native operations."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

import numpy as np

from app.core.constants import MAX_VERIFY_IDS, VERIFIABLE_ID_FIELDS


def verify_targets(field: str, values: List[str]) -> Set[str]:
    """Validate one id-existence request and return its de-duplicated ids.

    Shared by every backend so that the two limits which keep
    :meth:`IVectorStore.lookup_ids` from becoming a general query — the field
    allow-list and the id cap — cannot drift apart between implementations.

    Raises:
        ValueError: If the field is not verifiable, or too many ids were
            named. Both are refusals rather than a silently narrowed query:
            a truncated verification would report live labels as deleted.
    """
    if field not in VERIFIABLE_ID_FIELDS:
        raise ValueError(f"{field!r} is not a verifiable id field")
    wanted = {str(value) for value in (values or []) if str(value).strip()}
    if len(wanted) > MAX_VERIFY_IDS:
        raise ValueError(
            f"lookup_ids was given {len(wanted)} ids; the limit is {MAX_VERIFY_IDS}"
        )
    return wanted


class IVectorStore(ABC):
    """Interface for chunk storage and retrieval operations."""

    @abstractmethod
    def initialize_collection(self) -> str:
        """Ensure the backing collection and indexes exist."""
        raise NotImplementedError

    @property
    @abstractmethod
    def collection_name(self) -> str:
        """Return the active collection name."""
        raise NotImplementedError

    @abstractmethod
    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Upsert chunk points into the backing store."""
        raise NotImplementedError

    @abstractmethod
    def search_chunks(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
        include_vector: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using the mandatory internal safety filter."""
        raise NotImplementedError

    @abstractmethod
    def search_sparse(
        self,
        query_sparse: Dict[str, List[Any]],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_payload: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search the independent sparse arm with the same safety filters."""
        raise NotImplementedError

    @abstractmethod
    def delete_chunks(self, filters: Dict[str, Any]) -> int:
        """Hard delete chunks using a document/file filter."""
        raise NotImplementedError

    @abstractmethod
    def lookup_ids(
        self,
        field: str,
        values: List[str],
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[str]]:
        """Report which of ``values`` exist under ``filters``.

        Read-only existence check for a caller-supplied list of ids. It is
        deliberately not a query: the caller names every id it asks about,
        so the answer can never contain an identifier the caller did not
        already hold, and ``filters`` — which the service builds from the
        trusted identity, never from caller input — bounds the search to the
        caller's own tenant and ownership scope.

        Args:
            field: The payload field to match on. Implementations must
                reject anything outside
                :data:`app.core.constants.VERIFIABLE_ID_FIELDS`.
            values: The ids to look for.
            filters: Scope conditions, applied as equality matches.

        Returns:
            ``{"present": [...], "retrievable": [...]}`` — the subset of
            ``values`` found at all, and the subset that also passes the
            retrieval safety gate (``retrieval_allowed`` and a
            non-``removed`` review status). The two are separate because a
            chunk that exists but is barred from retrieval is neither a
            deleted label nor a reachable one, and reporting it as either
            would be a lie.
        """
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        """Get the number of stored points."""
        raise NotImplementedError

    def close(self) -> None:
        """Release backing-store resources when explicit shutdown is required."""
