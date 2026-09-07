"""Task extraction, persistence, tracking, and completion service."""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.billing import Customer
from app.models.task import AITask, TaskStatus, TaskType

logger = logging.getLogger("max.task")


class TaskService:
    """Manages persistent AI operational tasks, customer followups, and payment reminders."""

    @classmethod
    def create_task(
        cls,
        db: Session,
        description: str,
        task_type: TaskType = TaskType.CUSTOM,
        customer_name: Optional[str] = None,
        due_at: Optional[datetime] = None,
        priority: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: str = "MAX",
        business_id: Optional[uuid.UUID] = None,
    ) -> AITask:
        """Create and store a persistent task in PostgreSQL."""
        customer_id = None
        if customer_name:
            c = db.query(Customer).filter(Customer.name.ilike(f"%{customer_name.strip()}%")).first()
            if c:
                customer_id = c.id

        task = AITask(
            business_id=business_id,
            task_type=task_type,
            description=description.strip(),
            status=TaskStatus.PENDING,
            priority=priority,
            customer_id=customer_id,
            due_at=due_at,
            created_by=created_by,
            task_metadata=metadata or {},
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info("Created task %s: '%s'", task.id, task.description)
        return task

    @classmethod
    def list_tasks(
        cls,
        db: Session,
        business_id: Optional[uuid.UUID] = None,
        status: Optional[TaskStatus] = TaskStatus.PENDING,
        customer_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """List tasks optionally filtered by status and customer."""
        q = db.query(AITask)
        if business_id:
            q = q.filter(AITask.business_id == business_id)
        if status:
            q = q.filter(AITask.status == status)

        if customer_name:
            q = q.join(Customer, AITask.customer_id == Customer.id).filter(Customer.name.ilike(f"%{customer_name.strip()}%"))

        tasks = q.order_by(AITask.priority.desc(), AITask.created_at.desc()).limit(limit).all()

        results = []
        for t in tasks:
            due_str = t.due_at.strftime("%Y-%m-%d") if t.due_at else "No due date"
            results.append({
                "id": str(t.id),
                "task_type": t.task_type.value,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority,
                "customer_name": t.customer.name if t.customer else None,
                "due_at": due_str,
                "metadata": t.task_metadata,
            })
        return results

    @classmethod
    def complete_task(
        cls,
        db: Session,
        task_id_or_keyword: str,
        business_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Mark a pending task as COMPLETED using ID or keyword match."""
        task: Optional[AITask] = None
        clean = task_id_or_keyword.strip()

        # Try UUID
        try:
            task = db.query(AITask).filter(AITask.id == uuid.UUID(clean)).first()
        except ValueError:
            pass

        # Try keyword match on description or customer name
        if not task:
            q = db.query(AITask).filter(AITask.status == TaskStatus.PENDING)
            if business_id:
                q = q.filter(AITask.business_id == business_id)
            task = q.filter(AITask.description.ilike(f"%{clean}%")).first()

        if not task:
            return {
                "success": False,
                "message": f"Matching pending task for '{clean}' nahi mila.",
            }

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)

        return {
            "success": True,
            "task_id": str(task.id),
            "description": task.description,
            "message": f"Done. Task '{task.description}' complete mark kar diya gaya hai.",
        }

    @classmethod
    def extract_and_create_task(
        cls,
        db: Session,
        prompt: str,
        business_id: Optional[uuid.UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract structured task details from natural phrasing like:
        'Ramesh ka ₹500 baki hai, kal usko yaad dila dena'
        """
        lower = prompt.lower()
        reminder_keywords = ["yaad dila", "remind", "yaad rakhna", "task", "follow up", "call karna"]
        if not any(k in lower for k in reminder_keywords):
            return None

        # Determine task type
        task_type = TaskType.CUSTOM
        if any(w in lower for w in ["baki", "payment", "rupaye", "rs", "₹", "paise"]):
            task_type = TaskType.PAYMENT_REMINDER
        elif any(w in lower for w in ["stock", "maal", "inventory"]):
            task_type = TaskType.STOCK_REMINDER
        elif any(w in lower for w in ["customer", "call"]):
            task_type = TaskType.CUSTOMER_FOLLOWUP

        # Extract amount if present
        amount = None
        amt_match = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d{1,2})?)\s*(?:rupaye|rs|₹|baki)?", prompt, re.IGNORECASE)
        if amt_match:
            try:
                amount = float(amt_match.group(1))
            except Exception:
                pass

        # Extract due date
        now = datetime.now(timezone.utc)
        due_at = None
        if "kal" in lower or "tomorrow" in lower:
            due_at = now + timedelta(days=1)
        elif "parso" in lower:
            due_at = now + timedelta(days=2)
        elif "aaj" in lower or "today" in lower:
            due_at = now

        # Extract customer name
        customer_name = None
        # Check against existing customers in DB
        customers = db.query(Customer).all()
        for c in customers:
            if c.name.lower() in lower:
                customer_name = c.name
                break

        # Fallback regex for "X ka ... yaad dila dena"
        if not customer_name:
            m = re.search(r"\b([A-Z][a-z]+)\s+ka\b", prompt)
            if m:
                customer_name = m.group(1)

        task = cls.create_task(
            db=db,
            description=prompt.strip(),
            task_type=task_type,
            customer_name=customer_name,
            due_at=due_at,
            metadata={"amount": amount, "customer_name": customer_name} if (amount or customer_name) else None,
            business_id=business_id,
        )

        due_label = "kal" if "kal" in lower else (due_at.strftime("%d %b") if due_at else "")
        cust_label = f"{customer_name} ke liye " if customer_name else ""
        return {
            "task_id": str(task.id),
            "task_type": task.task_type.value,
            "description": task.description,
            "customer_name": customer_name,
            "amount": amount,
            "due_at": str(due_at) if due_at else None,
            "message": f"Done. {cust_label}Reminder task add kar diya hai ({due_label}).",
        }
