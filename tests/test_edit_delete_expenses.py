"""Regression tests for Issue #30: Add expense editing and deletion with historical settlement preservation.

Tests cover:
1. Editing an expense amount.
2. Editing the payer.
3. Editing a description.
4. Editing equal and weighted split configurations.
5. Deleting one expense from a group containing several expenses.
6. Rejecting nonexistent expense IDs for edit and delete.
7. Preserving expense IDs after edits and deletions (no renumbering).
8. Preventing duplicate expense IDs when new expenses are added after edits/deletions.
9. Editing an expense before any settlement.
10. Editing an expense after a partial settlement.
11. Editing an expense after a full settlement.
12. Deleting an expense after settlement records exist.
13. Preserving the exact contents and ordering of settlement history across edits and deletions.
14. Recalculating net balances correctly after changes.
15. Handling overpayments and reverse credits without losing money.
16. Preserving monetary rounding and weighted-share invariants.
17. Ensuring invalid edits and failed deletions do not modify persisted data.
18. Maintaining compatibility with legacy expense records that lack IDs.
19. Ensuring existing expense-adding and settlement behavior remains unchanged.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from split.calc import get_net_balances, who_owes, settle_plan, to_paise
from split.cli import main
from split.io import load_group, save_group


class TestEditDeleteExpenses(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.data_path = Path(self._tmp_dir.name) / "groups.json"
        self.defaults = (self.data_path,)

    def _write_store(self, data):
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _read_store(self):
        with open(self.data_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _run_cli(self, args):
        arguments = ["split"] + args
        out, err = io.StringIO(), io.StringIO()
        handler_returned = True
        with patch.object(sys, "argv", arguments), \
                patch.object(load_group, "__defaults__", self.defaults), \
                patch.object(save_group, "__defaults__", self.defaults), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                main()
            except SystemExit as exc:
                if exc.code == 2:
                    handler_returned = False
                else:
                    raise
        return handler_returned, out.getvalue(), err.getvalue()

    def test_edit_expense_amount(self):
        """1. Editing an expense amount updates balances correctly."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Groceries", "amount": 100.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": []
        }
        self._write_store({"g1": group})

        # Bob owes Alice 50. Now edit amount to 200.
        success, out, _ = self._run_cli(["edit-expense", "g1", "1", "Groceries", "200.0", "alice", "equal"])
        self.assertTrue(success)
        self.assertIn("Updated expense ID 1 in g1.", out)

        store = self._read_store()["g1"]
        self.assertEqual(len(store["expenses"]), 1)
        self.assertEqual(store["expenses"][0]["id"], 1)
        self.assertEqual(store["expenses"][0]["amount"], 200.0)
        self.assertEqual(who_owes(store), [{"from": "bob", "to": "alice", "amount": 100.0}])
        self.assertEqual(get_net_balances(store), {"alice": 10000, "bob": -10000})

    def test_edit_expense_payer(self):
        """2. Editing the payer shifts the obligation correctly."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Groceries", "amount": 100.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": []
        }
        self._write_store({"g1": group})

        # Switch payer from alice to bob
        success, out, _ = self._run_cli(["edit-expense", "g1", "1", "Groceries", "100.0", "bob", "equal"])
        self.assertTrue(success)

        store = self._read_store()["g1"]
        self.assertEqual(store["expenses"][0]["paid_by"], "bob")
        self.assertEqual(who_owes(store), [{"from": "alice", "to": "bob", "amount": 50.0}])
        self.assertEqual(get_net_balances(store), {"alice": -5000, "bob": 5000})

    def test_edit_expense_description(self):
        """3. Editing a description leaves calculations unchanged."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Groceries", "amount": 100.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": []
        }
        self._write_store({"g1": group})

        success, out, _ = self._run_cli(["edit-expense", "g1", "1", "Supermarket Groceries", "100.0", "alice", "equal"])
        self.assertTrue(success)

        store = self._read_store()["g1"]
        self.assertEqual(store["expenses"][0]["description"], "Supermarket Groceries")
        self.assertEqual(who_owes(store), [{"from": "bob", "to": "alice", "amount": 50.0}])

    def test_edit_split_configuration_equal_to_share_and_vice_versa(self):
        """4. Editing equal and weighted split configurations."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob", "charlie"],
            "expenses": [
                {"id": 1, "description": "Dinner", "amount": 90.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": []
        }
        self._write_store({"g1": group})

        # Change from equal split (30 each) to share split (bob=2, charlie=1, alice=0 share -> alice pays for them)
        success, out, _ = self._run_cli([
            "edit-expense", "g1", "1", "Dinner", "90.0", "alice", "share", "bob=2", "charlie=1"
        ])
        self.assertTrue(success)

        store = self._read_store()["g1"]
        exp = store["expenses"][0]
        self.assertEqual(exp["split"], "share")
        self.assertEqual(exp["shares"], {"bob": 2.0, "charlie": 1.0})
        # Bob owes 60, Charlie owes 30
        self.assertEqual(get_net_balances(store), {"alice": 9000, "bob": -6000, "charlie": -3000})

        # Now change it back to equal
        success, out, _ = self._run_cli([
            "edit-expense", "g1", "1", "Dinner", "90.0", "alice", "equal"
        ])
        self.assertTrue(success)
        store = self._read_store()["g1"]
        exp = store["expenses"][0]
        self.assertEqual(exp["split"], "equal")
        self.assertNotIn("shares", exp)
        self.assertEqual(get_net_balances(store), {"alice": 6000, "bob": -3000, "charlie": -3000})

    def test_delete_one_expense_from_multiple(self):
        """5. Deleting one expense from a group containing several expenses."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Breakfast", "amount": 20.0, "paid_by": "alice", "split": "equal"},
                {"id": 2, "description": "Lunch", "amount": 60.0, "paid_by": "bob", "split": "equal"},
                {"id": 3, "description": "Dinner", "amount": 100.0, "paid_by": "alice", "split": "equal"},
            ],
            "settlements": []
        }
        self._write_store({"g1": group})

        # Delete expense 2 (Lunch)
        success, out, _ = self._run_cli(["delete-expense", "g1", "2"])
        self.assertTrue(success)
        self.assertIn("Deleted expense ID 2 ('Lunch') from g1.", out)

        store = self._read_store()["g1"]
        expenses = store["expenses"]
        self.assertEqual(len(expenses), 2)
        self.assertEqual([e["id"] for e in expenses], [1, 3])
        # Remaining: Breakfast (20, alice pays) + Dinner (100, alice pays). Total alice paid 120, bob share 60.
        self.assertEqual(get_net_balances(store), {"alice": 6000, "bob": -6000})
        self.assertEqual(who_owes(store), [{"from": "bob", "to": "alice", "amount": 60.0}])

    def test_reject_nonexistent_group_and_expense_id(self):
        """6. Rejecting nonexistent group and expense IDs with clear errors."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [{"id": 1, "description": "Groceries", "amount": 50.0, "paid_by": "alice", "split": "equal"}],
            "settlements": []
        }
        self._write_store({"g1": group})

        # Nonexistent group
        success, out, _ = self._run_cli(["edit-expense", "nonexistent", "1", "Desc", "50.0", "alice", "equal"])
        self.assertIn("Error: Group 'nonexistent' not found.", out)

        success, out, _ = self._run_cli(["delete-expense", "nonexistent", "1"])
        self.assertIn("Error: Group 'nonexistent' not found.", out)

        # Nonexistent expense ID
        success, out, _ = self._run_cli(["edit-expense", "g1", "999", "Desc", "50.0", "alice", "equal"])
        self.assertIn("Error: Expense with ID '999' not found in group 'g1'.", out)

        success, out, _ = self._run_cli(["delete-expense", "g1", "999"])
        self.assertIn("Error: Expense with ID '999' not found in group 'g1'.", out)

    def test_preserve_expense_ids_after_edit_and_delete_no_renumbering(self):
        """7 & 8. Preserving expense IDs without renumbering and preventing duplicates."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "E1", "amount": 10.0, "paid_by": "alice", "split": "equal"},
                {"id": 2, "description": "E2", "amount": 20.0, "paid_by": "alice", "split": "equal"},
                {"id": 3, "description": "E3", "amount": 30.0, "paid_by": "alice", "split": "equal"},
            ],
            "settlements": []
        }
        self._write_store({"g1": group})

        # Delete expense 2
        self._run_cli(["delete-expense", "g1", "2"])
        store = self._read_store()["g1"]
        self.assertEqual([e["id"] for e in store["expenses"]], [1, 3])

        # Edit expense 3
        self._run_cli(["edit-expense", "g1", "3", "E3-updated", "40.0", "alice", "equal"])
        store = self._read_store()["g1"]
        self.assertEqual([e["id"] for e in store["expenses"]], [1, 3])
        self.assertEqual(store["expenses"][1]["id"], 3)

        # Now add a new expense. It must take next unused ID (4), NOT reuse 2 or 3
        self._run_cli(["add-expense", "g1", "E4", "50.0", "alice", "equal"])
        store = self._read_store()["g1"]
        self.assertEqual([e["id"] for e in store["expenses"]], [1, 3, 4])
        # Ensure IDs are unique
        ids = [e["id"] for e in store["expenses"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_editing_expense_after_partial_settlement(self):
        """10. Editing an expense after a partial settlement preserves history and updates balance."""
        # Alice pays 1000 for equal split -> Bob owes 500.
        # Bob partially settles 200 -> Bob owes 300.
        # Alice edits expense from 1000 to 600 -> Bob total obligation becomes 300.
        # With 200 already paid, Bob now owes 100.
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Party", "amount": 1000.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": [
                {"from": "bob", "to": "alice", "amount": 200.0}
            ]
        }
        self._write_store({"g1": group})

        self.assertEqual(who_owes(group), [{"from": "bob", "to": "alice", "amount": 300.0}])

        # Edit expense 1 to 600
        success, out, _ = self._run_cli(["edit-expense", "g1", "1", "Party", "600.0", "alice", "equal"])
        self.assertTrue(success)

        store = self._read_store()["g1"]
        # Settlement history preserved exactly
        self.assertEqual(store["settlements"], [{"from": "bob", "to": "alice", "amount": 200.0}])
        # Net balances: Alice paid 600, share 300, received 200 settlement -> net +100 (10000 paise).
        # Bob: share 300, paid 200 settlement -> net -100 (-10000 paise).
        self.assertEqual(get_net_balances(store), {"alice": 10000, "bob": -10000})
        self.assertEqual(who_owes(store), [{"from": "bob", "to": "alice", "amount": 100.0}])

    def test_editing_expense_after_full_settlement_creates_reverse_obligation(self):
        """11 & 15. Editing an expense after full settlement creates reverse credit/obligation correctly."""
        # Alice pays 1000 -> Bob settles 500 in full.
        # Alice realizes expense was only 400! Bob should only have owed 200.
        # Because Bob actually transferred 500, Alice now owes Bob 100.
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Electric Bill", "amount": 1000.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": [
                {"from": "bob", "to": "alice", "amount": 500.0}
            ]
        }
        self._write_store({"g1": group})

        self.assertEqual(who_owes(group), [])

        success, out, _ = self._run_cli(["edit-expense", "g1", "1", "Electric Bill", "400.0", "alice", "equal"])
        self.assertTrue(success)

        store = self._read_store()["g1"]
        # Settlement history unchanged!
        self.assertEqual(store["settlements"], [{"from": "bob", "to": "alice", "amount": 500.0}])
        # Balances: Alice paid 400, share 200, Bob share 200.
        # Bob settled 500 to Alice.
        # Alice net balance: +400 (paid) - 200 (share) - 500 (received) = -300 (-30000 paise).
        # Bob net balance: 0 (paid) - 200 (share) + 500 (paid settlement) = +300 (+30000 paise).
        self.assertEqual(get_net_balances(store), {"alice": -30000, "bob": 30000})
        # who_owes shows Alice owes Bob 300
        self.assertEqual(who_owes(store), [{"from": "alice", "to": "bob", "amount": 300.0}])
        self.assertEqual(settle_plan(store), [{"from": "alice", "to": "bob", "amount": 300.0}])

    def test_deleting_expense_after_settlement_preserves_settlement_history(self):
        """12 & 13. Deleting an expense preserves full settlement history unchanged."""
        # Alice pays 400 -> Bob pays 200.
        # If the expense is deleted (e.g. cancelled/refunded), Bob's 200 payment remains recorded,
        # so Alice owes Bob 200.
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Concert", "amount": 400.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": [
                {"from": "bob", "to": "alice", "amount": 200.0}
            ]
        }
        self._write_store({"g1": group})

        success, out, _ = self._run_cli(["delete-expense", "g1", "1"])
        self.assertTrue(success)

        store = self._read_store()["g1"]
        self.assertEqual(store["expenses"], [])
        self.assertEqual(store["settlements"], [{"from": "bob", "to": "alice", "amount": 200.0}])
        # Net balances: Alice -200, Bob +200
        self.assertEqual(get_net_balances(store), {"alice": -20000, "bob": 20000})
        self.assertEqual(who_owes(store), [{"from": "alice", "to": "bob", "amount": 200.0}])

    def test_failed_edits_and_deletions_leave_store_unmodified(self):
        """17. Validation failures leave persisted store completely byte-for-byte unmodified."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob"],
            "expenses": [
                {"id": 1, "description": "Groceries", "amount": 100.0, "paid_by": "alice", "split": "equal"}
            ],
            "settlements": [
                {"from": "bob", "to": "alice", "amount": 20.0}
            ]
        }
        self._write_store({"g1": group})
        original_bytes = self.data_path.read_bytes()

        invalid_calls = [
            # Invalid amount (zero, negative, non-numeric, inf, nan)
            ["edit-expense", "g1", "1", "Groceries", "0", "alice", "equal"],
            ["edit-expense", "g1", "1", "Groceries", "-50", "alice", "equal"],
            ["edit-expense", "g1", "1", "Groceries", "abc", "alice", "equal"],
            ["edit-expense", "g1", "1", "Groceries", "nan", "alice", "equal"],
            ["edit-expense", "g1", "1", "Groceries", "inf", "alice", "equal"],
            # Unknown member as payer
            ["edit-expense", "g1", "1", "Groceries", "100.0", "charlie", "equal"],
            # Invalid share split options
            ["edit-expense", "g1", "1", "Groceries", "100.0", "alice", "share"],
            ["edit-expense", "g1", "1", "Groceries", "100.0", "alice", "share", "alice=zero"],
            ["edit-expense", "g1", "1", "Groceries", "100.0", "alice", "share", "alice=-1"],
            ["edit-expense", "g1", "1", "Groceries", "100.0", "alice", "equal", "alice=1"],
            # Nonexistent ID
            ["edit-expense", "g1", "99", "Groceries", "100.0", "alice", "equal"],
            ["delete-expense", "g1", "99"],
        ]

        for cmd in invalid_calls:
            with self.subTest(cmd=cmd):
                self._run_cli(cmd)
                self.assertEqual(self.data_path.read_bytes(), original_bytes)

    def test_legacy_expenses_without_ids(self):
        """18. Support existing groups whose expenses lack IDs (positional fallback, no silent write on read)."""
        group = {
            "name": "Legacy",
            "members": ["alice", "bob"],
            "expenses": [
                {"description": "Old Exp 1", "amount": 100.0, "paid_by": "alice", "split": "equal"},
                {"description": "Old Exp 2", "amount": 200.0, "paid_by": "bob", "split": "equal"},
            ],
            "settlements": []
        }
        self._write_store({"legacy": group})
        original_bytes = self.data_path.read_bytes()

        # Read-only operations like summary or who_owes do NOT modify the file
        self._run_cli(["summary", "legacy"])
        self.assertEqual(self.data_path.read_bytes(), original_bytes)

        # Deleting expense "1" should match 1-based index 1 ("Old Exp 1")
        success, out, _ = self._run_cli(["delete-expense", "legacy", "1"])
        self.assertTrue(success)

        store = self._read_store()["legacy"]
        self.assertEqual(len(store["expenses"]), 1)
        self.assertEqual(store["expenses"][0]["description"], "Old Exp 2")

        # Now add a new expense: it should get id 2 (or max existing id + 1)
        self._run_cli(["add-expense", "legacy", "New Exp", "50.0", "alice", "equal"])
        store = self._read_store()["legacy"]
        self.assertEqual(len(store["expenses"]), 2)
        self.assertEqual(store["expenses"][1]["id"], 2)

    def test_monetary_rounding_and_shares_preserved_after_edit(self):
        """16. Invariant: Sum of net balances in paise is always exactly 0 after edit and delete."""
        group = {
            "name": "Flatmates",
            "members": ["alice", "bob", "charlie"],
            "expenses": [
                {"id": 1, "description": "Lunch", "amount": 10.05, "paid_by": "alice", "split": "share", "shares": {"alice": 2, "bob": 1, "charlie": 1}}
            ],
            "settlements": [
                {"from": "bob", "to": "alice", "amount": 2.51}
            ]
        }
        self._write_store({"g1": group})

        # Edit amount to fractional 2.675 (268 paise) with equal split
        self._run_cli(["edit-expense", "g1", "1", "Lunch", "2.675", "alice", "equal"])
        store = self._read_store()["g1"]
        balances = get_net_balances(store)
        self.assertEqual(sum(balances.values()), 0)

        # Add another expense and then delete the first one
        self._run_cli(["add-expense", "g1", "Coffee", "12.345", "bob", "equal"])
        self._run_cli(["delete-expense", "g1", "1"])

        store = self._read_store()["g1"]
        balances = get_net_balances(store)
        self.assertEqual(sum(balances.values()), 0)
        debts = who_owes(store)
        plan = settle_plan(store)
        # Net balance sum is always 0
        self.assertEqual(sum(balances.values()), 0)


if __name__ == "__main__":
    unittest.main()
