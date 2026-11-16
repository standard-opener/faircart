from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from faircart import Cart, FairCartError, allocate_payments, compare_topup, load_cart, money, optimize, quote_order, to_cents
from faircart.cli import main
from faircart.report import demo_cases, render_dashboard


def sample(name="shared"):
    return copy.deepcopy(next(c["cart"] for c in demo_cases() if c["id"] == name))


def partitions(values):
    if not values:
        yield []
        return
    first, *rest = values
    for blocks in partitions(rest):
        yield [(first,)] + blocks
        for i in range(len(blocks)):
            yield blocks[:i] + [(first,) + blocks[i]] + blocks[i + 1:]


def oracle_cost(raw, members):
    """Independent arithmetic over input dictionaries, without solver helpers."""
    cv = lambda v: int(Decimal(str(v)) * 100)
    subtotal = sum(cv(i["unit_price"]) * i.get("quantity", 1) for i in raw["items"] if i["owner"] in members)
    s = raw["store"]
    shipping = cv(s["shipping_fee"])
    if s.get("free_shipping_at") is not None and subtotal >= cv(s["free_shipping_at"]):
        shipping = 0
    discounts = [0]
    for c in raw.get("coupons", []):
        if c.get("owner") is not None and c["owner"] not in members or subtotal < cv(c["min_subtotal"]):
            continue
        discount = cv(c["amount"]) if c["kind"] == "fixed" else subtotal * cv(c["percent_off"]) // 10000
        if c.get("max_discount") is not None:
            discount = min(discount, cv(c["max_discount"]))
        discounts.append(min(discount, subtotal))
    return subtotal - max(discounts) + shipping


def random_carts(count, seed=3102):
    rng = random.Random(seed)
    carts = []
    for _ in range(count):
        n = rng.randint(1, 6)
        ids = [f"p{i}" for i in range(n)]
        coupons = []
        for k in range(rng.randint(0, 4)):
            c = {"id": f"C{k}", "kind": rng.choice(["fixed", "percent"]),
                 "min_subtotal": money(rng.randint(0, 13000)), "owner": rng.choice([None] + ids)}
            if c["kind"] == "fixed":
                c["amount"] = money(rng.randint(0, 6000))
            else:
                c["percent_off"] = money(rng.randint(0, 10000))
                if rng.choice([True, False]):
                    c["max_discount"] = money(rng.randint(0, 4000))
            coupons.append(c)
        carts.append({"title": "Generated cart", "currency": "HKD",
                      "people": [{"id": p, "name": p.upper(), "budget": money(rng.randint(0, 15000))} for p in ids],
                      "items": [{"id": f"i{i}", "owner": p, "name": "Basket", "unit_price": money(rng.randint(0, 9000)), "quantity": rng.randint(1, 3)} for i, p in enumerate(ids)],
                      "store": {"shipping_fee": money(rng.randint(0, 2000)), "free_shipping_at": rng.choice([None, "50.00", "100.00", "150.00"])},
                      "coupons": coupons})
    return carts


class FairCartTests(unittest.TestCase):
    def test_shared_cart_protects_small_buyer(self):
        p = optimize(sample())
        self.assertEqual((p.total, p.baselines, p.payments), (10800, (2400, 6000, 7200), (1661, 4154, 4985)))
        self.assertEqual(p.equal_payments, (3600, 3600, 3600))
        self.assertTrue(p.to_dict()["people"][0]["equal_split_breaks_cap"])

    def test_budget_cap_redistributes_only_within_other_limits(self):
        p = optimize(sample("capped"))
        self.assertEqual(p.payments, (1000, 4455, 5345))
        self.assertEqual(sum(p.payments), 10800)

    def test_two_orders_can_beat_merging_everyone(self):
        p = optimize(sample("split"))
        self.assertEqual((p.total, p.all_in_one.total, len(p.orders)), (7000, 8500, 2))
        self.assertEqual({o.coupon for o in p.orders}, {"AMY15", "CARA15"})
        self.assertEqual(sorted(x for o in p.orders for x in o.members), ["amy", "ben", "cara", "dan"])

    def test_infeasible_plan_reports_exact_shortfall_without_payments(self):
        p = optimize(sample("impossible"))
        self.assertFalse(p.feasible)
        self.assertIsNone(p.payments)
        self.assertEqual(p.shortfall, 2800)
        self.assertEqual(p.to_dict()["available_payment"], "80.00")
        self.assertTrue(all(x["payment"] is None for x in p.to_dict()["people"]))

    def test_topup_trap_includes_the_extra_item_cost(self):
        result = compare_topup(sample("topup"), owner="amy", price="15.00")
        self.assertEqual((result["before_total"], result["after_total"], result["cash_change"], result["verdict"]),
                         ("70.00", "73.00", "3.00", "costs_more"))

    def test_topup_can_save_cash_at_a_shipping_threshold(self):
        raw = sample("topup")
        raw["items"][0]["unit_price"] = "59.00"
        raw["store"]["free_shipping_at"] = "60.00"
        r = compare_topup(raw, owner="amy", price="1.00")
        self.assertEqual((r["cash_change"], r["verdict"]), ("-11.00", "saves_cash"))

    def test_topup_uses_an_independent_copy(self):
        raw = sample()
        before = copy.deepcopy(raw)
        compare_topup(raw, owner="amy", price="1.00")
        self.assertEqual(raw, before)

    def test_coupon_owner_must_be_in_the_order(self):
        raw = sample("split")
        cart = Cart.from_dict(raw)
        self.assertIsNone(quote_order(cart, ["ben", "dan"]).coupon)
        with self.assertRaises(FairCartError):
            quote_order(cart, ["amy", "amy"])

    def test_personal_coupon_cannot_be_reused_across_orders(self):
        p = optimize(sample("split"))
        personal = [o.coupon for o in p.orders if o.coupon]
        self.assertEqual(len(personal), len(set(personal)))

    def test_discount_does_not_reduce_shipping_qualification(self):
        raw = sample("topup")
        raw["items"][0]["unit_price"] = "70.00"
        raw["coupons"] = [{"id": "OFF20", "kind": "fixed", "min_subtotal": "70.00", "amount": "20.00"}]
        p = optimize(raw)
        self.assertEqual((p.total, p.orders[0].shipping), (5000, 0))

    def test_percent_discount_rounds_down_and_respects_cap(self):
        raw = sample("topup")
        raw["store"]["shipping_fee"] = "0.00"
        raw["items"][0]["unit_price"] = "1.03"
        raw["coupons"] = [{"id": "P", "kind": "percent", "min_subtotal": "0.00", "percent_off": "12.50", "max_discount": "0.10"}]
        self.assertEqual(optimize(raw).total, 93)
        del raw["coupons"][0]["max_discount"]
        self.assertEqual(optimize(raw).total, 91)

    def test_one_coupon_per_order_and_no_negative_merchandise(self):
        raw = sample("topup")
        raw["store"]["shipping_fee"] = "2.00"
        raw["coupons"] = [{"id": "A", "kind": "fixed", "min_subtotal": "0", "amount": "100.00"},
                          {"id": "B", "kind": "fixed", "min_subtotal": "0", "amount": "100.00"}]
        p = optimize(raw)
        self.assertEqual(p.total, 200)
        self.assertEqual(p.orders[0].coupon, "A")

    def test_each_baseline_includes_best_owned_coupon(self):
        raw = sample("topup")
        raw["coupons"] = [{"id": "OWN", "kind": "fixed", "min_subtotal": "0", "amount": "10.00", "owner": "amy"}]
        self.assertEqual(optimize(raw).baselines, (6000,))

    def test_public_coupon_can_repeat_in_separate_orders(self):
        raw = sample("split")
        raw["coupons"] = [{"id": "PUBLIC", "kind": "fixed", "min_subtotal": "40.00", "amount": "20.00", "owner": None}]
        p = optimize(raw)
        self.assertEqual(p.total, 6000)
        self.assertEqual([o.coupon for o in p.orders], ["PUBLIC", "PUBLIC"])

    def test_budget_is_capped_by_solo_price_even_when_budget_is_large(self):
        self.assertEqual(allocate_payments(100, [20, 100], [1000, 1000], ["a", "b"]), [17, 83])
        self.assertIsNone(allocate_payments(121, [20, 100], [1000, 1000]))

    def test_zero_price_and_zero_budget_are_supported(self):
        self.assertEqual(allocate_payments(0, [0, 0], [0, 0]), [0, 0])
        self.assertEqual(allocate_payments(10, [0, 20], [0, 20]), [0, 10])

    def test_rounding_is_exact_and_ties_use_person_id(self):
        self.assertEqual(allocate_payments(1, [1, 1, 1], [1, 1, 1], ["c", "a", "b"]), [0, 1, 0])
        self.assertEqual(allocate_payments(100, [100, 100, 100], [20, 100, 100]), [20, 40, 40])

    def test_allocation_invariants_over_500_generated_inputs(self):
        rng = random.Random(37)
        for _ in range(500):
            n = rng.randint(1, 8)
            baselines = [rng.randint(0, 10**7) for _ in range(n)]
            budgets = [rng.randint(0, 10**7) for _ in range(n)]
            capacity = sum(min(b, cap) for b, cap in zip(baselines, budgets))
            total = rng.randint(0, capacity + 1)
            result = allocate_payments(total, baselines, budgets)
            if total > capacity:
                self.assertIsNone(result)
            else:
                self.assertEqual(sum(result), total)
                self.assertTrue(all(0 <= p <= min(b, cap) for p, b, cap in zip(result, baselines, budgets)))

    def test_optimizer_matches_independent_partition_enumeration(self):
        for raw in random_carts(80):
            ids = [p["id"] for p in raw["people"]]
            expected = min(sum(oracle_cost(raw, group) for group in blocks) for blocks in partitions(ids))
            p = optimize(raw)
            self.assertEqual(p.total, expected)
            self.assertLessEqual(p.total, sum(p.baselines))
            capacity = sum(p.caps)
            self.assertEqual(p.feasible, p.total <= capacity)
            if p.feasible:
                self.assertEqual(sum(p.payments), p.total)
                self.assertTrue(all(value <= cap for value, cap in zip(p.payments, p.caps)))

    def test_whole_person_basket_multiple_lines_and_quantities(self):
        raw = sample("topup")
        raw["items"][0]["quantity"] = 2
        raw["items"].append({"id": "second", "owner": "amy", "name": "Second item", "unit_price": "4.50", "quantity": 3})
        self.assertEqual(optimize(raw).total, 12950)

    def test_cart_round_trip_and_inputs_are_not_modified(self):
        raw = sample()
        original = copy.deepcopy(raw)
        cart = Cart.from_dict(raw)
        self.assertEqual(Cart.from_dict(cart.to_dict()), cart)
        optimize(raw)
        self.assertEqual(raw, original)

    def test_money_parser_rejects_invalid_precision_nonfinite_and_floats(self):
        for v in [True, 1.2, None, "-1", "1.001", "NaN", "Infinity", "1e1000000", "1.00000000000000000000000000000001"]:
            with self.subTest(v=v), self.assertRaises(FairCartError):
                to_cents(v)
        self.assertEqual(to_cents("0.10"), 10)
        self.assertEqual(to_cents(Decimal("3.25")), 325)
        self.assertEqual(money(-3), "-0.03")

    def test_schema_rejects_unknown_keys_and_invalid_references(self):
        for mutation in [lambda c: c.update({"budegt": "10"}),
                         lambda c: c["items"][0].update(owner="missing"),
                         lambda c: c["people"][1].update(id="amy"),
                         lambda c: c["items"][0].update(quantity=True),
                         lambda c: c["coupons"][0].update(kind="stacked"),
                         lambda c: c["coupons"][0].update(owner="missing"),
                         lambda c: c["items"][0].update(unit_price="10000000.01")]:
            raw = sample()
            mutation(raw)
            with self.assertRaises(FairCartError):
                Cart.from_dict(raw)

    def test_percent_over_100_and_ambiguous_coupon_fields_fail(self):
        raw = sample()
        raw["coupons"][0] = {"id": "P", "kind": "percent", "percent_off": "101", "min_subtotal": "0"}
        with self.assertRaises(FairCartError):
            Cart.from_dict(raw)
        raw["coupons"][0] = {"id": "F", "kind": "fixed", "amount": "1", "percent_off": "10", "min_subtotal": "0"}
        with self.assertRaises(FairCartError):
            Cart.from_dict(raw)

    def test_maximum_group_size_and_fewer_order_tie_break(self):
        raw = random_carts(1)[0]
        raw["people"] = [{"id": str(i), "name": str(i), "budget": "10"} for i in range(8)]
        raw["items"] = [{"id": str(i), "owner": str(i), "name": "Item", "unit_price": "1"} for i in range(8)]
        raw["coupons"] = []
        raw["store"] = {"shipping_fee": "0"}
        p = optimize(raw)
        self.assertEqual((p.total, len(p.orders), p.subset_quotes), (800, 1, 255))
        raw["people"].append({"id": "extra", "name": "Extra", "budget": "10"})
        with self.assertRaises(FairCartError):
            optimize(raw)

    def test_report_escapes_untrusted_content_in_embedded_json(self):
        raw = sample()
        raw["title"] = "</script><img src=x onerror=alert(1)>"
        html = render_dashboard([{"id": "test", "label": "Test", "cart": raw}])
        self.assertNotIn(raw["title"], html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn('<html lang="en">', html)

    def test_cli_exit_codes_and_refusal_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cart.json"
            path.write_text(json.dumps(sample("impossible")))
            before = path.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["plan", str(path)]), 1)
                self.assertEqual(main(["plan", str(path), "--output", str(path)]), 2)
                self.assertEqual(main(["plan", str(path.parent / "missing")]), 2)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(FairCartError):
                load_cart(path.parent / "missing")

    def test_browser_engine_matches_python_for_205_carts_and_topups(self):
        node = os.environ.get("FAIRCART_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is optional; set FAIRCART_NODE to run browser-engine parity checks.")
        raw = [c["cart"] for c in demo_cases()] + random_carts(200, seed=76)
        edge = sample("topup")
        edge["store"] = {"shipping_fee": "1000000000.00", "free_shipping_at": None}
        edge["people"][0]["budget"] = "1000000000.00"
        raw[-1] = edge
        engine = str(files("faircart").joinpath("assets/engine.js"))
        script = "const fs=require('fs');require(process.argv[1]);const carts=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(carts.map(c=>({plan:FairCart.solve(c),topup:FairCart.topup(c,c.people[0].id,'1.25')}))));"
        response = subprocess.run([node, "-e", script, engine], input=json.dumps(raw), capture_output=True, text=True, check=True)
        browser_results = json.loads(response.stdout)
        for cart, actual in zip(raw, browser_results):
            self.assertEqual(actual["plan"], optimize(cart).to_dict())
            self.assertEqual(actual["topup"], compare_topup(cart, owner=cart["people"][0]["id"], price="1.25"))


if __name__ == "__main__":
    unittest.main()
