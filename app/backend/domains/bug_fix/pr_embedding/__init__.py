"""PR Embedding — TF-IDF vector search over historical PR review records.

Integrated from the standalone pr-embedding service. Provides semantic
search capabilities for bug fix analysis.
"""
from app.backend.domains.bug_fix.pr_embedding.search import search_reviews
from app.backend.domains.bug_fix.pr_embedding.tokenizer import tokenize

__all__ = ["search_reviews", "tokenize"]
