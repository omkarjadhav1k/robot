"""Authoritative Report Service providing SQL-aggregated business metrics."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.billing import Bill, Customer, PaymentStatus
from app.models.product import Product

logger = logging.getLogger(__name__)


class ReportService:
    """PostgreSQL-backed business intelligence reporting."""

    @staticmethod
    def get_business_summary(db: Session, business_id: Optional[Any] = None) -> Dict[str, Any]:
        """Aggregate store KPIs from database records."""
        now = datetime.now(timezone.utc)
        today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)

        # 1. Today's sales
        q_today = db.query(
            func.count(Bill.id).label("count"),
            func.coalesce(func.sum(Bill.total_amount), 0).label("revenue"),
        ).filter(Bill.created_at >= today_start)
        if business_id:
            q_today = q_today.filter(Bill.business_id == business_id)
        today_res = q_today.first()

        # 2. Total active products & low stock items count
        q_stock = db.query(
            func.count(Product.id).label("total_products"),
            func.sum(func.case((Product.current_stock <= Product.minimum_stock, 1), else_=0)).label("low_stock_count"),
        ).filter(Product.is_active == True)
        if business_id:
            q_stock = q_stock.filter(Product.business_id == business_id)
        stock_res = q_stock.first()

        # 3. Total outstanding customer credit
        q_cust = db.query(
            func.count(Customer.id).label("total_customers"),
            func.coalesce(func.sum(Customer.outstanding_balance), 0).label("total_due"),
        )
        if business_id:
            q_cust = q_cust.filter(Customer.business_id == business_id)
        cust_res = q_cust.first()

        return {
            "date": now.strftime("%Y-%m-%d"),
            "today_sales_count": int(today_res.count if today_res else 0),
            "today_revenue": float(today_res.revenue if today_res else 0.0),
            "total_products": int(stock_res.total_products if stock_res else 0),
            "low_stock_count": int(stock_res.low_stock_count if (stock_res and stock_res.low_stock_count) else 0),
            "total_customers": int(cust_res.total_customers if cust_res else 0),
            "total_credit_due": float(cust_res.total_due if cust_res else 0.0),
        }
