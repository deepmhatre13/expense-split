"""Comprehensive Benchmark Suite for settle_plan performance and optimality."""

import time
from split.calc import settle_plan, get_net_balances

def make_group(balances_list, name_prefix="p"):
    members = [f"{name_prefix}_{i:02d}" for i in range(len(balances_list))]
    debtor_indices = [i for i, b in enumerate(balances_list) if b < 0]
    creditor_indices = [i for i, b in enumerate(balances_list) if b > 0]

    debt_shares = {members[d]: float(-balances_list[d]) for d in debtor_indices}
    expenses = []
    for c in creditor_indices:
        expenses.append({
            "paid_by": members[c],
            "amount": float(balances_list[c]),
            "split": "share",
            "shares": debt_shares,
        })
    return {"members": members, "expenses": expenses}

def run_benchmark_case(name, balances, approximate=False):
    group = make_group(balances)
    if approximate:
        group["approximate"] = True

    t0 = time.perf_counter()
    payments = settle_plan(group)
    elapsed = time.perf_counter() - t0

    # Verify correctness: all balances cleared exactly
    net = dict(get_net_balances(group))
    for p in payments:
        assert p["amount"] > 0, "Non-positive payment!"
        assert p["from"] != p["to"], "Self payment!"
        amt_paise = int(round(p["amount"] * 100))
        net[p["from"]] += amt_paise
        net[p["to"]] -= amt_paise
    assert all(b == 0 for b in net.values()), f"Balances not cleared for {name}!"

    mode = "Approx" if approximate else "Exact"
    print(f"{name:38} | N={len(balances):2} | Mode={mode:6} | Payments={len(payments):2} | Time={elapsed:8.4f}s")
    return elapsed, len(payments)

def main():
    print("=" * 75)
    print("SETTLE_PLAN PERFORMANCE & SCALABILITY BENCHMARKS")
    print("=" * 75)

    cases = [
        # Small / medium exact cases
        ("1. N=10 Multiple zero subsets (pairs)", [100, -100] * 5, False),
        ("2. N=10 Single zero subset (no interm)", [10, 20, 30, 40, 50, -15, -25, -35, -45, -30], False),
        ("3. N=12 Independent pairs", [50, -50] * 6, False),
        ("4. N=14 Repeated balance values", [10] * 7 + [-10] * 7, False),
        ("5. N=15 Independent triplets", [10, 20, -30] * 5, False),
        ("6. N=16 Independent triplets + single", [10, 20, -30] * 4 + [40, -40, 25, -25], False),
        ("7. N=18 Mixed zero-sum subsets", [10, -10] * 5 + [20, 30, -50] * 2 + [15, -15], False),
        ("8. N=20 Many repeated pairs", [25, -25] * 10, False),
        ("9. N=20 Mixed pairs + triplets", [10, -10] * 7 + [20, 30, -50] * 2, False),
        ("10. N=22 Realistic mixed group", [10, -10] * 8 + [15, 25, -40] + [30, -30] + [5, -5], False),
        ("11. N=25 Realistic mixed (mostly pairs)", [10, -10] * 10 + [15, 35, -50] + [5, -5], False),
        ("12. N=25 Approximation mode (explicit)", list(range(1, 13)) + [-sum(range(1, 13))], True),
    ]

    for name, bals, approx in cases:
        run_benchmark_case(name, bals, approximate=approx)

    print("=" * 75)

if __name__ == "__main__":
    main()

