
"""Expense splitting and debt calculation logic."""

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

# The smallest monetary unit used when converting amounts to whole paise.
_SCALE = Decimal("0.01")


def to_paise(amount):
    """Convert a rupee amount to integer paise using ROUND_HALF_UP.

    Supported types: int, float, str, and Decimal.
    Raises TypeError for unsupported types and ValueError for invalid or
    non-finite amounts.
    """
    if (
        amount is None
        or isinstance(amount, bool)
        or not isinstance(amount, (int, float, str, Decimal))
    ):
        raise TypeError(
            f"Unsupported type for monetary amount: {type(amount).__name__}"
        )

    if isinstance(amount, Decimal):
        decimal_amount = amount
    elif isinstance(amount, str):
        try:
            decimal_amount = Decimal(amount.strip())
        except Exception as exc:
            raise ValueError(
                f"Invalid monetary amount: {amount!r}"
            ) from exc
    else:
        try:
            decimal_amount = Decimal(str(amount))
        except Exception as exc:
            raise ValueError(
                f"Invalid monetary amount: {amount!r}"
            ) from exc

    if not decimal_amount.is_finite():
        raise ValueError(
            f"Monetary amount must be finite, got {amount!r}"
        )

    paise = (
        decimal_amount * Decimal("100")
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return int(paise)


def split_equally(amount, num_people):
    """Split a total amount equally among a given number of people."""
    if num_people <= 0:
        raise ValueError("Number of people must be greater than 0")

    each = int(amount) // num_people
    return {"each": each}


def _split_by_share_paise(amount, shares):
    """Allocate an amount proportionally and return integer paise per person.

    Any leftover paise are distributed by largest fractional remainder.
    Ties are resolved by the original order of participants.
    """
    for person, weight in shares.items():
        if weight <= 0:
            raise ValueError(
                f"Weight for {person} must be greater than 0, got {weight}"
            )

    total_shares = sum(shares.values())
    if total_shares <= 0:
        raise ValueError("Total shares must be greater than 0")

    amount_paise = to_paise(amount)

    allocations = {}
    remainders = []
    unallocated = amount_paise

    for person, weight in shares.items():
        exact = (
            Decimal(amount_paise)
            * Decimal(str(weight))
            / Decimal(str(total_shares))
        )
        base = int(exact.to_integral_value(rounding=ROUND_FLOOR))

        allocations[person] = base
        unallocated -= base
        remainders.append((exact - base, person))

    remainders.sort(key=lambda item: -item[0])

    for i in range(unallocated):
        person = remainders[i % len(remainders)][1]
        allocations[person] += 1

    return allocations


def split_by_share(amount, shares):
    """Split an amount proportionally while preserving its exact total.

    Returns the existing public interface of participant amounts in rupees.
    Internally, allocations are calculated in integer paise.
    """
    allocations = _split_by_share_paise(amount, shares)

    return {
        person: float(Decimal(allocations[person]) * _SCALE)
        for person in shares
    }


def _expense_shares_paise(expense, members):
    """Return each member's expense share in integer paise."""
    amount = expense.get("amount", 0.0)
    amount_paise = to_paise(amount)

    if expense.get("split") == "share":
        allocated = _split_by_share_paise(
            amount, expense.get("shares", {})
        )
        return {
            member: allocated.get(member, 0)
            for member in members
        }

    if not members:
        return {}

    base_share = amount_paise // len(members)
    remainder = amount_paise % len(members)

    return {
        member: base_share + (1 if index < remainder else 0)
        for index, member in enumerate(members)
    }


def get_net_balances(group_data):
    """Calculate net balances in integer paise.

    Positive means the person is owed money; negative means they owe money.
    """
    members = group_data.get("members", [])
    if not members:
        return {}

    balances = {member: 0 for member in members}

    for expense in group_data.get("expenses", []):
        paid_by = expense.get("paid_by")
        amount_paise = to_paise(expense.get("amount", 0.0))

        balances[paid_by] += amount_paise

        for member, share in _expense_shares_paise(
            expense, members
        ).items():
            balances[member] -= share

    for settlement in group_data.get("settlements", []):
        payer = settlement["from"]
        receiver = settlement["to"]
        amount_paise = to_paise(settlement["amount"])

        # Ignore zero or negative settlement amounts.
        if amount_paise <= 0:
            continue

        balances[payer] += amount_paise
        balances[receiver] -= amount_paise

    return balances


def who_owes(group_data):
    """Calculate netted pairwise debts between group members."""
    members = group_data.get("members", [])
    if not members:
        return []

    owes = {
        member: {other: 0 for other in members}
        for member in members
    }

    for expense in group_data.get("expenses", []):
        paid_by = expense.get("paid_by")

        for member, share in _expense_shares_paise(
            expense, members
        ).items():
            if member == paid_by:
                continue

            owes[member][paid_by] += share

    for settlement in group_data.get("settlements", []):
        payer = settlement["from"]
        receiver = settlement["to"]
        amount_paise = to_paise(settlement["amount"])

        if amount_paise <= 0:
            continue

        owes[payer][receiver] -= amount_paise

    debts = []

    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            member1 = members[i]
            member2 = members[j]
            net = owes[member1][member2] - owes[member2][member1]

            if net > 0:
                debts.append({
                    "from": member1,
                    "to": member2,
                    "amount": net / 100.0,
                })
            elif net < 0:
                debts.append({
                    "from": member2,
                    "to": member1,
                    "amount": -net / 100.0,
                })

    return debts


def settle_plan(group_data):
    """Return a minimum-payment plan that clears all net balances."""
    balances = get_net_balances(group_data)

    non_zero = [
        (person, balance)
        for person, balance in balances.items()
        if balance != 0
    ]

    if not non_zero:
        return []

    def solve_subset(members_with_balances):
        """Settle one zero-sum subset using deterministic debt matching."""
        debtors = [
            [person, -balance]
            for person, balance in members_with_balances
            if balance < 0
        ]
        creditors = [
            [person, balance]
            for person, balance in members_with_balances
            if balance > 0
        ]

        debtors.sort(key=lambda item: (-item[1], item[0]))
        creditors.sort(key=lambda item: (-item[1], item[0]))

        payments = []
        i = 0
        j = 0

        while i < len(debtors) and j < len(creditors):
            debtor, debt_amount = debtors[i]
            creditor, credit_amount = creditors[j]

            payment = min(debt_amount, credit_amount)

            if payment > 0:
                payments.append({
                    "from": debtor,
                    "to": creditor,
                    "amount": payment / 100.0,
                })

            debtors[i][1] -= payment
            creditors[j][1] -= payment

            if debtors[i][1] == 0:
                i += 1
            if creditors[j][1] == 0:
                j += 1

        return payments

    n = len(non_zero)
    memo = {}

    def get_max_subsets(mask):
        """Find the maximum number of zero-sum participant subsets."""
        if mask == 0:
            return 0, []

        if mask in memo:
            return memo[mask]

        lowest_bit = mask & -mask
        submask = (mask - 1) & mask

        best_count = -1
        best_subsets = []
        current = submask

        while True:
            candidate_mask = current | lowest_bit

            subset_sum = sum(
                non_zero[index][1]
                for index in range(n)
                if candidate_mask & (1 << index)
            )

            if subset_sum == 0:
                remaining_count, remaining_subsets = get_max_subsets(
                    mask ^ candidate_mask
                )

                if 1 + remaining_count > best_count:
                    best_count = 1 + remaining_count
                    best_subsets = (
                        [candidate_mask] + remaining_subsets
                    )

            if current == 0:
                break

            current = (current - 1) & submask

        memo[mask] = (best_count, best_subsets)
        return memo[mask]

    full_mask = (1 << n) - 1
    _, optimal_subsets = get_max_subsets(full_mask)

    payments = []

    for subset_mask in optimal_subsets:
        subset_members = [
            non_zero[index]
            for index in range(n)
            if subset_mask & (1 << index)
        ]
        payments.extend(solve_subset(subset_members))

    payments.sort(key=lambda payment: (
        payment["from"],
        payment["to"],
    ))

    return payments
