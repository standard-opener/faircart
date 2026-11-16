# FairCart

**Group checkout planning with personal budgets and protected solo prices.**

FairCart finds the cheapest way for a small group to place orders at one store,
then allocates the total without exceeding anyone's budget or modeled solo price.
It compares separate purchases, one combined order, and every allowed grouping.
An extra-item comparison checks whether a free-shipping top-up actually reduces
cash outlay.

Python 3.10+ · No third-party runtime dependencies · MIT license

## Motivation

A cheaper group bill can still be unfair to one buyer. Suppose Amy wants HKD 12
of stationery, while Ben and Cara want HKD 48 and HKD 60 of goods. Sharing the
checkout equally could make Amy pay more than her entire solo purchase.

FairCart answers two connected questions: which orders should the group place,
and how much can each person contribute without exceeding an agreed limit?

## Quick start

From the project directory:

```bash
python -m pip install .
python examples/demo.py
```

The distribution is `faircart-share`. The import name and terminal command are
both `faircart`.

```bash
faircart plan examples/shared.json
faircart plan examples/shared.json --format json
faircart demo --output my-calculator.html
```

Open `my-calculator.html` in a browser. It is a self-contained calculator with
editable buyers, basket amounts, budgets, shipping terms, and coupons. It works
offline. Python and browser engines implement the same pricing and allocation
rules. The browser engine uses exact integer cents and BigInt for allocation.

Existing output files are not overwritten. Use a new output name for each run.
The same commands work as `python -m faircart ...` after installation.

## Worked example

Shipping costs HKD 12 per order. A merchandise subtotal of HKD 100 qualifies for
free shipping and a public HKD 12 discount. These are supplied example terms.

| Buyer | Basket | Best solo order | Budget | Equal share of group bill | FairCart payment | Saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Amy | 12.00 | 24.00 | 20.00 | 36.00 | 16.61 | 7.39 |
| Ben | 48.00 | 60.00 | 60.00 | 36.00 | 41.54 | 18.46 |
| Cara | 60.00 | 72.00 | 72.00 | 36.00 | 49.85 | 22.15 |
| Total | 120.00 | 156.00 | | 108.00 | 108.00 | 48.00 |

An equal split exceeds Amy's budget and solo price. FairCart protects her payment
limit while keeping the payments equal to the checkout total, to the cent.

If Amy's budget falls to HKD 10, the payments become **10.00, 44.55, and 53.45**.
If the three budgets are 10.00, 30.00, and 40.00, the cheapest checkout still costs
108.00 while the payment caps cover only 80.00. FairCart reports a **28.00 shortfall**.

## Python API

```python
from faircart import load_cart, optimize, compare_topup

cart = load_cart("examples/shared.json")
plan = optimize(cart)
print(plan.to_text())
print(plan.to_dict())

assert plan.feasible
assert sum(plan.payments) == plan.total  # integer cents
assert all(p <= cap for p, cap in zip(plan.payments, plan.caps))

trap = load_cart("examples/topup.json")
print(compare_topup(trap, owner="amy", price="15.00"))
# Before: 70.00; after: 73.00; cash change: +3.00.
```

`optimize` also accepts a cart dictionary. Use decimal strings, integer amounts,
or `Decimal` for money in Python. Binary floating-point amounts are rejected.
`Plan.total`, `baselines`, `caps`, `payments`, and all `Order` amounts use integer
cents. `Plan.to_dict()` formats monetary values as two-decimal strings.

`payments` is `None` when no allocation meets every cap. The cheapest ordering
plan remains available to explain the shortfall. Do not treat an infeasible plan
as a payment instruction.

## Input format

```json
{
  "title": "Group purchase",
  "currency": "HKD",
  "people": [
    {"id": "amy", "name": "Amy", "budget": "30.00"},
    {"id": "ben", "name": "Ben", "budget": "50.00"}
  ],
  "items": [
    {"id": "pens", "owner": "amy", "name": "Pens", "unit_price": "12.00", "quantity": 1},
    {"id": "food", "owner": "ben", "name": "Groceries", "unit_price": "35.00", "quantity": 1}
  ],
  "store": {"shipping_fee": "12.00", "free_shipping_at": "50.00"},
  "coupons": [
    {"id": "SAVE5", "kind": "fixed", "min_subtotal": "50.00", "amount": "5.00", "owner": null}
  ]
}
```

- Each person owns at least one item line. IDs are unique within each list.
- A person's complete basket stays in one order. Different people may share it.
- At most one coupon applies to each order. Discounts reduce merchandise only.
- A coupon with `owner: null` is public and repeatable across orders.
- A personal coupon has an owner ID and requires that person's basket in the
  order. The whole-basket rule prevents using it in two orders.
- A percent coupon uses `kind: "percent"`, `percent_off: "10.00"`, and an optional
  `max_discount`. A value of 10 means 10% off. Percentage discounts round down
  to the nearest cent before any cap applies.
- Shipping and coupon thresholds use the merchandise subtotal **before discounts**.
  Set `free_shipping_at` to `null` or omit it for a store without free shipping.

Unknown fields, unknown owners, invalid quantities, negative money, nonfinite
values, and fractional cents fail explicitly.

## Payment policy

For buyer `i`, the protected solo price `b_i` is the cheapest **single order** for
that buyer's whole basket, using their own coupons and public repeatable coupons.
The payment cap is `min(b_i, budget_i)`.

FairCart minimizes checkout cost first. It then allocates contributions
proportionally to solo prices, fixes any contribution that hits a cap, and
redistributes the remaining cost across uncapped buyers. Exact fractions avoid
rounding drift. Largest fractional remainders receive the final cents, with buyer
ID as the deterministic tie-break.

All orders settle through one shared pool. Buyers accept this contribution rule
before purchasing. It guarantees budget compliance and no increase over each
modeled solo price. It does not claim that this policy is the only definition of
fairness or that every subgroup would prefer the resulting allocation.

## Further use cases

| File | Demonstration |
| --- | --- |
| `examples/shared.json` | Equal sharing would overcharge a small buyer |
| `examples/capped.json` | A lower personal budget requires a different allocation |
| `examples/split.json` | Two personal coupons make two orders cheaper than one |
| `examples/impossible.json` | Payment caps cannot fund the cheapest checkout |
| `examples/topup.json` | Adding an item removes shipping but increases total spending |

```bash
faircart plan examples/split.json
faircart plan examples/impossible.json --format json
faircart topup examples/topup.json --owner amy --price 15.00 --name "Extra snack"
faircart plan examples/shared.json --format html --output checkout.html
```

CLI exit codes: `0` for a successful feasible plan or completed comparison,
`1` for an infeasible payment plan, and `2` for invalid input or file errors.
The `demo` command returns `0` when it writes the calculator, including its
infeasible example. `topup` reports budget feasibility in its JSON output.

## Distinctive contribution

FairCart combines checkout grouping with individual payment protection and a
checkable explanation when budgets cannot cover the cheapest checkout. It also
compares cash spending before and after a top-up. These features connect the
purchase decision to the later division of costs.

[sharepay](https://pypi.org/project/sharepay/) documents splitting recorded expenses
and settling balances. [WaSHI's coupon example](https://ohtaman.github.io/washi/examples/ecommerce-coupons)
demonstrates checkout optimization. FairCart's application combines grouping,
protected solo prices, budget caps, and exact-cent settlement in a small Python
API. The underlying optimization and allocation methods build on established
ideas. The worked example and automated tests demonstrate the payment policy
and compare the optimizer against independent exhaustive search.

## Tests

```bash
python -m unittest discover -s tests -v
```

The suite contains 28 tests. It includes an independent exhaustive partition
oracle for 80 generated carts, 500 allocation invariant cases, and parity checks
between Python and browser calculations on 205 carts and their top-up comparisons.
The parity test uses Node.js when available. Set `FAIRCART_NODE` to an executable
path if Node is not on `PATH`. The other tests require only Python's standard
library.

## Scope

The exact optimizer supports one store, 1–8 buyers, up to 100 item lines and 16
coupons. Every buyer's basket stays intact. It excludes tax, mixed currencies,
multiple delivery addresses, coupon stacking, and account-specific store rules
beyond the supplied coupon ownership. Public coupons must actually be reusable
under the store's terms. Real prices and terms are entered by the user.

The model supports currencies represented by two decimal places. Combined
merchandise is limited to 10,000,000.00 units. Individual monetary inputs cannot
exceed 1,000,000,000.00. The browser interface edits each person's basket subtotal,
while the Python API also accepts separate item lines and quantities.

The package calculates plans and never places an order or transfers money.

## Building distributions

Build distributions using `python -m pip install build` followed by
`python -m build`. The packaging structure follows the
[Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).
