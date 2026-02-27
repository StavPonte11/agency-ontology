"""Routers package — re-exports all sub-routers for main.py."""
from services.retrieval_api.routers import lookup, search, enrich, schema_context, feedback

__all__ = ["lookup", "search", "enrich", "schema_context", "feedback"]
