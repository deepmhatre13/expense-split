# expense-split

Split shared costs in a group, like a flat, a trip or a hackathon team, and see who owes whom. A command-line tool in plain Python with no dependencies. Groups are saved in `data/groups.json`.

## Running it

You need Python 3.8 or newer.

```
python3 -m split summary groupA
python3 -m split add-expense groupA "Pizza" 1200 priya
python3 -m split settle groupA ravi priya
python3 -m unittest discover tests
```

On Windows, use `python` instead of `python3`.

## Commands

| Command | Does |
|---|---|
| `summary <group>` | Members, expenses, and who owes whom |
| `add-expense <group> <description> <amount> <paid_by> [equal\|share]` | Records an expense. Split equally unless you say otherwise |
| `edit-expense <group> <expense_id> <description> <amount> <paid_by> [equal\|share]` | Updates an existing expense by its stable ID |
| `delete-expense <group> <expense_id>` | Deletes an expense by its stable ID |
| `settle <group> <payer> <receiver>` | Records that `payer` paid back what they owe `receiver` |

## How it's supposed to work

- Every expense is assigned a unique, stable ID within its group. Editing an expense preserves its ID, and deleting an expense leaves all other expense IDs unchanged (no renumbering).
- Legacy expenses without an explicit ID can be referenced by their 1-based order in the group.
- Editing or deleting an expense preserves the exact historical record of all settlements; balances and settlement plans are recalculated from remaining expenses and existing payments.
- An amount must be more than 0, and whoever paid must be a member of the group.
- An equal split keeps the paise, and the shares always add up to exactly the total. ₹1000 between three people is ₹333.34, ₹333.33 and ₹333.33.
- `share` splits by weights, given after it as `name=weight`: `add-expense flatmates "Groceries" 900 karan share karan=2 arjun=1` means Karan's share is twice Arjun's.
- The summary shows each pair of people at most once, with the amount after everything is netted out. If Ravi owes Priya ₹300 and Priya owes Ravi ₹100, it shows "Ravi owes Priya ₹200.00".
- Nobody is ever shown owing themselves.
- After `settle ravi priya`, Ravi no longer owes Priya anything, and the summary shows that.

## Code

- `split/calc.py`: splitting and working out debts
- `split/io.py`: reading and writing `data/groups.json`
- `split/cli.py`: the commands
- `tests/`: tests, run with `python3 -m unittest discover tests`

## Contributing

Fork the repo, make your changes on a new branch, and open a pull request. Run the tests first.

If you find a bug, open an issue with the steps to reproduce it, what you expected, and what happened instead.

Part of Source Start by CSI SPIT. MIT licensed.
