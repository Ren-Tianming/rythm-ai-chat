import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class GenerationControl:
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)


class GenerationControlRegistry:
    def __init__(self) -> None:
        self._controls: dict[uuid.UUID, GenerationControl] = {}

    def register(self, generation_id: uuid.UUID) -> GenerationControl:
        control = GenerationControl()
        self._controls[generation_id] = control
        return control

    def cancel(self, generation_id: uuid.UUID) -> bool:
        control = self._controls.get(generation_id)
        if not control:
            return False
        control.cancelled.set()
        return True

    def remove(self, generation_id: uuid.UUID) -> None:
        self._controls.pop(generation_id, None)


generation_controls = GenerationControlRegistry()
