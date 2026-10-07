"""Test to reproduce Issue #10: Settlement can leave incorrect residual balances."""

import unittest
from split.calc import who_owes, get_net_balances


class TestSettlementValidation(unittest.TestCase):
    """Tests for settlement amount validation in who_owes."""
    
    def test_partial_settlement_correct_direction(self):
        """Case 1: Partial settlement with correct direction should work."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 200.0}]
        }
        result = who_owes(g)
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 300.0}])
    
    def test_settlement_negative_amount(self):
        """BUG: Negative settlement amount should be rejected, not increase debt."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': -200.0}]
        }
        result = who_owes(g)
        # Current behavior: Alice owes 700 (WRONG - negative amount increased debt)
        # Expected: Should be rejected or result in 500 (no change)
        # This test FAILS before fix, showing the bug
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 500.0}],
                         "Negative settlement amount should not change the debt")
    
    def test_settlement_zero_amount(self):
        """Zero settlement amount should not change anything."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 1000.0, 'split': 'equal'}],
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 0.0}]
        }
        result = who_owes(g)
        self.assertEqual(result, [{'from': 'alice', 'to': 'bob', 'amount': 500.0}])
    
    def test_settlement_larger_than_debt(self):
        """Settlement larger than debt creates reverse debt (documented behavior)."""
        g = {
            'members': ['alice', 'bob'],
            'expenses': [{'paid_by': 'bob', 'amount': 400.0, 'split': 'equal'}],  # Alice owes 200
            'settlements': [{'from': 'alice', 'to': 'bob', 'amount': 500.0}]  # Pays 500
        }
        result = who_owes(g)
        # Current behavior: Shows bob owes alice 300 (overpayment creates credit)
        # This is arguably correct - if you overpay, you're owed the difference
        self.assertEqual(result, [{'from': 'bob', 'to': 'alice', 'amount': 300.0}])


if __name__ == '__main__':
    unittest.main()
