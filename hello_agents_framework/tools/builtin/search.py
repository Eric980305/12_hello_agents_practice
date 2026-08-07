"""Multi-provider web search with deterministic fallback."""

import os
from collections.abc import Mapping
from typing import Any, Literal

from ..base import Tool

try:
    from tavily import TavilyClient
except ImportError:  # pragma: no cover - dependency availability is runtime state.
    TavilyClient = None  # type: ignore[assignment,misc]

try:
    from serpapi.google_search import GoogleSearch
except ImportError:  # pragma: no cover - dependency availability is runtime state.
    GoogleSearch = None  # type: ignore[assignment,misc]


SearchBackend = Literal["hybrid", "tavily", "serpapi"]
SUPPORTED_BACKENDS = {"hybrid", "tavily", "serpapi"}


class SearchTool(Tool):
    """Search Tavily first and optionally fall back to SerpAPI."""

    name = "search"
    description = (
        "Search the current web through configured Tavily or SerpAPI providers "
        "and return concise results with source URLs."
    )

    def __init__(
        self,
        backend: SearchBackend = "hybrid",
        tavily_key: str | None = None,
        serpapi_key: str | None = None,
        max_results: int = 3,
    ) -> None:
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"unsupported search backend: {backend}.")
        if not 1 <= max_results <= 10:
            raise ValueError("max_results must be between 1 and 10.")

        self.backend = backend
        self.max_results = max_results
        self._tavily_key = tavily_key or os.getenv("TAVILY_API_KEY")
        self._serpapi_key = serpapi_key or os.getenv("SERPAPI_API_KEY")
        self._tavily_client = (
            TavilyClient(api_key=self._tavily_key)
            if self._tavily_key and TavilyClient is not None
            else None
        )
        available: list[str] = []
        if self._tavily_client is not None:
            available.append("tavily")
        if self._serpapi_key and GoogleSearch is not None:
            available.append("serpapi")
        self.available_backends = tuple(available)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Focused web search query.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def run(self, parameters: Mapping[str, Any]) -> str:
        query_value = parameters.get("query")
        if not isinstance(query_value, str):
            raise TypeError("search query must be a string.")
        query = query_value.strip()
        if not query:
            raise ValueError("search query must not be empty.")

        candidates = self._candidate_backends()
        if not candidates:
            if self.backend == "hybrid":
                return (
                    "Search unavailable: configure TAVILY_API_KEY or "
                    "SERPAPI_API_KEY."
                )
            return f"Search unavailable: {self.backend} backend is not configured."

        failures: list[str] = []
        completed_without_results = False
        for backend in candidates:
            try:
                result = (
                    self._search_tavily(query)
                    if backend == "tavily"
                    else self._search_serpapi(query)
                )
            except Exception:
                failures.append(backend)
                continue
            if result:
                return result
            completed_without_results = True

        if completed_without_results:
            return "Search completed: no results found."
        return "Search failed: " + ", ".join(failures) + " backend failed."

    def _candidate_backends(self) -> tuple[str, ...]:
        if self.backend == "hybrid":
            return self.available_backends
        if self.backend in self.available_backends:
            return (self.backend,)
        return ()

    def _search_tavily(self, query: str) -> str | None:
        if self._tavily_client is None:
            return None
        response = self._tavily_client.search(
            query=query,
            search_depth="basic",
            include_answer=True,
            max_results=self.max_results,
        )
        if not isinstance(response, Mapping):
            return None

        answer = response.get("answer")
        answer_text = answer.strip() if isinstance(answer, str) else ""
        entries = self._format_entries(response.get("results"), "url", "content")
        return self._compose_result("tavily", answer_text, entries)

    def _search_serpapi(self, query: str) -> str | None:
        if not self._serpapi_key or GoogleSearch is None:
            return None
        response = GoogleSearch(
            {
                "engine": "google",
                "q": query,
                "api_key": self._serpapi_key,
                "gl": "cn",
                "hl": "zh-cn",
                "num": self.max_results,
            }
        ).get_dict()
        if not isinstance(response, Mapping) or response.get("error"):
            return None

        answer_text = self._extract_direct_answer(response)
        entries = self._format_entries(
            response.get("organic_results"),
            "link",
            "snippet",
        )
        return self._compose_result("serpapi", answer_text, entries)

    def _format_entries(
        self,
        raw_entries: object,
        url_key: str,
        content_key: str,
    ) -> list[str]:
        if not isinstance(raw_entries, list):
            return []
        entries: list[str] = []
        for index, item in enumerate(raw_entries[: self.max_results], start=1):
            if not isinstance(item, Mapping):
                continue
            title = str(item.get("title", "Untitled result")).strip()
            content = str(item.get(content_key, "")).strip()[:500]
            url = str(item.get(url_key, "")).strip()
            parts = [f"[{index}] {title or 'Untitled result'}"]
            if content:
                parts.append(content)
            if url:
                parts.append(f"Source: {url}")
            entries.append("\n".join(parts))
        return entries

    @staticmethod
    def _extract_direct_answer(response: Mapping[str, Any]) -> str:
        for key in ("answer_box", "knowledge_graph"):
            value = response.get(key)
            if not isinstance(value, Mapping):
                continue
            for field in ("answer", "result", "description", "snippet"):
                text = value.get(field)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return ""

    @staticmethod
    def _compose_result(
        backend: str,
        answer: str,
        entries: list[str],
    ) -> str | None:
        if not answer and not entries:
            return None
        sections = [f"Search backend: {backend}"]
        if answer:
            sections.append(f"Answer: {answer}")
        sections.extend(entries)
        return "\n\n".join(sections)


__all__ = ["SearchTool"]
