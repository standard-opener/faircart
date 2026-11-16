from pathlib import Path

from faircart import compare_topup, load_cart, optimize

examples = Path(__file__).resolve().parent
for case in ["shared", "capped", "split", "impossible"]:
    print(optimize(load_cart(examples / f"{case}.json")).to_text())
    print()

print("Top-up comparison:")
print(compare_topup(load_cart(examples / "topup.json"), owner="amy", price="15.00", name="Extra snack"))
