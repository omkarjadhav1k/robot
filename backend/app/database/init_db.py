"""Database schema initialization and seed data generation."""

from decimal import Decimal
import logging
import uuid
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.session import engine, SessionLocal
from app.models import (
    Business,
    Customer,
    Product,
    RobotDevice,
)

logger = logging.getLogger("business_ai_robot.database.init")


def init_database():
    """Create all tables in the configured database and seed initial business data if empty."""
    logger.info("Verifying and creating database tables...")
    Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()
    try:
        # Check if default business already exists
        business = db.query(Business).first()
        if not business:
            logger.info("Seeding initial business tenant, robot, customers, and inventory...")
            business = Business(
                name="Smart Retail Mart",
                business_type="Retail Store",
                owner_name="Store Owner",
                currency="INR",
                working_hours="8:00 AM - 10:00 PM",
            )
            db.add(business)
            db.flush()

            # Attach default robot
            robot = RobotDevice(
                business_id=business.id,
                device_id="ROBOT-001",
                nickname="Counter Robot",
                location="Main Billing Counter",
                is_active=True,
            )
            db.add(robot)

            # Add starter customer
            customer = Customer(
                business_id=business.id,
                name="Ramesh",
                phone="9876543210",
                outstanding_balance=Decimal("0.00"),
            )
            db.add(customer)

            # Add starter products / inventory
            starter_products = [
                Product(
                    business_id=business.id,
                    name="Sugar",
                    unit="kg",
                    purchase_price=Decimal("38.00"),
                    selling_price=Decimal("45.00"),
                    current_stock=Decimal("100.00"),
                    minimum_stock=Decimal("15.00"),
                    is_active=True,
                ),
                Product(
                    business_id=business.id,
                    name="Rice",
                    unit="kg",
                    purchase_price=Decimal("50.00"),
                    selling_price=Decimal("60.00"),
                    current_stock=Decimal("150.00"),
                    minimum_stock=Decimal("20.00"),
                    is_active=True,
                ),
                Product(
                    business_id=business.id,
                    name="Cooking Oil",
                    unit="L",
                    purchase_price=Decimal("120.00"),
                    selling_price=Decimal("140.00"),
                    current_stock=Decimal("40.00"),
                    minimum_stock=Decimal("10.00"),
                    is_active=True,
                ),
                Product(
                    business_id=business.id,
                    name="Tea",
                    unit="pack",
                    purchase_price=Decimal("95.00"),
                    selling_price=Decimal("120.00"),
                    current_stock=Decimal("50.00"),
                    minimum_stock=Decimal("10.00"),
                    is_active=True,
                ),
            ]
            db.add_all(starter_products)
            db.commit()
            logger.info("Database initialized with starter business and inventory data.")
        else:
            logger.info(f"Database already contains business: '{business.name}'")
    except Exception as e:
        logger.error(f"Error during database initialization: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
