"""Web search utility — wraps Tavily (or fallback) with retry and error handling."""
from __future__ import annotations
import logging
import asyncio
import os
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 1.5


async def search_web(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
) -> List[Dict[str, Any]]:
    """
    Perform a web search using Tavily API.
    Returns a list of result dicts with 'title', 'url', 'content'.
    Returns empty list if API is unavailable.
    Raises RuntimeError only if the API key is missing entirely.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY environment variable is not set. "
            "Please add it to your .env file."
        )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": search_depth,
                        "topic": "general",
                        "max_results": max_results,
                        "include_answer": False,
                    },
                )
                response.raise_for_status()
                results = response.json().get("results", [])

            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.0),
                }
                for r in results
            ]

        except Exception as e:
            last_error = e
            logger.warning(f"Search attempt {attempt}/{MAX_RETRIES} failed for query '{query[:50]}': {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)

    logger.error(f"All search retries failed for query '{query[:50]}': {last_error}")
    raise RuntimeError(f"Web search failed: {last_error}")
