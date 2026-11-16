# FairCart Quick Start

FairCart helps friends place group orders and share the bill within each
person's budget and solo price.

## Try the calculator

Open `FairCart_Demo.html` in this folder. It runs offline in a browser.
No installation is needed for this interface.

The calculator opens with Amy, Ben and Cara's purchase ready to use. The group
saves HKD 48. Amy pays 16.61 instead of the equal share of 36.00.

Edit the names, basket amounts, budgets, store terms or coupons, then click
**Calculate plan**. For a quick demonstration, change Amy's maximum payment to
10.00. The payments adjust to 10.00, 44.55 and 53.45.

Use **Add person** and **Add coupon** for a new purchase. Public coupons apply
once per order. A personal coupon requires its owner's basket in that order.

## Install the Python package

From this folder, with Python 3.10 or newer:

```bash
python -m pip install .
python examples/demo.py
python -m faircart plan examples/shared.json
```

Use `python3` if that is the Python command on your computer.

To generate another standalone calculator, choose a new output filename:

```bash
python -m faircart demo --output my-calculator.html
```

See `README.md` for the input format, Python API, examples and tests.
