"""
Knowledge Base (KB) Tool

Provides policy and FAQ lookups:
- search_policy: Search the knowledge base for relevant articles
  using weighted keyword matching with synonym expansion.
- get_article: Retrieve a specific article by article_id.
- list_topics: List all available article titles and IDs.

Data source: data/knowledge_base.json (mock)
"""

import json
import os
import re
from typing import Any, Dict, List

from .base import BaseTool


# ── Core synonym map for customer-service terms ──────────────────────────────
# This covers common paraphrases customers use. Article-level synonyms
# (from the JSON) are merged at search time for per-article expansion.
CORE_SYNONYMS: Dict[str, List[str]] = {
    "refund": ["money back", "reimburse", "credit", "cashback", "reimbursement", "repay"],
    "return": ["send back", "give back", "return window", "return period"],
    "cancel": ["cancellation", "void", "abort", "cancelled"],
    "shipping": ["delivery", "dispatch", "ship", "deliver", "courier"],
    "warranty": ["guarantee", "coverage", "warranty claim"],
    "damaged": ["broken", "defective", "faulty", "cracked", "not working", "dead on arrival", "doa"],
    "exchange": ["swap", "size change", "color change", "wrong size", "wrong color"],
    "payment": ["pay", "upi", "credit card", "debit card", "cod", "cash on delivery"],
    "escalation": ["escalate", "human agent", "manager", "supervisor", "specialist"],
    "contact": ["support", "help", "phone", "email", "helpline", "reach", "customer service"],
}

# Build a reverse map: phrase -> canonical keyword
_REVERSE_SYNONYM_MAP: Dict[str, str] = {}
for canonical, synonyms in CORE_SYNONYMS.items():
    for syn in synonyms:
        _REVERSE_SYNONYM_MAP[syn.lower()] = canonical.lower()


def _load_kb() -> dict:
    """Load knowledge base data from JSON file."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base.json")
    with open(path) as f:
        return json.load(f)


def _expand_query_with_synonyms(query: str) -> List[str]:
    """
    Expand a query by adding canonical keywords for any synonym matches.

    For example: "can I get my money back" → adds "refund" to keywords
    because "money back" is a synonym of "refund".

    Returns the expanded list of keywords (original + canonical expansions).
    """
    query_lower = query.lower().strip()

    if not query_lower:
        return []

    # Extract meaningful keywords (skip short/common words)
    stop_words = {
        "is", "the", "a", "an", "of", "to", "in", "for", "and", "or", "my", "me",
        "what", "how", "do", "does", "your", "you", "i", "it", "be", "on", "with",
        "can", "this", "that", "from", "have", "has", "been", "was", "will", "would",
        "should", "could", "about", "there", "their", "they", "are", "its", "get",
        "got", "please", "want", "need", "tell", "know", "also", "any",
    }
    # Strip trailing/leading punctuation from each token before filtering
    words = []
    for w in query_lower.split():
        cleaned = w.strip(".,;:?!\"'()[]{}—–-")
        if len(cleaned) > 2 and cleaned not in stop_words:
            words.append(cleaned)

    if not words:
        # Fallback: try the whole query only if it has meaningful content
        fallback = query_lower.strip(".,;:?!\"'()[]{}—–-")
        if len(fallback) > 2:
            words = [fallback]
        else:
            return []

    # Check for multi-word synonym phrases in the query
    expanded = set(words)
    for phrase, canonical in _REVERSE_SYNONYM_MAP.items():
        if phrase in query_lower:
            expanded.add(canonical)
            # Also add the individual words of the phrase for matching
            for w in phrase.split():
                if len(w) > 2 and w not in stop_words:
                    expanded.add(w)

    # Also expand single-word synonyms
    for word in list(words):
        if word in _REVERSE_SYNONYM_MAP:
            expanded.add(_REVERSE_SYNONYM_MAP[word])

    return list(expanded)


def _keyword_match(query: str, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Search articles using weighted keyword matching with synonym expansion.

    Scoring weights:
      - Title match:   3 points per keyword (strongest relevance signal)
      - Tag match:     2 points per keyword (curated labels)
      - Synonym match: 2 points per keyword (article-defined synonyms)
      - Content match: 1 point per keyword (body text, noisier)

    Keywords are expanded using the core synonym map and per-article
    synonym fields to catch paraphrased queries.
    """
    keywords = _expand_query_with_synonyms(query)

    if not keywords:
        return []

    results = []
    for article in articles:
        title = article.get("title", "").lower()
        content = article.get("content", "").lower()
        tags = [t.lower() for t in article.get("tags", [])]
        tags_str = " ".join(tags)
        article_synonyms = [s.lower() for s in article.get("synonyms", [])]
        synonyms_str = " ".join(article_synonyms)

        score = 0
        for kw in keywords:
            # Title match (highest weight)
            if kw in title:
                score += 3
            # Tag match (medium-high weight)
            if kw in tags_str:
                score += 2
            # Article synonym match (medium-high weight)
            if kw in synonyms_str:
                score += 2
            # Content match (base weight)
            if kw in content:
                score += 1

        if score > 0:
            results.append((score, article))

    # Sort by relevance (weighted score), descending
    results.sort(key=lambda x: x[0], reverse=True)
    return [article for _, article in results]


class KBTool(BaseTool):
    """Knowledge Base — policy lookup, FAQ search, article retrieval."""

    name = "kb"
    description = (
        "Knowledge Base for policy and FAQ lookups. Use this tool when "
        "the customer asks about company policies, rules, procedures, "
        "return/refund/exchange/warranty/shipping/cancellation policies, "
        "or how things work. "
        "Operations: "
        "(1) search_policy — search for company policies by natural language query. "
        "(2) get_article — retrieve a specific article by article_id (e.g. KB-001). "
        "(3) list_topics — list all available policy article titles and IDs. "
        "Do NOT use this tool for order operations — use the oms tool instead."
    )
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search_policy", "get_article", "list_topics"],
                "description": "The KB operation to perform.",
            },
            "query": {
                "type": "string",
                "description": "Natural language search query for policy lookup (required for search_policy).",
            },
            "article_id": {
                "type": "string",
                "description": "Article ID to retrieve (required for get_article, e.g. KB-001).",
            },
        },
        "required": ["operation"],
    }

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a KB operation against mock knowledge base data."""
        data = _load_kb()
        articles = data.get("articles", [])

        op = params.get("operation")

        if op == "search_policy":
            query = params.get("query", "")
            if not query.strip():
                return {"status": "error", "message": "Search query cannot be empty"}

            results = _keyword_match(query, articles)

            if not results:
                return {
                    "status": "success",
                    "message": "No matching articles found. Try rephrasing your question.",
                    "data": [],
                }

            # Return top 3 most relevant articles
            top_results = results[:3]
            return {
                "status": "success",
                "message": f"Found {len(results)} matching article(s)",
                "data": top_results,
            }

        elif op == "get_article":
            article_id = params.get("article_id", "").strip().upper()
            if not article_id:
                return {"status": "error", "message": "article_id is required for get_article"}

            for article in articles:
                if article.get("article_id", "").upper() == article_id:
                    return {
                        "status": "success",
                        "message": f"Article {article_id} retrieved",
                        "data": article,
                    }

            return {
                "status": "error",
                "message": f"Article {article_id} not found",
            }

        elif op == "list_topics":
            topics = [
                {"article_id": a["article_id"], "title": a["title"]}
                for a in articles
            ]
            return {
                "status": "success",
                "message": f"{len(topics)} articles available",
                "data": topics,
            }

        return {"status": "error", "message": f"Unknown KB operation: {op}"}
