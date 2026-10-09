"""Regression tests for Issue #15: add-expense accepts invalid monetary amounts.

The README says an amount must be greater than 0, but add-expense used to
convert the CLI argument straight to float without checking that it is a
positive finite number. Zero, negative numbers, nan and infinity were all
written into groups.json.

Every test here works against its own temporary groups.json file, so the
repository's real data/groups.json is never touched.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from split.cli import main
from split.io import load_group, save_group


class TestAddExpenseAmountValidation(unittest.TestCase):
    """add-expense must reject non-positive and non-finite amounts."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.data_path = Path(self._tmp_dir.name) / "groups.json"
        self.group_data = {
            "members": ["karan", "siddharth", "arjun"],
            "expenses": [],
            "settlements": [],
        }
        self._write_store()

    def _write_store(self):
        """(Re)creates the temporary store with only the test group."""
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump({"flatmates": self.group_data}, f, indent=2)

    def _read_store(self):
        with open(self.data_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _run_add_expense(self, amount):
        """Runs add-expense against the temporary store.

        `split.io` binds its default filepath at import time, so we patch the
        io functions' __defaults__ rather than the module attribute.

        Returns (handler_returned, stdout, stderr). `handler_returned` is
        False when argparse itself rejected the amount (SystemExit 2).
        """
        arguments = [
            "split", "add-expense", "flatmates", "Groceries", amount, "karan"
        ]
        output, error = io.StringIO(), io.StringIO()
        handler_returned = True
        defaults = (self.data_path,)
        with patch.object(sys, "argv", arguments), \
                patch.object(load_group, "__defaults__", defaults), \
                patch.object(save_group, "__defaults__", defaults), \
                redirect_stdout(output), redirect_stderr(error):
            try:
                main()
            except SystemExit as exc:
                if exc.code == 2:
                    handler_returned = False
                else:
                    raise
        return handler_returned, output.getvalue(), error.getvalue()

    def _stored_expenses(self):
        return self._read_store()["flatmates"]["expenses"]

    def _assert_rejected(self, amount):
        """The command must fail with a clear error and leave the store alone."""
        before = self._read_store()
        handler_returned, output, error = self._run_add_expense(amount)
        self.assertTrue(handler_returned,
                        f"amount {amount!r} should not be rejected by argparse")
        self.assertIn("Error:", output)
        self.assertEqual(self._read_store(), before,
                         f"rejected amount {amount!r} modified groups.json")
        self.assertEqual(self._stored_expenses(), [])

    def test_zero_amount_is_rejected(self):
        self._assert_rejected("0")

    def test_negative_amount_is_rejected(self):
        self._assert_rejected("-100")

    def test_nan_amount_is_rejected(self):
        self._assert_rejected("nan")

    def test_positive_infinity_is_rejected(self):
        self._assert_rejected("inf")

    def test_negative_infinity_is_rejected(self):
        # argparse reads '-inf' as an option flag, so it never reaches the
        # handler; the command still exits 2 without touching the store.
        before = self._read_store()
        handler_returned, _, error = self._run_add_expense("-inf")
        self.assertFalse(handler_returned)
        self.assertIn("invalid float value", error)
        self.assertEqual(self._read_store(), before)
        self.assertEqual(self._stored_expenses(), [])

    def test_non_numeric_amount_is_rejected(self):
        before = self._read_store()
        handler_returned, output, error = self._run_add_expense("abc")
        # argparse rejects unparseable floats with exit code 2 before any
        # handler runs, so the store must stay untouched either way.
        self.assertFalse(handler_returned)
        self.assertIn("invalid float value", error)
        self.assertEqual(self._read_store(), before)
        self.assertEqual(self._stored_expenses(), [])

    def test_positive_amount_is_accepted(self):
        handler_returned, output, error = self._run_add_expense("100")
        self.assertTrue(handler_returned)
        self.assertIn("Added expense 'Groceries' of ₹100.00", output)
        self.assertEqual(len(self._stored_expenses()), 1)
        self.assertEqual(self._stored_expenses()[0]["amount"], 100.0)

    def test_rejected_inputs_do_not_modify_groups_json(self):
        # One pass over every invalid input, checking the file byte-for-byte.
        initial_bytes = self.data_path.read_bytes()
        for amount in ("0", "-100", "nan", "inf", "-inf", "abc"):
            handler_returned, _, _ = self._run_add_expense(amount)
            if amount in ("-inf", "abc"):
                # argparse rejects these (exit 2) before the handler runs.
                self.assertFalse(handler_returned)
            else:
                self.assertTrue(handler_returned)
            self.assertEqual(self.data_path.read_bytes(), initial_bytes,
                             f"amount {amount!r} changed groups.json")


if __name__ == "__main__":
    unittest.main()
