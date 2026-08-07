import sqlite3
import tempfile
import unittest
from pathlib import Path

from apps.user_store import UserAccountStore


class UserAccountStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "accounts.db"
        self.store = UserAccountStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_registers_and_authenticates_without_plaintext_password(self) -> None:
        account = self.store.register("浚民", "correct-horse-battery")

        authenticated = self.store.authenticate("浚民", "correct-horse-battery")
        rejected = self.store.authenticate("浚民", "wrong-password")

        self.assertEqual(authenticated, account)
        self.assertEqual(self.store.get_by_id(account["user_id"]), account)
        self.assertIsNone(self.store.get_by_id("missing-user"))
        self.assertIsNone(rejected)
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT password_salt, password_hash FROM app_users WHERE user_id = ?",
                (account["user_id"],),
            ).fetchone()
        self.assertNotIn(b"correct-horse-battery", row)

    def test_rejects_duplicate_username_case_insensitively(self) -> None:
        self.store.register("Junmin", "correct-horse-battery")

        with self.assertRaisesRegex(ValueError, "已注册"):
            self.store.register("junmin", "another-secure-password")

    def test_validates_username_and_password(self) -> None:
        with self.assertRaisesRegex(ValueError, "2–64"):
            self.store.register("x", "correct-horse-battery")
        with self.assertRaisesRegex(ValueError, "6–256"):
            self.store.register("valid-user", "short")

        account = self.store.register("six-user", "123456")

        self.assertEqual(
            self.store.authenticate("six-user", "123456"),
            account,
        )


if __name__ == "__main__":
    unittest.main()
