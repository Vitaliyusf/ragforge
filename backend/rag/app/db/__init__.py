"""Database abstractions for document storage."""
from app.db.session import get_document_store
from app.db.interfaces import IDocumentStore

__all__ = ["get_document_store", "IDocumentStore"]