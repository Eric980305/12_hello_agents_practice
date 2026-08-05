import unittest
from datetime import timedelta

from pydantic import ValidationError

from hello_agents_practice.memory import (
    MemoryConfig,
    MemoryItem,
    MemoryManager,
    WorkingMemory,
)
from hello_agents_practice.memory.base import utc_now


class MemoryContractTest(unittest.TestCase):
    def test_validates_records_and_isolates_metadata(self) -> None:
        first = MemoryItem(
            user_id="user-a",
            content="Remember Python",
            memory_type="working",
        )
        second = MemoryItem(
            user_id="user-a",
            content="Remember tests",
            memory_type="working",
        )
        first.metadata["topic"] = "python"

        self.assertEqual(second.metadata, {})
        self.assertIsNotNone(first.created_at.tzinfo)
        with self.assertRaises(ValidationError):
            MemoryItem(user_id=" ", content="x", memory_type="working")
        with self.assertRaises(ValidationError):
            MemoryItem(
                user_id="user-a",
                content="x",
                memory_type="working",
                importance=1.1,
            )


class WorkingMemoryTest(unittest.TestCase):
    def test_enforces_per_user_capacity_and_isolation(self) -> None:
        manager = MemoryManager(MemoryConfig(working_memory_capacity=2))
        oldest = manager.add_memory(user_id="user-a", content="first Python note")
        manager.add_memory(user_id="user-a", content="second Python note")
        manager.add_memory(user_id="user-b", content="other user's note")
        manager.add_memory(user_id="user-a", content="third Python note")

        self.assertEqual(
            manager.get_memory_stats(user_id="user-a")["total_memories"],
            2,
        )
        self.assertEqual(
            manager.get_memory_stats(user_id="user-b")["total_memories"],
            1,
        )
        self.assertFalse(
            manager.remove_memory(user_id="user-a", memory_id="missing")
        )
        with self.assertRaises(KeyError):
            manager.update_memory(
                user_id="user-a",
                memory_id=oldest.id,
                content="evicted",
            )

    def test_prunes_expired_records_and_ranks_relevance_before_importance(self) -> None:
        store = WorkingMemory()
        store.add(
            MemoryItem(
                user_id="user-a",
                content="expired Python note",
                memory_type="working",
                expires_at=utc_now() - timedelta(seconds=1),
            )
        )
        store.add(
            MemoryItem(
                user_id="user-a",
                content="Python function parameters",
                memory_type="working",
                importance=0.2,
            )
        )
        store.add(
            MemoryItem(
                user_id="user-a",
                content="Important meeting",
                memory_type="working",
                importance=1.0,
            )
        )

        results = store.retrieve(
            "Python function",
            user_id="user-a",
            limit=5,
            min_importance=0.0,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].memory.content, "Python function parameters")
        self.assertEqual(len(store.list(user_id="user-a")), 2)

    def test_updates_forgets_and_clears_only_the_requested_user(self) -> None:
        manager = MemoryManager()
        low = manager.add_memory(
            user_id="user-a",
            content="temporary detail",
            importance=0.1,
        )
        keep = manager.add_memory(
            user_id="user-a",
            content="important Python detail",
            importance=0.9,
        )
        other = manager.add_memory(
            user_id="user-b",
            content="other user Python detail",
            importance=0.9,
        )

        updated = manager.update_memory(
            user_id="user-a",
            memory_id=keep.id,
            content="updated Python detail",
            metadata={"source": "test"},
        )
        self.assertEqual(updated.content, "updated Python detail")
        self.assertEqual(updated.metadata, {"source": "test"})
        self.assertEqual(
            manager.forget_memories(
                user_id="user-a",
                strategy="importance_based",
                threshold=0.2,
            ),
            1,
        )
        with self.assertRaises(KeyError):
            manager.update_memory(
                user_id="user-a",
                memory_id=low.id,
                content="gone",
            )
        self.assertEqual(manager.clear_memories(user_id="user-a"), 1)
        self.assertTrue(
            manager.remove_memory(user_id="user-b", memory_id=other.id)
        )

    def test_rejects_memory_types_not_implemented_in_this_stage(self) -> None:
        manager = MemoryManager()

        with self.assertRaisesRegex(ValueError, "ttl_seconds"):
            manager.add_memory(
                user_id="user-a",
                content="temporary fact",
                ttl_seconds=0,
            )
        with self.assertRaisesRegex(ValueError, "not enabled"):
            manager.add_memory(
                user_id="user-a",
                content="persistent fact",
                memory_type="semantic",
            )


if __name__ == "__main__":
    unittest.main()
