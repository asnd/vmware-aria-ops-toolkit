"""Error response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information (for validation errors)."""

    loc: list[str] | None = Field(None, description="Location of error in request")
    msg: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error category/type")
    detail: str | list[ErrorDetail] = Field(..., description="Error details")
    request_id: str | None = Field(None, description="Request ID for tracking")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "detail": [
                    {
                        "loc": ["body", "vlan"],
                        "msg": "Invalid VLAN ID",
                        "type": "value_error",
                    }
                ],
                "request_id": "req_abc123",
                "timestamp": "2025-12-27T10:30:45Z",
            }
        }
