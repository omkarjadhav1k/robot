"""Dynamic AI Memory service for contextual preferences and operating habits."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.ai_memory import AIMemory

logger = logging.getLogger("max.memory")


class MemoryService:
    """Manages separate, non-authoritative contextual memory for MAX."""

    @classmethod
    def store_memory(
        cls,
        db: Session,
        business_id: Optional[uuid.UUID],
        content: str,
        memory_type: str = "BUSINESS_PREFERENCE",
        importance: int = 5,
        source: str = "CONVERSATION",
        expires_at: Optional[datetime] = None,
    ) -> AIMemory:
        """Store a contextual preference or fact. NEVER overrules database truth."""
        mem = AIMemory(
            business_id=business_id,
            memory_type=memory_type.upper(),
            content=content.strip(),
            importance=max(1, min(10, importance)),
            source=source,
            expires_at=expires_at,
        )
        db.add(mem)
        db.commit()
        db.refresh(mem)
        logger.info("Stored AI memory [%s]: '%s'", mem.memory_type, mem.content)
        return mem

    @classmethod
    def get_relevant_memories(
        cls,
        db: Session,
        business_id: Optional[uuid.UUID] = None,
        query_text: str = "",
        limit: int = 4,
    ) -> List[str]:
        """
        Retrieve relevant active memories matching query context keywords.
        Returns concise strings formatted for AI system context.
        """
        now = datetime.now(timezone.utc)
        q = db.query(AIMemory).filter(
            (AIMemory.expires_at.is_(None)) | (AIMemory.expires_at > now)
        )
        if business_id:
            q = q.filter(AIMemory.business_id == business_id)

        all_mems = q.order_by(AIMemory.importance.desc(), AIMemory.created_at.desc()).limit(30).all()
        if not all_mems:
            return []

        # Simple keyword relevance scoring
        words = set(query_text.lower().split()) if query_text else set()

        scored = []
        for m in all_mems:
            content_lower = m.content.lower()
            score = m.importance
            if words:
                matches = sum(1 for w in words if len(w) > 2 and w in content_lower)
                score += matches * 3
            scored.append((score, m.content))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    @classmethod
    def list_memories(
        cls,
        db: Session,
        business_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List all stored memories for the admin dashboard."""
        q = db.query(AIMemory)
        if business_id:
            q = q.filter(AIMemory.business_id == business_id)
        mems = q.order_by(AIMemory.importance.desc(), AIMemory.created_at.desc()).limit(limit).all()

        return [
            {
                "id": str(m.id),
                "memory_type": m.memory_type,
                "content": m.content,
                "importance": m.importance,
                "source": m.source,
                "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else None,
            }
            for m in mems
        ]

    @classmethod
    def delete_memory(cls, db: Session, memory_id: uuid.UUID, business_id: Optional[uuid.UUID] = None) -> bool:
        """Delete a memory item."""
        q = db.query(AIMemory).filter(AIMemory.id == memory_id)
        if business_id:
            q = q.filter(AIMemory.business_id == business_id)
        mem = q.first()
        if mem:
            db.delete(mem)
            db.commit()
            return True
        return False
