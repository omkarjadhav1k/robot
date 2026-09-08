"""Robot V1 Real-Time Non-LLM Conversation Engine Package."""

from app.engine.command_registry import COMMAND_REGISTRY, CommandDefinition, CommandMode, CommandPriority
from app.engine.conversation_engine import ConversationEngine
from app.engine.conversation_state import ConversationStateManager, StateContext
from app.engine.entity_extractor import EntityExtractor, ExtractedEntities
from app.engine.fast_query_engine import FastQueryEngine, FastQueryResult
from app.engine.intent_router import IntentMatch, IntentRouter
from app.engine.response_templates import ResponseTemplates
from app.engine.task_manager import BackgroundTaskManager
from app.engine.websocket_handler import WebSocketSessionHandler

__all__ = [
    "CommandMode",
    "CommandPriority",
    "CommandDefinition",
    "COMMAND_REGISTRY",
    "ExtractedEntities",
    "EntityExtractor",
    "IntentMatch",
    "IntentRouter",
    "ResponseTemplates",
    "FastQueryResult",
    "FastQueryEngine",
    "StateContext",
    "ConversationStateManager",
    "BackgroundTaskManager",
    "ConversationEngine",
    "WebSocketSessionHandler",
]
