import unittest

from examples.official_memory_rag_quickstart import _build_rerank_endpoint


class OfficialMemoryRAGQuickstartTest(unittest.TestCase):
    def test_builds_workspace_rerank_endpoint(self) -> None:
        self.assertEqual(
            _build_rerank_endpoint(
                "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
            ),
            "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-api/v1/reranks",
        )

    def test_rejects_non_https_endpoint(self) -> None:
        with self.assertRaises(ValueError):
            _build_rerank_endpoint("http://localhost:8000")


if __name__ == "__main__":
    unittest.main()
