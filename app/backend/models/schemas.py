from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class FlowRunStatus(str, Enum):
    IDLE = "IDLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class ErrorResponse(BaseModel):
    message: str
    error: str | None = None


# Flow-related schemas
class FlowCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    viewport: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    is_template: bool = False
    tags: Optional[List[str]] = None
    domain: Optional[str] = Field(
        default=None,
        description="DomainPack id that owns this flow (e.g. finance, bug_fix)",
    )


class FlowUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    viewport: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    is_template: Optional[bool] = None
    tags: Optional[List[str]] = None


class FlowResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    viewport: Optional[Dict[str, Any]]
    data: Optional[Dict[str, Any]]
    is_template: bool
    tags: Optional[List[str]]
    domain: str = "finance"
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class FlowSummaryResponse(BaseModel):
    """Lightweight flow response without nodes/edges for listing"""
    id: int
    name: str
    description: Optional[str]
    is_template: bool
    tags: Optional[List[str]]
    domain: str = "finance"
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Flow Run schemas
class FlowRunCreateRequest(BaseModel):
    """Request to create a new flow run"""
    request_data: Optional[Dict[str, Any]] = None


class FlowRunUpdateRequest(BaseModel):
    """Request to update an existing flow run"""
    status: Optional[FlowRunStatus] = None
    results: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class FlowRunResponse(BaseModel):
    """Complete flow run response"""
    id: int
    flow_id: int
    status: FlowRunStatus
    run_number: int
    created_at: datetime
    updated_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    request_data: Optional[Dict[str, Any]]
    results: Optional[Dict[str, Any]]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class FlowRunSummaryResponse(BaseModel):
    """Lightweight flow run response for listing"""
    id: int
    flow_id: int
    status: FlowRunStatus
    run_number: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

    class Config:
        from_attributes = True


# API Key schemas
class ApiKeyCreateRequest(BaseModel):
    """Request to create or update an API key"""
    provider: str = Field(..., min_length=1, max_length=100)
    key_value: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_active: bool = True


class ApiKeyUpdateRequest(BaseModel):
    """Request to update an existing API key"""
    key_value: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    """Complete API key response"""
    id: int
    provider: str
    key_value: str
    is_active: bool
    description: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    last_used: Optional[datetime]

    class Config:
        from_attributes = True


class ApiKeySummaryResponse(BaseModel):
    """API key response without the actual key value"""
    id: int
    provider: str
    is_active: bool
    description: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    last_used: Optional[datetime]
    has_key: bool = True  # Indicates if a key is set

    class Config:
        from_attributes = True


class ApiKeyBulkUpdateRequest(BaseModel):
    """Request to update multiple API keys at once"""
    api_keys: List[ApiKeyCreateRequest]
