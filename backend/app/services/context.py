from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ContextMessage:
    role: str
    content: str


def select_complete_rounds(
    messages: Iterable[ContextMessage], max_rounds: int = 5
) -> list[ContextMessage]:
    """Return the latest complete user/assistant pairs in chronological order."""
    pairs: list[tuple[ContextMessage, ContextMessage]] = []
    pending_user: ContextMessage | None = None
    for message in messages:
        if message.role == "user":
            pending_user = message
        elif message.role == "assistant" and pending_user is not None:
            pairs.append((pending_user, message))
            pending_user = None
    selected = pairs[-max_rounds:]
    return [message for pair in selected for message in pair]
