"""Business AI Robot — FastAPI Central Brain Entrypoint."""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("business_ai_robot")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown routines."""
    logger.info("Initializing Business AI Robot Central Brain...")
    logger.info(f"Environment: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")

    # Synchronize database tables
    try:
        from app.database.base import Base
        from app.database.session import SessionLocal, engine
        import app.models  # Ensures all 18 models are loaded

        Base.metadata.create_all(bind=engine)
        logger.info("Database tables synchronized successfully.")

        # Seed initial business and demo catalog if empty
        with SessionLocal() as db:
            from decimal import Decimal
            from app.models.business import Business
            from app.models.product import Product

            biz = db.query(Business).first()
            if not biz:
                biz = Business(
                    name="Business AI Robot Store",
                    owner_name="Store Owner",
                    business_type="Retail Grocery & General Store",
                    currency="INR",
                )
                db.add(biz)
                db.flush()
                logger.info("Created default business tenant: %s", biz.id)

            # Check if products exist
            prod_count = db.query(Product).filter(Product.business_id == biz.id).count()
            if prod_count == 0:
                seed_items = [
                    ("Basmati Rice", "kg", Decimal("85.00"), Decimal("50.00"), Decimal("10.00")),
                    ("Sugar", "kg", Decimal("45.00"), Decimal("40.00"), Decimal("10.00")),
                    ("Tata Salt", "packet", Decimal("28.00"), Decimal("5.00"), Decimal("10.00")),
                    ("Sunflower Oil 1L", "bottle", Decimal("150.00"), Decimal("25.00"), Decimal("5.00")),
                    ("Wheat Flour 5kg", "bag", Decimal("210.00"), Decimal("18.00"), Decimal("3.00")),
                    ("Milk 1L", "packet", Decimal("60.00"), Decimal("30.00"), Decimal("5.00")),
                    ("Tea Powder 250g", "box", Decimal("120.00"), Decimal("15.00"), Decimal("4.00")),
                    ("Tea", "cup", Decimal("20.00"), Decimal("100.00"), Decimal("10.00")),
                    ("Veg Sandwich", "pcs", Decimal("80.00"), Decimal("50.00"), Decimal("5.00")),
                ]
                for name, unit, price, stock, min_stock in seed_items:
                    p = Product(
                        business_id=biz.id,
                        name=name,
                        unit=unit,
                        selling_price=price,
                        purchase_price=price * Decimal("0.8"),
                        current_stock=stock,
                        minimum_stock=min_stock,
                        is_active=True,
                    )
                    db.add(p)
                db.commit()
                logger.info("Seeded %d store products into database.", len(seed_items))

            # Ensure essential products exist and have realistic stock and price
            for p_name, p_unit, p_price, p_stock in [
                ("Tata Salt", "packet", Decimal("28.00"), Decimal("37.00")),
                ("Surf Excel", "packet", Decimal("140.00"), Decimal("50.00")),
                ("Sugar", "kg", Decimal("42.00"), Decimal("10.00")),
                ("Maggi", "packet", Decimal("14.00"), Decimal("40.00")),
                ("Basmati Rice", "kg", Decimal("85.00"), Decimal("50.00")),
                ("Tea", "cup", Decimal("20.00"), Decimal("100.00")),
                ("Veg Sandwich", "pcs", Decimal("80.00"), Decimal("50.00")),
            ]:
                existing_p = db.query(Product).filter(Product.name.ilike(p_name)).first()
                if not existing_p:
                    db.add(Product(
                        business_id=biz.id,
                        name=p_name,
                        unit=p_unit,
                        selling_price=p_price,
                        purchase_price=p_price * Decimal("0.8"),
                        current_stock=p_stock,
                        minimum_stock=Decimal("5.00"),
                        is_active=True,
                    ))
                    db.commit()
                else:
                    changed = False
                    if not existing_p.selling_price or existing_p.selling_price <= Decimal("0.00"):
                        existing_p.selling_price = p_price
                        changed = True
                    if not existing_p.current_stock or existing_p.current_stock <= Decimal("0.00"):
                        existing_p.current_stock = p_stock
                        changed = True
                    if changed:
                        db.commit()

            # Ensure sample customers Rahul & Amit exist with WhatsApp numbers
            from app.models.billing import Customer
            for c_name, c_phone in [("Rahul", "9876543210"), ("Amit", "9876543211")]:
                existing_c = db.query(Customer).filter(Customer.business_id == biz.id, Customer.name.ilike(c_name)).first()
                if not existing_c:
                    db.add(Customer(
                        business_id=biz.id,
                        name=c_name,
                        phone=c_phone,
                        outstanding_balance=Decimal("0.00"),
                    ))
                    db.commit()
                    logger.info("Seeded sample customer %s (%s)", c_name, c_phone)
    except Exception as e:
        logger.error(f"Failed to synchronize database tables on startup: {e}", exc_info=True)

    yield
    logger.info("Shutting down Business AI Robot Central Brain...")


def create_application() -> FastAPI:
    """Application factory for FastAPI instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "Central Brain for the Business AI Robot system. "
            "Coordinates physical robot hardware (ESP32), business database, "
            "Gemini conversational AI, and the mobile management application."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # Cross-Origin Resource Sharing (CORS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    # 1. Mount at root level for direct hardware endpoints (/health, /robots/...)
    app.include_router(api_router)
    # 2. Mount under versioned prefix (/api/v1/health, /api/v1/robots/...)
    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["root"])
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "online",
            "docs": "/docs",
            "admin": "/admin",
            "health": "/health",
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled server error at {request.url}: {exc}", exc_info=True)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(exc), "error_type": type(exc).__name__})

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
