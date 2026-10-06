"""Unit tests for calculation logic in expense-split."""

import copy
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from split.calc import split_equally, split_by_share, who_owes, get_net_balances
from split.cli import cmd_settle


def total_in_paise(result):
    """Adds up split shares exactly, in integer paise."""
    return sum(int(round(value * 100)) for value in result.values())


class TestSplitCalculations(unittest.TestCase):

    def test_split_equally_even_division(self):
        """Even division without remainder should divide accurately."""
        res = split_equally(120, 3)
        self.assertEqual(res["each"], 40)

    def test_split_equally_invalid_people(self):
        """Zero or negative number of people should raise ValueError."""
        with self.assertRaises(ValueError):
            split_equally(100, 0)

    def test_split_by_share_basic(self):
        """Splitting by proportional weights should divide correctly."""
        shares = {"alice": 2, "bob": 1}
        res = split_by_share(90, shares)
        self.assertEqual(res["alice"], 60.0)
        self.assertEqual(res["bob"], 30.0)

    def test_split_by_share_original_bug_totals_exactly(self):
        """₹100 split with equal weights must still total exactly ₹100.00."""
        shares = {"alice": 1, "bob": 1, "charlie": 1}
        res = split_by_share(100, shares)
        self.assertEqual(set(res), {"alice", "bob", "charlie"})
        self.assertEqual(total_in_paise(res), 10000)

    def test_split_by_share_uneven_weights(self):
        """Uneven weights stay proportional and preserve the exact total."""
        shares = {"alice": 2, "bob": 1, "charlie": 1}
        res = split_by_share(100, shares)
        self.assertEqual(set(res), {"alice", "bob", "charlie"})
        self.assertEqual(res["alice"], 50.0)
        self.assertEqual(res["bob"], 25.0)
        self.assertEqual(res["charlie"], 25.0)
        self.assertEqual(total_in_paise(res), 10000)

    def test_split_by_share_rounding_heavy(self):
        """Many fractional paise still leave no money lost or created."""
        shares = {"alice": 1, "bob": 1, "charlie": 1, "dave": 1, "erin": 1}
        res = split_by_share(0.03, shares)
        self.assertEqual(set(res), {"alice", "bob", "charlie", "dave", "erin"})
        self.assertEqual(total_in_paise(res), 3)

    def test_split_by_share_is_deterministic(self):
        """Identical inputs always produce identical output."""
        shares = {"alice": 3, "bob": 2, "charlie": 4}
        first = split_by_share(123.45, shares)
        for _ in range(5):
            self.assertEqual(split_by_share(123.45, shares), first)

    def test_split_by_share_exact_division_unchanged(self):
        """Splitting amounts that divide exactly keeps the expected values."""
        self.assertEqual(split_by_share(90, {"alice": 2, "bob": 1}),
                         {"alice": 60.0, "bob": 30.0})
        self.assertEqual(split_by_share(100, {"alice": 1, "bob": 1}),
                         {"alice": 50.0, "bob": 50.0})

    def test_split_by_share_zero_total_weights(self):
        """Zero or negative total weights should still raise ValueError."""
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": 0, "bob": 0})
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": -1, "bob": -1})

    def test_split_by_share_rejects_zero_individual_weight(self):
        """A zero weight for one participant should raise ValueError."""
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": 2, "bob": 0})
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": 0, "bob": 1, "charlie": 1})

    def test_split_by_share_rejects_negative_individual_weight(self):
        """A negative weight for one participant should raise ValueError,
        even when the total weight is positive."""
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": 3, "bob": -1})
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": 10, "bob": -2})
        with self.assertRaises(ValueError):
            split_by_share(100, {"alice": -1, "bob": 2})

    def test_split_by_share_rejects_non_positive_mixed_weights(self):
        """Mixed positive/zero/negative weights are all rejected."""
        for shares in ({"alice": 1, "bob": 0, "charlie": 2},
                       {"alice": 5, "bob": -1, "charlie": 1}):
            with self.assertRaises(ValueError):
                split_by_share(100, shares)

    def test_split_by_share_positive_weights_still_work(self):
        """Positive weights, including fractional ones, still split exactly."""
        res = split_by_share(90, {"alice": 0.5, "bob": 0.25, "charlie": 0.25})
        self.assertEqual(set(res), {"alice", "bob", "charlie"})
        self.assertTrue(all(v > 0 for v in res.values()))
        self.assertEqual(total_in_paise(res), 9000)

    def test_who_owes_empty_group(self):
        """An empty group should return no debts."""
        self.assertEqual(who_owes({}), [])

    def test_balances_sum_to_zero(self):
        """Net balances in paise should always sum to exactly 0."""
        group_data = {
            "members": ["alice", "bob", "charlie"],
            "expenses": [
                {"paid_by": "alice", "amount": 10.00, "split": "equal"},
                {"paid_by": "bob", "amount": 3.33, "split": "equal"}
            ],
            "settlements": [
                {"from": "charlie", "to": "alice", "amount": 2.00}
            ]
        }
        balances = get_net_balances(group_data)
        self.assertEqual(sum(balances.values()), 0)


class TestSettleCommand(unittest.TestCase):

    def setUp(self):
        self.group_data = {
            "members": ["ravi", "priya"],
            "expenses": [
                {"paid_by": "priya", "amount": 400.00, "split": "equal"}
            ],
            "settlements": []
        }

    def test_settle_records_payment_in_debt_direction_and_clears_debt(self):
        group = copy.deepcopy(self.group_data)
        args = SimpleNamespace(group="groupA", payer="ravi", receiver="priya")

        with patch("split.cli.load_group", return_value=group), \
                patch("split.cli.save_group") as save_group, \
                redirect_stdout(io.StringIO()):
            cmd_settle(args)

        save_group.assert_called_once_with("groupA", group)
        self.assertEqual(
            group["settlements"],
            [{"from": "ravi", "to": "priya", "amount": 200.0}]
        )
        self.assertEqual(who_owes(group), [])

    def test_settle_rejects_reverse_direction(self):
        group = copy.deepcopy(self.group_data)
        args = SimpleNamespace(group="groupA", payer="priya", receiver="ravi")
        output = io.StringIO()

        with patch("split.cli.load_group", return_value=group), \
                patch("split.cli.save_group") as save_group, \
                redirect_stdout(output):
            cmd_settle(args)

        save_group.assert_not_called()
        self.assertEqual(group["settlements"], [])
        self.assertEqual(
            who_owes(group),
            [{"from": "ravi", "to": "priya", "amount": 200.0}]
        )
        self.assertIn("No pending debt found between priya and ravi.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
