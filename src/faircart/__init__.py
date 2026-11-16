"""Group checkout planning with exact monetary arithmetic."""

from .model import Cart, FairCartError, load_cart, money, to_cents
from .solver import allocate_payments, compare_topup, optimize, quote_order

__version__ = "1.0.0"
__all__ = ["Cart", "FairCartError", "load_cart", "money", "to_cents",
           "allocate_payments", "compare_topup", "optimize", "quote_order"]
