"""Request-local deadline shared across provider calls and tool boundaries.

Synchronous tools cannot be preempted; expiry prevents starting further work
and rejects late results. Provider calls receive only the remaining time.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

from app.ai.errors import OpenAITimeoutError

_deadline: ContextVar[float | None] = ContextVar("ai_deadline", default=None)


class AssistantDeadlineExceeded(OpenAITimeoutError):
    code = "deadline_exceeded"


@contextmanager
def execution_budget(seconds: float):
    token = _deadline.set(monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining_seconds(default: float) -> float:
    deadline = _deadline.get()
    remaining = default if deadline is None else min(default, deadline - monotonic())
    if remaining <= 0:
        raise AssistantDeadlineExceeded("Assistant execution deadline exceeded.")
    return remaining
