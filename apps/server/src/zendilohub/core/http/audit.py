"""
The audit trail of the API. Every route that changes something declares what it does (`audited('member.removed')`)
or that it changes nothing worth recording (`Unaudited`); the kernel refuses routes without either, so no change goes
unrecorded by accident. After the response, `AuditRecorder` publishes what happened as an `ActionPerformed` event.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from fastapi import Depends, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from zendilohub.core.events.integration_events import ActionPerformed

from .access import Principal

if TYPE_CHECKING:
    from .http_kernel import HttpKernel


@dataclass(kw_only=True)
class PendingAudit:
    """An audited request on its way through the app; handlers can add what only they know."""

    action: str
    tenant_id: str | None = None
    target: str | None = None
    actor_id: str | None = None
    actor_email: str | None = None
    """For requests without a session yet, e.g. a login."""
    forget_actor_email: bool = False
    """The actor's account is gone after this request (deleted): record it without the address."""


def audited(action: str, *, target: Callable[[Request], str | None] | None = None) -> Any:
    """Records every request to the route as `action`; `target` names what it acted on (default: none)."""

    async def dependency(request: Request) -> None:
        request.state.audit = PendingAudit(
            action=action,
            tenant_id=request.path_params.get('tenant_id'),
            target=target(request) if target else None,
        )

    dependency.__audited__ = True  # type: ignore[attr-defined]
    return Depends(dependency)


def unaudited() -> None:
    """Marks a state-changing method that changes nothing worth recording (e.g. a preview sent as POST)."""


Unaudited = Depends(unaudited)


def note_audit(
    request: Request,
    *,
    tenant_id: str | None = None,
    target: str | None = None,
    actor_id: str | None = None,
    actor_email: str | None = None,
    forget_actor_email: bool = False,
) -> None:
    """Adds what the handler learned, e.g. the id of what it just created."""
    pending: PendingAudit | None = getattr(request.state, 'audit', None)
    if pending is None:
        return
    pending.tenant_id = tenant_id or pending.tenant_id
    pending.target = target or pending.target
    pending.actor_id = actor_id or pending.actor_id
    pending.actor_email = actor_email or pending.actor_email
    pending.forget_actor_email = forget_actor_email or pending.forget_actor_email


def path_param(name: str) -> Callable[[Request], str | None]:
    return lambda request: request.path_params.get(name)


def declares_audit(call: Any) -> bool:
    return call is unaudited or getattr(call, '__audited__', False)


type AuditSink = Callable[[ActionPerformed], Awaitable[None]]


class AuditRecorder:
    """Publishes the audited requests once they are answered (pure ASGI, so streaming responses keep working)."""

    def __init__(self, app: ASGIApp, kernel: Callable[[], HttpKernel]) -> None:
        self._app = app
        self._kernel = kernel

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self._app(scope, receive, send)
            return
        status = 500

        async def send_and_remember(message: Message) -> None:
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self._app(scope, receive, send_and_remember)
        finally:
            state: dict[str, Any] = scope.get('state', {})
            pending = cast(PendingAudit | None, state.get('audit'))
            if pending is not None:
                principal = cast(Principal | None, state.get('principal'))
                actor_email = principal.email if principal else pending.actor_email
                client = scope.get('client')
                await self._kernel().record(
                    ActionPerformed(
                        action=pending.action,
                        tenant_id=pending.tenant_id,
                        target=pending.target,
                        actor_id=principal.user_id if principal else pending.actor_id,
                        actor_email=None if pending.forget_actor_email else actor_email,
                        succeeded=status < 400,
                        status=status,
                        client=client[0] if client else None,
                    )
                )
