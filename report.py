from __future__ import annotations

import json
from html import escape
from importlib.resources import files

from .solver import optimize


def demo_cases() -> list[dict]:
    return json.loads(files("faircart").joinpath("assets/scenarios.json").read_text(encoding="utf-8"))


def render_dashboard(cases: list[dict]) -> str:
    if not cases:
        raise ValueError("At least one scenario is required.")
    case = cases[0]
    payload = [{**case, "result": optimize(case["cart"]).to_dict()}]
    data = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    assets = files("faircart").joinpath("assets")
    css = assets.joinpath("dashboard.css").read_text(encoding="utf-8")
    engine = assets.joinpath("engine.js").read_text(encoding="utf-8")
    ui = assets.joinpath("dashboard.js").read_text(encoding="utf-8")
    title = escape("FairCart | Group checkout planner")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head><body>
<header><a class="brand" href="#"><span class="brand-mark">f.</span>FairCart</a><span class="header-note">Group checkout planner</span><span class="offline">Works offline</span></header>
<main><section class="intro"><div><div class="eyebrow">SMARTER GROUP PURCHASES</div><h1>Save together.<br>Keep it fair.</h1><p>Find the cheapest way to order, then share the cost within everyone's limits.</p></div><div class="intro-note"><span>THE PAYMENT PROMISE</span><p>Your payment stays within your budget and your best solo price.</p></div></section>
<div class="workspace"><section class="inputs"><div class="section-title"><h2>Your group</h2><button id="reset" class="quiet">Reset inputs</button></div><p class="helper">Edit the basket amounts or budgets, then calculate.</p><div id="group-form"></div>
<div class="section-title terms"><h2>Store terms</h2></div><div id="store-form"></div><div id="coupon-form"></div>
<button class="primary" id="calculate">Calculate plan <span aria-hidden="true">↗</span></button><p id="input-error" class="error-text" role="alert"></p><p class="helper compact">Example prices and coupon rules. Amounts use two decimal places.</p></section>
<section class="results" aria-label="Calculation results" aria-live="polite"><div id="result"></div></section></div>
<section class="topup"><div><div class="eyebrow">BEFORE YOU ADD ONE MORE ITEM</div><h2>Does a top-up actually save money?</h2><p>Compare the full checkout cost with and without an extra item.</p></div><div class="topup-form"><label>Buyer<select id="topup-owner"></select></label><label>Extra item price<input id="topup-price" type="number" min="0" step="0.01" value="15.00"></label><button id="topup-check">Compare costs</button></div><div id="topup-result" role="status"></div></section>
<section class="how"><h2>How FairCart decides</h2><div><article><b>01</b><h3>Price every grouping</h3><p>Compare separate and combined orders using the supplied shipping and coupon terms.</p></article><article><b>02</b><h3>Protect each person</h3><p>Cap payments at each person's budget and best solo checkout price.</p></article><article><b>03</b><h3>Balance every cent</h3><p>Allocate the bill proportionally, adjust for caps, and keep the sum exact.</p></article></div></section>
<footer><span>FairCart 1.0.0</span><span>One store. Up to 8 people. One coupon per order. Group-wide settlement.</span></footer></main>
<noscript><p>This calculator needs JavaScript. The Python package also provides text and JSON reports.</p></noscript>
<script type="application/json" id="scenario-data">{data}</script><script>{engine}</script><script>{ui}</script></body></html>'''
