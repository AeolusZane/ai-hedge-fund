from typing import Dict, Optional, Any, Literal
from pydantic import BaseModel


class BaseEvent(BaseModel):
    """Base class for all Server-Sent Event events"""

    type: str

    def to_sse(self) -> str:
        """Convert to Server-Sent Event format"""
        event_type = self.type.lower()
        return f"event: {event_type}\ndata: {self.model_dump_json()}\n\n"


class StartEvent(BaseEvent):
    """Event indicating the start of processing"""

    type: Literal["start"] = "start"
    timestamp: Optional[str] = None

class ProgressUpdateEvent(BaseEvent):
    """Event containing an agent's progress update.

    `chunk` carries a partial LLM token batch when a streaming stage
    (currently just Analyze) emits incremental output; the frontend
    accumulates these per agent to render the response as it grows.
    """

    type: Literal["progress"] = "progress"
    agent: str
    ticker: Optional[str] = None
    status: str
    timestamp: Optional[str] = None
    analysis: Optional[str] = None
    chunk: Optional[str] = None

class ErrorEvent(BaseEvent):
    """Event indicating an error occurred"""

    type: Literal["error"] = "error"
    message: str
    timestamp: Optional[str] = None


class CompleteEvent(BaseEvent):
    """Event indicating successful completion with results"""

    type: Literal["complete"] = "complete"
    data: Dict[str, Any]
    timestamp: Optional[str] = None
