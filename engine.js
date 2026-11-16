/* FairCart browser engine. All prices are integer cents. */
(function (root) {
  "use strict";
  const fail = message => { throw new Error(message); };
  const money = value => `${value < 0 ? "-" : ""}${Math.floor(Math.abs(value) / 100)}.${String(Math.abs(value) % 100).padStart(2, "0")}`;
  function cents(value, label = "amount") {
    const text = String(value).trim();
    if ((typeof value !== "string" && !(typeof value === "number" && Number.isInteger(value))) || !/^\+?\d+(?:\.\d{1,2})?$/.test(text)) fail(`${label}: use a nonnegative amount with at most two decimal places.`);
    const [whole, fraction = ""] = text.replace(/^\+/, "").split(".");
    const result = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
    if (!Number.isSafeInteger(result)) fail(`${label}: amount is out of range.`);
    return result;
  }
  function inputCents(value, label = "amount") {
    const result = cents(value, label);
    if (result > 100000000000) fail(`${label}: amount is out of range.`);
    return result;
  }
  function keys(value, allowed, required, label) {
    if (!value || Array.isArray(value) || typeof value !== "object" || Object.keys(value).some(k => !allowed.includes(k)) || required.some(k => !(k in value))) fail(`Invalid ${label} fields.`);
  }
  function text(value, label) {
    if (typeof value !== "string" || !value.trim() || [...value].length > 120) fail(`Invalid ${label}.`);
    return value.trim();
  }
  function normalize(data) {
    keys(data, ["title", "currency", "people", "items", "store", "coupons"], ["people", "items", "store"], "cart");
    if (!Array.isArray(data.people) || data.people.length < 1 || data.people.length > 8) fail("Use between 1 and 8 people.");
    if (!Array.isArray(data.items) || data.items.length < 1 || data.items.length > 100) fail("Use between 1 and 100 item lines.");
    const people = data.people.map(p => {
      keys(p, ["id", "name", "budget"], ["id", "name", "budget"], "person");
      return {id: text(p.id, "person ID"), name: text(p.name, "name"), budget: inputCents(p.budget, "budget")};
    });
    const ids = new Set(people.map(p => p.id));
    if (ids.size !== people.length) fail("Person IDs must be unique.");
    const items = data.items.map(i => {
      keys(i, ["id", "owner", "name", "unit_price", "quantity"], ["id", "owner", "name", "unit_price"], "item");
      const owner = text(i.owner, "owner"), quantity = i.quantity === undefined ? 1 : i.quantity;
      if (!ids.has(owner)) fail("Unknown item owner.");
      if (!Number.isInteger(quantity) || quantity < 1 || quantity > 1000) fail("quantity must be an integer from 1 to 1000.");
      return {id: text(i.id, "item ID"), owner, name: text(i.name, "item name"), price: inputCents(i.unit_price, "unit price"), quantity};
    });
    if (new Set(items.map(i => i.id)).size !== items.length) fail("Item IDs must be unique.");
    if ([...ids].some(id => !items.some(i => i.owner === id))) fail("Every person must own at least one item line.");
    if (items.reduce((s, i) => s + i.price * i.quantity, 0) > 1000000000) fail("Combined merchandise cannot exceed 10000000.00.");
    keys(data.store, ["shipping_fee", "free_shipping_at"], ["shipping_fee"], "store");
    const shipping = inputCents(data.store.shipping_fee, "shipping fee");
    const threshold = data.store.free_shipping_at == null ? null : inputCents(data.store.free_shipping_at, "free shipping threshold");
    const coupons = data.coupons === undefined ? [] : data.coupons;
    if (!Array.isArray(coupons) || coupons.length > 16) fail("Use at most 16 coupons.");
    const normalizedCoupons = coupons.map(c => {
      keys(c, ["id", "kind", "min_subtotal", "amount", "percent_off", "max_discount", "owner"], ["id", "kind", "min_subtotal"], "coupon");
      if (!["fixed", "percent"].includes(c.kind)) fail("Coupon kind must be fixed or percent.");
      const owner = c.owner == null ? null : c.owner;
      if (owner !== null && !ids.has(owner)) fail("Unknown coupon owner.");
      if (c.kind === "fixed" && (!("amount" in c) || "percent_off" in c || "max_discount" in c)) fail("Invalid fixed coupon.");
      if (c.kind === "percent" && (!("percent_off" in c) || "amount" in c)) fail("Invalid percent coupon.");
      const amount = c.kind === "fixed" ? inputCents(c.amount) : 0;
      const rate = c.kind === "percent" ? inputCents(c.percent_off) : 0;
      if (rate > 10000) fail("percent_off cannot exceed 100.");
      return {id: text(c.id, "coupon ID"), kind: c.kind, minimum: inputCents(c.min_subtotal), owner,
              amount, rate, cap: c.max_discount == null ? null : inputCents(c.max_discount)};
    });
    if (new Set(normalizedCoupons.map(c => c.id)).size !== normalizedCoupons.length) fail("Coupon IDs must be unique.");
    const currency = data.currency === undefined ? "HKD" : data.currency;
    if (typeof currency !== "string" || !/^[a-zA-Z]{3}$/.test(currency)) fail("currency must be a three-letter code.");
    return {title: text(data.title === undefined ? "Group checkout" : data.title, "title"), currency: currency.toUpperCase(), people, items, shipping, threshold, coupons: normalizedCoupons};
  }
  function compareText(a, b) {
    const left = Array.from(a, c => c.codePointAt(0)), right = Array.from(b, c => c.codePointAt(0));
    for (let i = 0; i < Math.min(left.length, right.length); i++) if (left[i] !== right[i]) return left[i] < right[i] ? -1 : 1;
    return left.length - right.length;
  }
  function quote(cart, mask) {
    const members = cart.people.filter((p, i) => mask & (1 << i)).map(p => p.id);
    const subtotal = cart.items.filter(i => members.includes(i.owner)).reduce((s, i) => s + i.price * i.quantity, 0);
    const shipping = cart.threshold !== null && subtotal >= cart.threshold ? 0 : cart.shipping;
    let result = {members, subtotal, discount: 0, shipping, coupon: null, total: subtotal + shipping};
    for (const c of cart.coupons) {
      if (subtotal < c.minimum || c.owner !== null && !members.includes(c.owner)) continue;
      let discount = c.kind === "fixed" ? c.amount : Math.floor(subtotal * c.rate / 10000);
      if (c.cap !== null) discount = Math.min(discount, c.cap);
      discount = Math.min(discount, subtotal);
      const candidate = {members, subtotal, shipping, discount, coupon: c.id, total: subtotal - discount + shipping};
      if (candidate.total < result.total || candidate.total === result.total && compareText(candidate.coupon || "", result.coupon || "") < 0) result = candidate;
    }
    return result;
  }
  function allocate(total, baselines, budgets, ids) {
    const caps = baselines.map((b, i) => Math.min(b, budgets[i]));
    if (total > caps.reduce((a, b) => a + b, 0)) return null;
    const raw = caps.map(() => [0n, 1n]);
    let active = baselines.map((b, i) => i).filter(i => baselines[i] > 0 && caps[i] > 0), remaining = BigInt(total);
    while (active.length) {
      const weight = active.reduce((s, i) => s + BigInt(baselines[i]), 0n);
      const fixed = active.filter(i => remaining * BigInt(baselines[i]) >= BigInt(caps[i]) * weight);
      if (!fixed.length) { active.forEach(i => {raw[i] = [remaining * BigInt(baselines[i]), weight];}); break; }
      fixed.forEach(i => {raw[i] = [BigInt(caps[i]), 1n]; remaining -= BigInt(caps[i]);});
      active = active.filter(i => !fixed.includes(i));
    }
    const payments = raw.map(([n, d]) => Number(n / d));
    const remainder = total - payments.reduce((a, b) => a + b, 0);
    const rank = raw.map((_, i) => i).sort((a, b) => {
      const left = raw[a][0] % raw[a][1] * raw[b][1], right = raw[b][0] % raw[b][1] * raw[a][1];
      return left > right ? -1 : left < right ? 1 : compareText(ids[a], ids[b]);
    });
    rank.slice(0, remainder).forEach(i => {payments[i]++;});
    return payments;
  }
  function solve(data) {
    const cart = normalize(data), count = cart.people.length, full = (1 << count) - 1;
    const quotes = Array.from({length: full + 1}, (_, mask) => mask ? quote(cart, mask) : null), memo = new Map([[0, {total: 0, groups: []}]]);
    function preferred(a, b) {
      if (!b || a.total !== b.total) return !b || a.total < b.total;
      if (a.groups.length !== b.groups.length) return a.groups.length < b.groups.length;
      for (let i = 0; i < a.groups.length; i++) if (a.groups[i] !== b.groups[i]) return a.groups[i] < b.groups[i];
      return false;
    }
    function best(mask) {
      if (memo.has(mask)) return memo.get(mask);
      const first = mask & -mask;
      let chosen;
      for (let sub = mask; sub; sub = (sub - 1) & mask) if (sub & first) {
        const rest = best(mask ^ sub), candidate = {total: quotes[sub].total + rest.total, groups: [sub, ...rest.groups].sort((a, b) => a - b)};
        if (preferred(candidate, chosen)) chosen = candidate;
      }
      memo.set(mask, chosen); return chosen;
    }
    const choice = best(full), baselines = cart.people.map((_, i) => quotes[1 << i].total), budgets = cart.people.map(p => p.budget), ids = cart.people.map(p => p.id);
    const payments = allocate(choice.total, baselines, budgets, ids), caps = baselines.map((b, i) => Math.min(b, budgets[i]));
    const equal = cart.people.map(() => Math.floor(choice.total / count));
    [...ids.keys()].sort((a, b) => compareText(ids[a], ids[b])).slice(0, choice.total % count).forEach(i => {equal[i]++;});
    const available = caps.reduce((a, b) => a + b, 0), solo = baselines.reduce((a, b) => a + b, 0);
    const orderObject = o => ({members: o.members, subtotal: money(o.subtotal), discount: money(o.discount), shipping: money(o.shipping), coupon: o.coupon, total: money(o.total)});
    return {title: cart.title, currency: cart.currency, status: payments === null ? "infeasible" : "feasible", solo_total: money(solo), optimal_total: money(choice.total), potential_saving: money(solo - choice.total), all_in_one_total: money(quotes[full].total), available_payment: money(available), shortfall: money(Math.max(0, choice.total - available)), order_count: choice.groups.length, orders: choice.groups.map(g => orderObject(quotes[g])),
      people: cart.people.map((p, i) => ({id: p.id, name: p.name, basket: money(cart.items.filter(x => x.owner === p.id).reduce((s, x) => s + x.price * x.quantity, 0)), solo_cost: money(baselines[i]), budget: money(p.budget), payment_cap: money(caps[i]), payment: payments === null ? null : money(payments[i]), saving: payments === null ? null : money(baselines[i] - payments[i]), equal_split: money(equal[i]), equal_split_breaks_cap: equal[i] > caps[i]})),
      checks: {budgets_met: payments !== null, no_one_worse_off: payments !== null, payments_match_total: payments !== null && payments.reduce((a, b) => a + b, 0) === choice.total}, search: {method: "exact subset dynamic programming", subset_quotes: full}, policy: "Capped proportional payments based on best solo prices, settled across the whole group."};
  }
  function topup(data, owner, price, name = "Extra item", quantity = 1) {
    const expanded = JSON.parse(JSON.stringify(data));
    let id = "topup";
    while (expanded.items.some(i => i.id === id)) id += "_";
    expanded.items.push({id, owner, name, unit_price: money(inputCents(price)), quantity});
    const before = solve(data), after = solve(expanded), difference = cents(after.optimal_total) - cents(before.optimal_total);
    return {currency: before.currency, item: name, owner, added_item_cost: money(inputCents(price) * quantity), before_total: before.optimal_total, after_total: after.optimal_total, cash_change: money(difference), verdict: difference > 0 ? "costs_more" : difference < 0 ? "saves_cash" : "same_cash", basis: "Cash outlay only. The second basket contains an extra item.", before_budget_feasible: before.status === "feasible", after_budget_feasible: after.status === "feasible"};
  }
  root.FairCart = {solve, normalize, allocate, topup, money, cents};
})(globalThis);
