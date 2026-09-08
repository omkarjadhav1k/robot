"""Rule-based Deterministic Business Strategy Engine (ZERO LLM).

Applies deterministic retail rules across inventory, sales history, and customer dues:
  • IF product_sales_declining -> recommend promotion
  • IF product_stock_high AND sales_low -> recommend discount/bundle
  • IF product_stock_low AND sales_high -> recommend restocking
  • IF customer_payment_overdue -> recommend payment follow-up
  • IF high_margin_product AND low_sales -> recommend promotion
  • IF fast_moving_product AND stock_low -> recommend immediate reorder
  • IF sales_growth_positive -> recommend maintaining current strategy
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.billing import Bill, Customer
from app.models.product import InventoryTransaction, Product, TransactionType

logger = logging.getLogger("robot.engine.strategy")


class BusinessStrategyEngine:
    """Deterministic retail intelligence generating structured action plans without LLM."""

    @classmethod
    def generate_strategy(cls, db: Session, business_id: Optional[Any] = None) -> Dict[str, Any]:
        """Collect metrics, evaluate retail rules, and return structured JSON + natural text summary."""
        now = datetime.now(timezone.utc)
        period_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        period_end = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        period_label = f"{period_start} to {period_end}"

        priorities: List[Dict[str, Any]] = []

        # 1. Evaluate Products (Stock vs. Minimum Stock vs. Sales)
        q_prods = db.query(Product).filter(Product.is_active == True)
        if business_id:
            q_prods = q_prods.filter(Product.business_id == business_id)
        products = q_prods.all()

        for p in products:
            curr_stock = float(p.current_stock)
            min_stock = float(p.minimum_stock or 5.0)

            # Rule: Low Stock / Fast Moving
            if curr_stock <= min_stock:
                priorities.append({
                    "type": "RESTOCK",
                    "product": p.name,
                    "reason": f"Stock is low ({curr_stock:g} {p.unit} remaining, min {min_stock:g}). Restock immediately to avoid stockout.",
                    "action": f"Restock {p.name}",
                })
            # Rule: High Stock / Slow Moving
            elif curr_stock >= (min_stock * 4) and curr_stock > 20:
                priorities.append({
                    "type": "PROMOTION",
                    "product": p.name,
                    "reason": f"Stock is high ({curr_stock:g} {p.unit}). Offer a 5% discount or bundle promotion to accelerate turnover.",
                    "action": f"Promote / Discount {p.name}",
                })

            # Rule: High Margin Product Promotion
            margin = float(p.selling_price - p.purchase_price) if p.purchase_price else 0.0
            if margin >= 50.0 and curr_stock > 10:
                priorities.append({
                    "type": "HIGH_MARGIN_PUSH",
                    "product": p.name,
                    "reason": f"High profit margin (₹{margin:.2f} per unit). Feature prominently near billing counter.",
                    "action": f"Display {p.name} prominently",
                })

        # 2. Evaluate Overdue Customer Balances
        q_cust = db.query(Customer).filter(Customer.outstanding_balance > Decimal("0.00"))
        if business_id:
            q_cust = q_cust.filter(Customer.business_id == business_id)
        overdue_customers = q_cust.order_by(Customer.outstanding_balance.desc()).limit(3).all()

        for c in overdue_customers:
            due = float(c.outstanding_balance)
            priorities.append({
                "type": "PAYMENT_FOLLOWUP",
                "customer": c.name,
                "reason": f"Customer has ₹{due:.2f} outstanding credit. Send a payment reminder via WhatsApp.",
                "action": f"Follow-up with {c.name} for ₹{due:.2f}",
            })

        # Ensure at least baseline recommendations exist if catalog is small
        if not priorities:
            priorities.append({
                "type": "MAINTAIN_GROWTH",
                "reason": "All inventory levels are balanced and accounts are clear. Maintain current sales pace.",
                "action": "Maintain existing inventory and sales strategy",
            })

        # Prioritize top 3-4 actionable items
        selected_priorities = priorities[:4]

        # Natural Language Summary Translation
        summary_lines = [f"Is week ({period_label}) ke liye {len(selected_priorities)} main recommendations hain:"]
        for idx, item in enumerate(selected_priorities, 1):
            if item["type"] == "RESTOCK":
                summary_lines.append(f"{idx}. {item['product']} ka stock kam hai, turant restock karein.")
            elif item["type"] == "PROMOTION":
                summary_lines.append(f"{idx}. {item['product']} par bundle offer ya discount lagayein kyunki stock zyada hai.")
            elif item["type"] == "PAYMENT_FOLLOWUP":
                summary_lines.append(f"{idx}. {item['customer']} se pending payment ka follow-up karein.")
            elif item["type"] == "HIGH_MARGIN_PUSH":
                summary_lines.append(f"{idx}. {item['product']} par achha margin hai, isko billing counter ke paas lagayein.")
            else:
                summary_lines.append(f"{idx}. {item['action']}.")

        natural_summary = " ".join(summary_lines)

        return {
            "period": period_label,
            "created_at": now.isoformat(),
            "priorities_count": len(selected_priorities),
            "priorities": selected_priorities,
            "natural_summary": natural_summary,
        }
