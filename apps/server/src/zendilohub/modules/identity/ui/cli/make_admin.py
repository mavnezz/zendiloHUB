from collections.abc import Sequence

from zendilohub.core.bus.command_bus import CommandBus
from zendilohub.core.module import CliOutput

from ...application.commands.change_role import MakeAdmin


class MakeAdminCommand:
    usage = 'make-admin <email>'
    description = 'Makes an existing user an administrator'

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    async def run(self, args: Sequence[str], output: CliOutput) -> int:
        if len(args) != 1:
            output.error(f'Usage: zendilohub {self.usage}')
            return 1
        user = await self._bus.execute(MakeAdmin(args[0]))
        output.line(f'{user.email} is an administrator now.')
        return 0
