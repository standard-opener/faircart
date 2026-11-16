from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from typing import Any


class FairCartError(ValueError):
    """Invalid cart or unsupported monetary input."""


def to_cents(value: Any, label: str = "amount") -> int:
    """Parse a nonnegative amount with at most two decimal places."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise FairCartError(f"{label}: use a decimal string, integer or Decimal.")
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number > Decimal("1000000000"):
            raise FairCartError(f"{label}: amount must be between 0 and 1000000000.")
        with localcontext() as context:
            context.prec = 40
            rounded = number.quantize(Decimal("0.01"))
            if number != rounded:
                raise FairCartError(f"{label}: use a nonnegative amount with at most two decimal places.")
            return int(rounded * 100)
    except (DecimalException, ValueError, OverflowError) as exc:
        if isinstance(exc, FairCartError):
            raise
        raise FairCartError(f"{label}: invalid monetary amount.") from exc


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def _keys(data: Any, allowed: set[str], required: set[str], label: str) -> dict:
    if not isinstance(data, dict):
        raise FairCartError(f"{label} must be an object.")
    if set(data) - allowed or required - set(data):
        raise FairCartError(f"{label}: unexpected or missing keys. Allowed: {sorted(allowed)}; required: {sorted(required)}.")
    return data


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise FairCartError(f"{label} must be a nonempty string of at most 120 characters.")
    return value.strip()


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    budget: int


@dataclass(frozen=True)
class Item:
    id: str
    owner: str
    name: str
    unit_price: int
    quantity: int

    @property
    def subtotal(self) -> int:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Coupon:
    id: str
    kind: str
    min_subtotal: int
    amount: int = 0
    rate_bps: int = 0
    max_discount: int | None = None
    owner: str | None = None


@dataclass(frozen=True)
class Cart:
    title: str
    currency: str
    people: tuple[Person, ...]
    items: tuple[Item, ...]
    shipping_fee: int
    free_shipping_at: int | None
    coupons: tuple[Coupon, ...]

    @classmethod
    def from_dict(cls, raw: dict) -> "Cart":
        data = _keys(raw, {"title", "currency", "people", "items", "store", "coupons"},
                     {"people", "items", "store"}, "cart")
        title = _text(data.get("title", "Group checkout"), "title")
        currency = data.get("currency", "HKD")
        if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise FairCartError("currency must be a three-letter code.")
        people_raw, items_raw, coupons_raw = data["people"], data["items"], data.get("coupons", [])
        if not isinstance(people_raw, list) or not 1 <= len(people_raw) <= 8:
            raise FairCartError("Use between 1 and 8 people.")
        if not isinstance(items_raw, list) or not 1 <= len(items_raw) <= 100:
            raise FairCartError("Use between 1 and 100 item lines.")
        if not isinstance(coupons_raw, list) or len(coupons_raw) > 16:
            raise FairCartError("Use at most 16 coupons.")
        people = []
        for p in people_raw:
            _keys(p, {"id", "name", "budget"}, {"id", "name", "budget"}, "person")
            people.append(Person(_text(p["id"], "person.id"), _text(p["name"], "person.name"),
                                 to_cents(p["budget"], "budget")))
        ids = {p.id for p in people}
        if len(ids) != len(people):
            raise FairCartError("Person IDs must be unique.")
        items = []
        for item in items_raw:
            _keys(item, {"id", "owner", "name", "unit_price", "quantity"},
                  {"id", "owner", "name", "unit_price"}, "item")
            owner = _text(item["owner"], "item.owner")
            quantity = item.get("quantity", 1)
            if owner not in ids:
                raise FairCartError(f"Unknown item owner: {owner}.")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 1000:
                raise FairCartError("quantity must be an integer from 1 to 1000.")
            items.append(Item(_text(item["id"], "item.id"), owner, _text(item["name"], "item.name"),
                              to_cents(item["unit_price"], "unit_price"), quantity))
        if len({i.id for i in items}) != len(items):
            raise FairCartError("Item IDs must be unique.")
        if {i.owner for i in items} != ids:
            raise FairCartError("Every person must own at least one item line.")
        if sum(i.subtotal for i in items) > 1000000000:
            raise FairCartError("Combined merchandise cannot exceed 10000000.00.")
        store = _keys(data["store"], {"shipping_fee", "free_shipping_at"}, {"shipping_fee"}, "store")
        shipping = to_cents(store["shipping_fee"], "shipping_fee")
        threshold = store.get("free_shipping_at")
        threshold = None if threshold is None else to_cents(threshold, "free_shipping_at")
        coupons = []
        for coupon in coupons_raw:
            _keys(coupon, {"id", "kind", "min_subtotal", "amount", "percent_off", "max_discount", "owner"},
                  {"id", "kind", "min_subtotal"}, "coupon")
            kind = coupon["kind"]
            if kind not in ("fixed", "percent"):
                raise FairCartError("Coupon kind must be fixed or percent.")
            owner = coupon.get("owner")
            if owner is not None and (not isinstance(owner, str) or owner not in ids):
                raise FairCartError("Coupon owner must be an existing person ID or null.")
            amount, rate, cap = 0, 0, None
            if kind == "fixed":
                if "amount" not in coupon or "percent_off" in coupon or "max_discount" in coupon:
                    raise FairCartError("A fixed coupon requires amount and cannot contain percent fields.")
                amount = to_cents(coupon["amount"], "coupon.amount")
            else:
                if "percent_off" not in coupon or "amount" in coupon:
                    raise FairCartError("A percent coupon requires percent_off and cannot contain amount.")
                rate = to_cents(coupon["percent_off"], "percent_off")
                if rate > 10000:
                    raise FairCartError("percent_off cannot exceed 100.")
                cap = None if coupon.get("max_discount") is None else to_cents(coupon["max_discount"], "max_discount")
            coupons.append(Coupon(_text(coupon["id"], "coupon.id"), kind,
                                  to_cents(coupon["min_subtotal"], "min_subtotal"), amount, rate, cap, owner))
        if len({c.id for c in coupons}) != len(coupons):
            raise FairCartError("Coupon IDs must be unique.")
        return cls(title, currency.upper(), tuple(people), tuple(items), shipping, threshold, tuple(coupons))

    def to_dict(self) -> dict:
        coupons = []
        for c in self.coupons:
            row = {"id": c.id, "kind": c.kind, "min_subtotal": money(c.min_subtotal), "owner": c.owner}
            if c.kind == "fixed":
                row["amount"] = money(c.amount)
            else:
                row["percent_off"] = money(c.rate_bps)
                if c.max_discount is not None:
                    row["max_discount"] = money(c.max_discount)
            coupons.append(row)
        return {"title": self.title, "currency": self.currency,
                "people": [{"id": p.id, "name": p.name, "budget": money(p.budget)} for p in self.people],
                "items": [{**asdict(i), "unit_price": money(i.unit_price)} for i in self.items],
                "store": {"shipping_fee": money(self.shipping_fee),
                          "free_shipping_at": None if self.free_shipping_at is None else money(self.free_shipping_at)},
                "coupons": coupons}


def load_cart(path: str | Path) -> Cart:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_float=Decimal)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FairCartError(f"Cannot load cart: {exc}") from exc
    return Cart.from_dict(data)
