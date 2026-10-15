"""Regression tests for Issue #10: Settlement can leave incorrect residual balances."""

import unittest
from split.calc import who_owes, get_net_balances


class TestPartialSettlements(unittest.TestCase):
    """Test cases for partial settlement scenarios from Issue #10."""
    
    def test_case1_partial_settlement(self):
        """Case 1: Alice owes Bob 500, Alice pays 200. Expected: Alice owes 300."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 200.0}]
        }
        result = who_owes(g)
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 300.0}])
        
        # Also verify get_net_balances
        balances = get_net_balances(g)
        self.assertEqual(balances, {'alice': -30000, 'bob': 30000})
    
    def test_case2_full_settlement(self):
        """Case 2: Alice owes Bob 500, Alice pays 500. Expected: No debt."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 500.0}]
        }
        result = who_owes(g)
        self.assertEqual(result, [])
        
        # Also verify get_net_balances
        balances = get_net_balances(g)
        self.assertEqual(balances, {'alice': 0, 'bob': 0})
    
    def test_case3_multiple_partial_settlements(self):
        """Case 3: Alice owes 500, pays 200 then 100. Expected: Alice owes 200."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [
                {'from': 'alice', 'to': 'bob', 'amount': 200.0},
                {'from': 'alice', 'to': 'bob', 'amount': 100.0}
            ]
        }
        result = who_owes(g)
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 200.0}])
        
        # Also verify get_net_balances
        balances = get_net_balances(g)
        self.assertEqual(balances, {'alice': -20000, 'bob': 20000})
    
    def test_case4_settlement_larger_than_debt(self):
        """Case 4: Settlement larger than debt creates reverse credit."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 400.0, 'split': 'equal'}],  # Alice owes 200
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 300.0}]  # Pays 300
        }
        result = who_owes(g)
        # Overpayment results in receiver owing the difference
        self.assertEqual(result, [{'from': 'bob', 'to': 'alice', 'amount': 100.0}])
    
    def test_case5_multiple_people_settlement_isolated(self):
        """Case 5: Settlement between two people doesn't affect other debts."""
        g = {
            'members': ['alice', 'bob', 'charlie'],
            'expenses': [
                {'paid_by': 'bob', 'amount': 900.0, 'split': 'equal'},
                {'paid_by': 'charlie', 'amount': 600.0, 'split': 'equal'},
            ],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 100.0}]
        }
        result = who_owes(g)
        
        # Alice owes Bob: 300 - 100 = 200 (reduced by settlement)
        alice_bob = next((d for d in result if d['from'] == 'alice' and d['to'] == 'bob'), None)
        self.assertIsNotNone(alice_bob)
        self.assertEqual(alice_bob['amount'], 200.0)
        
        # Alice owes Charlie: 200 (unchanged by Alice-Bob settlement)
        alice_charlie = next((d for d in result if d['from'] == 'alice' and d['to'] == 'charlie'), None)
        self.assertIsNotNone(alice_charlie)
        self.assertEqual(alice_charlie['amount'], 200.0)
    
    def test_negative_settlement_amount_rejected(self):
        """Negative settlement amounts should be ignored, not increase debt."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': -200.0}]
        }
        result = who_owes(g)
        # Negative amount should not increase the debt
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 500.0}])
    
    def test_zero_settlement_amount_no_change(self):
        """Zero settlement amount should not change anything."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 0.0}]
        }
        result = who_owes(g)
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 500.0}])
    
    def test_no_settlements(self):
        """Verify no settlements produces correct result."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': []
        }
        result = who_owes(g)
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 500.0}])
    
    def test_multiple_expenses(self):
        """Verify multiple expenses are handled correctly with settlement."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [
                {'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'},  # Alice owes 500
                {'paid_by': 'alice', 'amount': 400.0, 'split': 'equal'},  # Bob owes 200
            ],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 100.0}]
        }
        result = who_owes(g)
        # Net before settlement: Alice owes 500 - 200 = 300
        # After settlement: 300 - 100 = 200
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 200.0}])
    
    def test_get_net_balances_consistency(self):
        """Verify get_net_balances matches who_owes after partial settlement."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 200.0}]
        }
        
        debts = who_owes(g)
        balances = get_net_balances(g)
        
        # Alice should owe 300
        self.assertEqual(debts[0]['amount'], 300.0)
        self.assertEqual(balances['alice'], -30000)
        self.assertEqual(balances['bob'], 30000)
        
        # Sum should be 0
        self.assertEqual(sum(balances.values()), 0)


import copy
import io
import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from split.calc import settle_plan, to_paise
from split.cli import main, cmd_settle
from split.io import load_group, save_group


class TestPartialSettlementCLI(unittest.TestCase):
    """Regression tests for Issue #29: Support partial settlements with explicit payment amounts."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.data_path = Path(self._tmp_dir.name) / "groups.json"
        self.defaults = (self.data_path,)

    def _write_store(self, store_dict):
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(store_dict, f, indent=2)

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

    def test_partial_payment_reduces_outstanding_balance_correctly(self):
        # Bob paid 1000 for equal split with Alice -> Alice owes Bob 500
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Dinner", "paid_by": "bob", "amount": 1000.0, "split": "equal"}],
            "settlements": []
        }
        self._write_store({"flatmates": group})

        handler_returned, out, err = self._run_cli(["settle", "flatmates", "alice", "bob", "200"])
        self.assertTrue(handler_returned)
        self.assertIn("Settled! Alice paid ₹200.00 to Bob.", out)

        store = self._read_store()["flatmates"]
        self.assertEqual(len(store["settlements"]), 1)
        self.assertEqual(store["settlements"][0], {"from": "alice", "to": "bob", "amount": 200.0})

        debts = who_owes(store)
        self.assertEqual(debts, [{"from": "alice", "to": "bob", "amount": 300.0}])
        balances = get_net_balances(store)
        self.assertEqual(balances, {"alice": -30000, "bob": 30000})

    def test_multiple_partial_payments_accumulate_correctly(self):
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Rent", "paid_by": "bob", "amount": 2000.0, "split": "equal"}],  # Alice owes 1000
            "settlements": []
        }
        self._write_store({"flatmates": group})

        # Payment 1: 300
        self._run_cli(["settle", "flatmates", "alice", "bob", "300"])
        store = self._read_store()["flatmates"]
        self.assertEqual(who_owes(store), [{"from": "alice", "to": "bob", "amount": 700.0}])
        self.assertEqual(get_net_balances(store), {"alice": -70000, "bob": 70000})

        # Payment 2: 200
        self._run_cli(["settle", "flatmates", "alice", "bob", "200"])
        store = self._read_store()["flatmates"]
        self.assertEqual(who_owes(store), [{"from": "alice", "to": "bob", "amount": 500.0}])
        self.assertEqual(get_net_balances(store), {"alice": -50000, "bob": 50000})

        # Payment 3: final 500 clears obligation
        self._run_cli(["settle", "flatmates", "alice", "bob", "500"])
        store = self._read_store()["flatmates"]
        self.assertEqual(who_owes(store), [])
        self.assertEqual(get_net_balances(store), {"alice": 0, "bob": 0})
        self.assertEqual(settle_plan(store), [])

        self.assertEqual(len(store["settlements"]), 3)
        self.assertEqual(store["settlements"][0]["amount"], 300.0)
        self.assertEqual(store["settlements"][1]["amount"], 200.0)
        self.assertEqual(store["settlements"][2]["amount"], 500.0)

    def test_full_settlement_when_amount_omitted(self):
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Dinner", "paid_by": "bob", "amount": 1000.0, "split": "equal"}],
            "settlements": []
        }
        self._write_store({"flatmates": group})

        handler_returned, out, err = self._run_cli(["settle", "flatmates", "alice", "bob"])
        self.assertTrue(handler_returned)
        self.assertIn("Settled! Alice paid ₹500.00 to Bob.", out)

        store = self._read_store()["flatmates"]
        self.assertEqual(store["settlements"], [{"from": "alice", "to": "bob", "amount": 500.0}])
        self.assertEqual(who_owes(store), [])
        self.assertEqual(get_net_balances(store), {"alice": 0, "bob": 0})

    def test_invalid_amounts_rejected_without_modifying_store(self):
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Dinner", "paid_by": "bob", "amount": 1000.0, "split": "equal"}],  # owes 500
            "settlements": []
        }
        self._write_store({"flatmates": group})
        original_bytes = self.data_path.read_bytes()

        invalid_inputs = ["0", "-100", "nan", "inf", "-inf", "abc", "100.50.25"]
        for val in invalid_inputs:
            with self.subTest(val=val):
                handler_returned, out, err = self._run_cli(["settle", "flatmates", "alice", "bob", val])
                if not handler_returned:
                    self.assertIn("unrecognized arguments", err)
                else:
                    self.assertIn("Error:", out)
                self.assertEqual(self.data_path.read_bytes(), original_bytes)

    def test_overpayment_rejected_without_modifying_store(self):
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Dinner", "paid_by": "bob", "amount": 1000.0, "split": "equal"}],  # owes 500
            "settlements": []
        }
        self._write_store({"flatmates": group})
        original_bytes = self.data_path.read_bytes()

        handler_returned, out, err = self._run_cli(["settle", "flatmates", "alice", "bob", "500.01"])
        self.assertTrue(handler_returned)
        self.assertIn("Error:", out)
        self.assertIn("exceeds outstanding obligation", out)
        self.assertEqual(self.data_path.read_bytes(), original_bytes)

    def test_fractional_rupee_follows_monetary_rounding_policy(self):
        # Bob pays 10.00, Alice owes 5.00. Alice pays 2.675 (which rounds HALF_UP to 268 paise = 2.68 rupees)
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Groceries", "paid_by": "bob", "amount": 10.00, "split": "equal"}],
            "settlements": []
        }
        self._write_store({"flatmates": group})

        handler_returned, out, _ = self._run_cli(["settle", "flatmates", "alice", "bob", "2.675"])
        self.assertTrue(handler_returned)
        self.assertIn("Settled! Alice paid ₹2.68 to Bob.", out)

        store = self._read_store()["flatmates"]
        self.assertEqual(store["settlements"], [{"from": "alice", "to": "bob", "amount": 2.68}])
        balances = get_net_balances(store)
        # Alice started at -500 paise, paid 268 paise -> now -232 paise
        self.assertEqual(balances["alice"], -232)
        self.assertEqual(balances["bob"], 232)
        self.assertEqual(who_owes(store), [{"from": "alice", "to": "bob", "amount": 2.32}])

    def test_multiple_participants_and_netted_balances_remain_correct(self):
        # 3 participants: Charlie owes Alice 30 via plan, and Bob owes Alice 30 / Charlie owes Bob 30 direct
        group = {
            "members": ["alice", "bob", "charlie"],
            "expenses": [
                {
                    "description": "Lunch",
                    "paid_by": "alice",
                    "amount": 60.0,
                    "split": "share",
                    "shares": {"alice": 1, "bob": 1},
                },
                {
                    "description": "Dinner",
                    "paid_by": "bob",
                    "amount": 60.0,
                    "split": "share",
                    "shares": {"bob": 1, "charlie": 1},
                },
            ],
            "settlements": [],
        }
        self._write_store({"chain": group})

        # Planned payment: charlie -> alice: 30.0
        # Charlie makes partial payment of 10.0 to Alice
        handler_returned, out, _ = self._run_cli(["settle", "chain", "charlie", "alice", "10"])
        self.assertTrue(handler_returned)
        self.assertIn("Settled! Charlie paid ₹10.00 to Alice.", out)

        store = self._read_store()["chain"]
        balances = get_net_balances(store)
        self.assertEqual(balances, {"alice": 2000, "bob": 0, "charlie": -2000})
        self.assertEqual(sum(balances.values()), 0)

        plan = settle_plan(store)
        self.assertEqual(plan, [{"from": "charlie", "to": "alice", "amount": 20.0}])

        # Summary output check: debts in who_owes reflect reduced obligations
        handler_returned, summary_out, _ = self._run_cli(["summary", "chain"])
        self.assertTrue(handler_returned)
        self.assertIn("Bob owes Alice ₹20.00", summary_out)
        self.assertIn("Charlie owes Bob ₹20.00", summary_out)

    def test_settlement_direction_validation_intact(self):
        group = {
            "members": ["bob", "alice"],
            "expenses": [{"description": "Dinner", "paid_by": "bob", "amount": 1000.0, "split": "equal"}],  # Alice owes Bob 500
            "settlements": []
        }
        self._write_store({"flatmates": group})
        original_bytes = self.data_path.read_bytes()

        # Bob tries to pay Alice 200 (reverse direction)
        handler_returned, out, _ = self._run_cli(["settle", "flatmates", "bob", "alice", "200"])
        self.assertTrue(handler_returned)
        self.assertIn("No pending debt found between bob and alice.", out)
        self.assertEqual(self.data_path.read_bytes(), original_bytes)


if __name__ == '__main__':
    unittest.main()
