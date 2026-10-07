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


if __name__ == '__main__':
    unittest.main()
