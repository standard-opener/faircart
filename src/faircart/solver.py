from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Any

from .model import Cart, FairCartError, Item, money, to_cents


@dataclass(frozen=True)
class Order:
    members: tuple[str, ...]
    subtotal: int
    discount: int
    shipping: int
    coupon: str | None

    @property
    def total(self) -> int:
        return self.subtotal - self.discount + self.shipping

    def to_dict(self) -> dict:
        return {"members": list(self.members), "subtotal": money(self.subtotal),
                "discount": money(self.discount), "shipping": money(self.shipping),
                "coupon": self.coupon, "total": money(self.total)}


def quote_order(cart: Cart, members: tuple[str, ...] | list[str]) -> Order:
    """Choose at most one eligible coupon for a whole-person basket."""
    members = tuple(members)
    if not members or len(set(members)) != len(members) or not set(members) <= {p.id for p in cart.people}:
        raise FairCartError("Order members must be distinct, known person IDs.")
    subtotal = sum(i.subtotal for i in cart.items if i.owner in members)
    shipping = 0 if cart.free_shipping_at is not None and subtotal >= cart.free_shipping_at else cart.shipping_fee
    candidates = [Order(members, subtotal, 0, shipping, None)]
    for coupon in cart.coupons:
        if subtotal < coupon.min_subtotal or coupon.owner is not None and coupon.owner not in members:
            continue
        discount = coupon.amount if coupon.kind == "fixed" else subtotal * coupon.rate_bps // 10000
        if coupon.max_discount is not None:
            discount = min(discount, coupon.max_discount)
        candidates.append(Order(members, subtotal, min(subtotal, discount), shipping, coupon.id))
    return min(candidates, key=lambda o: (o.total, o.coupon or ""))


def allocate_payments(total: int, baselines: list[int], budgets: list[int], ids: list[str] | None = None) -> list[int] | None:
    """Capped proportional allocation in integer cents with exact fractions.

    The unconstrained target has the same payment / solo-cost ratio for everyone.
    Budget and solo-price caps take priority. Largest fractional remainders receive
    the remaining cents, with person ID as the deterministic tie-break.
    """
    if (isinstance(total, bool) or not isinstance(total, int) or total < 0 or
            len(baselines) != len(budgets) or not baselines or
            any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in baselines + budgets)):
        raise FairCartError("Allocation needs nonnegative integer cents and matching nonempty lists.")
    ids = ids if ids is not None else [str(i) for i in range(len(baselines))]
    if len(ids) != len(baselines) or not all(isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
        raise FairCartError("Allocation IDs must be unique strings matching the amount lists.")
    caps = [min(b, cap) for b, cap in zip(baselines, budgets)]
    if total > sum(caps):
        return None
    raw = [Fraction(0) for _ in caps]
    active = {i for i, b in enumerate(baselines) if b > 0 and caps[i] > 0}
    remaining = total
    while active:
        weight = sum(baselines[i] for i in active)
        level = Fraction(remaining, weight)
        fixed = {i for i in active if level * baselines[i] >= caps[i]}
        if not fixed:
            for i in active:
                raw[i] = level * baselines[i]
            break
        for i in fixed:
            raw[i] = Fraction(caps[i])
            remaining -= caps[i]
        active -= fixed
    payments = [int(value) for value in raw]
    remainder = total - sum(payments)
    rank = sorted(range(len(raw)), key=lambda i: (-(raw[i] - payments[i]), ids[i]))
    for i in rank[:remainder]:
        payments[i] += 1
    assert sum(payments) == total and all(0 <= p <= c for p, c in zip(payments, caps))
    return payments


@dataclass(frozen=True)
class Plan:
    cart: Cart
    orders: tuple[Order, ...]
    baselines: tuple[int, ...]
    payments: tuple[int, ...] | None
    equal_payments: tuple[int, ...]
    all_in_one: Order
    subset_quotes: int

    @property
    def total(self) -> int:
        return sum(o.total for o in self.orders)

    @property
    def feasible(self) -> bool:
        return self.payments is not None

    @property
    def caps(self) -> tuple[int, ...]:
        return tuple(min(b, p.budget) for b, p in zip(self.baselines, self.cart.people))

    @property
    def shortfall(self) -> int:
        return max(0, self.total - sum(self.caps))

    def to_dict(self) -> dict[str, Any]:
        people = []
        for i, p in enumerate(self.cart.people):
            payment = None if self.payments is None else self.payments[i]
            people.append({"id": p.id, "name": p.name, "basket": money(sum(x.subtotal for x in self.cart.items if x.owner == p.id)),
                           "solo_cost": money(self.baselines[i]), "budget": money(p.budget),
                           "payment_cap": money(self.caps[i]), "payment": None if payment is None else money(payment),
                           "saving": None if payment is None else money(self.baselines[i] - payment),
                           "equal_split": money(self.equal_payments[i]),
                           "equal_split_breaks_cap": self.equal_payments[i] > self.caps[i]})
        return {"title": self.cart.title, "currency": self.cart.currency,
                "status": "feasible" if self.feasible else "infeasible",
                "solo_total": money(sum(self.baselines)), "optimal_total": money(self.total),
                "potential_saving": money(sum(self.baselines) - self.total),
                "all_in_one_total": money(self.all_in_one.total), "available_payment": money(sum(self.caps)),
                "shortfall": money(self.shortfall), "order_count": len(self.orders),
                "orders": [o.to_dict() for o in self.orders], "people": people,
                "checks": {"budgets_met": self.feasible, "no_one_worse_off": self.feasible,
                           "payments_match_total": self.feasible and sum(self.payments) == self.total},
                "search": {"method": "exact subset dynamic programming", "subset_quotes": self.subset_quotes},
                "policy": "Capped proportional payments based on best solo prices, settled across the whole group."}

    def to_text(self) -> str:
        result = self.to_dict()
        currency = self.cart.currency
        lines = [f"FairCart: {self.cart.title}", f"Status: {result['status']}",
                 f"Separate purchases: {currency} {result['solo_total']}",
                 f"Cheapest checkout: {currency} {result['optimal_total']} in {len(self.orders)} order(s)",
                 f"Potential saving: {currency} {result['potential_saving']}"]
        if not self.feasible:
            lines += [f"Payment caps cover {currency} {result['available_payment']}.",
                      f"Shortfall: {currency} {result['shortfall']}. No payment plan satisfies every cap."]
        else:
            for person in result["people"]:
                lines.append(f"{person['name']}: pay {currency} {person['payment']}; "
                             f"solo {person['solo_cost']}; save {person['saving']}; budget {person['budget']}")
        for i, order in enumerate(self.orders, 1):
            lines.append(f"Order {i}: {', '.join(order.members)}; coupon {order.coupon or 'none'}; total {currency} {money(order.total)}")
        return "\n".join(lines)


def optimize(cart: Cart | dict) -> Plan:
    if isinstance(cart, dict):
        cart = Cart.from_dict(cart)
    if not isinstance(cart, Cart):
        raise FairCartError("Expected a Cart or cart dictionary.")
    count = len(cart.people)
    full = (1 << count) - 1
    quotes = {mask: quote_order(cart, [p.id for i, p in enumerate(cart.people) if mask & (1 << i)])
              for mask in range(1, full + 1)}

    @lru_cache(None)
    def best(mask: int) -> tuple[int, tuple[int, ...]]:
        if not mask:
            return 0, ()
        first = mask & -mask
        sub = mask
        choice = None
        while sub:
            if sub & first:
                rest_cost, rest_groups = best(mask ^ sub)
                candidate = (quotes[sub].total + rest_cost, tuple(sorted((sub,) + rest_groups)))
                if choice is None or (candidate[0], len(candidate[1]), candidate[1]) < (choice[0], len(choice[1]), choice[1]):
                    choice = candidate
            sub = (sub - 1) & mask
        return choice

    total, groups = best(full)
    baseline = tuple(quotes[1 << i].total for i in range(count))
    allocation = allocate_payments(total, list(baseline), [p.budget for p in cart.people], [p.id for p in cart.people])
    quotient, remainder = divmod(total, count)
    rank = sorted(range(count), key=lambda i: cart.people[i].id)
    equal = [quotient] * count
    for i in rank[:remainder]:
        equal[i] += 1
    return Plan(cart, tuple(quotes[g] for g in groups), baseline,
                None if allocation is None else tuple(allocation), tuple(equal), quotes[full], len(quotes))


def compare_topup(cart: Cart | dict, *, owner: str, price: Any, name: str = "Extra item", quantity: int = 1) -> dict:
    """Compare cash outlay for required items with / without one extra line."""
    cart = Cart.from_dict(cart) if isinstance(cart, dict) else cart
    raw = cart.to_dict()
    used_ids = {i.id for i in cart.items}
    item_id = "topup"
    while item_id in used_ids:
        item_id += "_"
    raw["items"].append({"id": item_id, "owner": owner, "name": name,
                         "unit_price": money(to_cents(price, "top-up price")), "quantity": quantity})
    expanded = Cart.from_dict(raw)
    before, after = optimize(cart), optimize(expanded)
    difference = after.total - before.total
    verdict = "costs_more" if difference > 0 else "saves_cash" if difference < 0 else "same_cash"
    return {"currency": cart.currency, "item": name, "owner": owner,
            "added_item_cost": money(to_cents(price) * quantity),
            "before_total": money(before.total), "after_total": money(after.total),
            "cash_change": money(difference), "verdict": verdict,
            "basis": "Cash outlay only. The second basket contains an extra item.",
            "before_budget_feasible": before.feasible, "after_budget_feasible": after.feasible}
