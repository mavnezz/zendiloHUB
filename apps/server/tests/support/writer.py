from zendilohub.modules.tickets.domain.exceptions import AssistantFailedError
from zendilohub.modules.tickets.domain.models.assist import AssistInput


class FakeWriter:
    """Stands in for Claude: remembers what it was asked and answers with a canned text."""

    def __init__(self) -> None:
        self.enabled = True
        self.asked: list[AssistInput] = []
        self.answer = 'Draft text.'
        self.failure: str | None = None

    async def write(self, request: AssistInput) -> str:
        self.asked.append(request)
        if self.failure:
            raise AssistantFailedError(self.failure)
        return self.answer
