"""Authoritative Business endpoints for Inventory, Billing, Customers, and Reports."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.billing import BillSource
from app.services.billing_service import BillingService
from app.services.customer_service import CustomerService
from app.services.inventory_service import InventoryService
from app.services.report_service import ReportService

router = APIRouter()


class BillCreateRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(..., description="List of items with name and quantity")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    payment_method: str = "CASH"
    discount: float = 0.0
    tax_rate: float = 0.0


# ------------------------------------------------------------------------------
# Inventory Endpoints
# ------------------------------------------------------------------------------

@router.get("/inventory/products", summary="List store products")
def list_products(
    business_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve catalog products with prices and current stock levels."""
    return InventoryService.list_all_products(db, business_id=business_id, limit=limit)


@router.get("/inventory/low-stock", summary="Get low stock items")
def get_low_stock(
    business_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return inventory items at or below reorder threshold."""
    return InventoryService.get_low_stock_items(db, business_id=business_id, limit=limit)


@router.get("/inventory/stock/{product_name}", summary="Query product stock")
def get_product_stock(
    product_name: str,
    business_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Fetch live stock and unit price for a given product."""
    res = InventoryService.get_stock(db, product_name, business_id=business_id)
    if not res.get("found"):
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


# ------------------------------------------------------------------------------
# Billing Endpoints
# ------------------------------------------------------------------------------

@router.get("/billing/today", summary="Get today's sales and bills")
def get_todays_bills(
    business_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Fetch verified today's bill count and revenue."""
    return BillingService.get_todays_bills(db, business_id=business_id)


@router.post("/billing", status_code=status.HTTP_201_CREATED, summary="Create a new invoice")
def create_bill(
    req: BillCreateRequest,
    business_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Atomically generate an invoice, deduct stock, and register payment/credit."""
    try:
        return BillingService.create_bill(
            db=db,
            items_requested=req.items,
            customer_name=req.customer_name,
            customer_phone=req.customer_phone,
            payment_method=req.payment_method,
            discount=req.discount,
            tax_rate=req.tax_rate,
            source=BillSource.APP_MANUAL,
            business_id=business_id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create bill: {str(e)}")


# ------------------------------------------------------------------------------
# Customer Endpoints
# ------------------------------------------------------------------------------

@router.get("/customers/balance/{customer_name}", summary="Get customer balance")
def get_customer_balance(
    customer_name: str,
    business_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Look up customer account balance and ledger status."""
    res = CustomerService.get_customer_balance(db, customer_name, business_id=business_id)
    if not res.get("found"):
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


# ------------------------------------------------------------------------------
# Report Endpoints
# ------------------------------------------------------------------------------

@router.get("/reports/summary", summary="Store business KPI summary")
def get_business_summary(
    business_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return today's revenue, active product count, low stock count, and total credit due."""
    return ReportService.get_business_summary(db, business_id=business_id)
