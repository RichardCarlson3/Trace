"""Bounded, stateless continuation state for a single seed's neighbor traversal."""

import base64
import binascii
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ServiceError

Direction = Literal["incoming", "outgoing", "both"]


class NeighborCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = 1
    work_id: str
    direction: Direction
    limit: int = Field(ge=1, le=50)
    outgoing_offset: int | None = Field(default=None, ge=0)
    incoming_cursor: str | None = Field(
        default=None, min_length=1, max_length=2048, pattern=r"^\S+$"
    )
    turn: Literal["incoming", "outgoing"] = "outgoing"

    def encode(self) -> str:
        return base64.urlsafe_b64encode(self.model_dump_json().encode()).decode().rstrip("=")

    @classmethod
    def start_or_decode(
        cls, cursor: str, *, work_id: str, direction: Direction, limit: int
    ) -> "NeighborCursor":
        if cursor == "*":
            return cls(
                work_id=work_id,
                direction=direction,
                limit=limit,
                outgoing_offset=0 if direction != "incoming" else None,
                incoming_cursor="*" if direction != "outgoing" else None,
            )
        try:
            if not cursor or len(cursor) > 8192:
                raise ValueError("Invalid cursor length")
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            state = cls.model_validate_json(raw)
            if (state.work_id, state.direction, state.limit) != (work_id, direction, limit):
                raise ValueError("Cursor belongs to a different query")
            if direction == "incoming" and state.outgoing_offset is not None:
                raise ValueError("Unexpected outgoing state")
            if direction == "outgoing" and state.incoming_cursor is not None:
                raise ValueError("Unexpected incoming state")
            if state.outgoing_offset is None and state.incoming_cursor is None:
                raise ValueError("Cursor is already exhausted")
            return state
        except (ValueError, binascii.Error):
            raise ServiceError(
                422,
                "invalid_cursor",
                "Invalid neighbors cursor; keep the same paper, direction, and limit",
            ) from None
