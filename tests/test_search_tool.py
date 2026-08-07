import unittest
from unittest.mock import Mock, patch

from hello_agents_framework.tools import SearchTool


class SearchToolTest(unittest.TestCase):
    def test_hybrid_prefers_tavily_and_normalizes_sources(self) -> None:
        tavily_client = Mock()
        tavily_client.search.return_value = {
            "answer": "Python was created by Guido van Rossum.",
            "results": [
                {
                    "title": "Python history",
                    "content": "Python development began in the late 1980s.",
                    "url": "https://www.python.org/doc/essays/foreword/",
                }
            ],
        }

        with patch(
            "hello_agents_framework.tools.builtin.search.TavilyClient",
            return_value=tavily_client,
        ), patch(
            "hello_agents_framework.tools.builtin.search.GoogleSearch",
        ) as serpapi_search:
            tool = SearchTool(
                backend="hybrid",
                tavily_key="tavily-key",
                serpapi_key="serpapi-key",
            )
            result = tool.run({"query": "Python history"})

        self.assertEqual(tool.available_backends, ("tavily", "serpapi"))
        self.assertIn("Search backend: tavily", result)
        self.assertIn("Python was created", result)
        self.assertIn("https://www.python.org/doc/essays/foreword/", result)
        serpapi_search.assert_not_called()

    def test_hybrid_falls_back_to_serpapi(self) -> None:
        tavily_client = Mock()
        tavily_client.search.side_effect = RuntimeError("provider unavailable")
        serpapi_response = Mock()
        serpapi_response.get_dict.return_value = {
            "organic_results": [
                {
                    "title": "Fallback result",
                    "snippet": "SerpAPI supplied this result.",
                    "link": "https://example.com/fallback",
                }
            ]
        }

        with patch(
            "hello_agents_framework.tools.builtin.search.TavilyClient",
            return_value=tavily_client,
        ), patch(
            "hello_agents_framework.tools.builtin.search.GoogleSearch",
            return_value=serpapi_response,
        ) as serpapi_search:
            tool = SearchTool(
                backend="hybrid",
                tavily_key="tavily-key",
                serpapi_key="serpapi-key",
            )
            result = tool.run({"query": "current topic"})

        self.assertIn("Search backend: serpapi", result)
        self.assertIn("https://example.com/fallback", result)
        serpapi_search.assert_called_once()

    def test_explicit_backend_does_not_fall_back(self) -> None:
        tavily_client = Mock()
        tavily_client.search.side_effect = RuntimeError("provider unavailable")

        with patch(
            "hello_agents_framework.tools.builtin.search.TavilyClient",
            return_value=tavily_client,
        ), patch(
            "hello_agents_framework.tools.builtin.search.GoogleSearch",
        ) as serpapi_search:
            tool = SearchTool(
                backend="tavily",
                tavily_key="tavily-key",
                serpapi_key="serpapi-key",
            )
            result = tool.run({"query": "current topic"})

        self.assertEqual(result, "Search failed: tavily backend failed.")
        serpapi_search.assert_not_called()

    def test_reports_missing_configuration_and_rejects_invalid_input(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            tool = SearchTool()

        self.assertEqual(tool.available_backends, ())
        self.assertEqual(
            tool.run({"query": "Python"}),
            "Search unavailable: configure TAVILY_API_KEY or SERPAPI_API_KEY.",
        )
        with self.assertRaises(ValueError):
            tool.run({"query": "  "})
        with self.assertRaises(TypeError):
            tool.run({"query": ["Python"]})
        with self.assertRaises(ValueError):
            SearchTool(backend="unknown")


if __name__ == "__main__":
    unittest.main()
