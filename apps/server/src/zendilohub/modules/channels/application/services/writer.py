from dataclasses import dataclass

from ...domain.models.templates import render
from ...domain.ports.repositories import PersonalRepository, QueueChannelRepository, TemplateRepository
from ...domain.ports.services import Names


@dataclass(frozen=True, kw_only=True)
class Context:
    """What a text is about: the ticket, its customer and the member writing."""

    tenant_id: str
    queue_id: str
    user_id: str | None = None
    ticket_number: int | None = None
    ticket_subject: str = ''
    customer_name: str = ''
    customer_email: str = ''


class Writer:
    """Fills salutations, signatures and auto replies with their placeholders."""

    def __init__(
        self,
        queues: QueueChannelRepository,
        templates: TemplateRepository,
        personal: PersonalRepository,
        names: Names,
    ) -> None:
        self._queues = queues
        self._templates = templates
        self._personal = personal
        self._names = names

    async def values(self, context: Context) -> dict[str, str]:
        tenant_id = context.tenant_id
        personal = await self._personal.find(tenant_id, context.user_id) if context.user_id else None
        email = await self._names.member_email(tenant_id, context.user_id) if context.user_id else None
        return {
            'agent.name': personal.name if personal and personal.name else (email or '').split('@')[0],
            'agent.title': personal.title if personal else '',
            'agent.email': email or '',
            'agent.signature': personal.signature if personal else '',
            'customer.name': context.customer_name,
            'customer.email': context.customer_email,
            'queue.name': await self._names.queue(tenant_id, context.queue_id) or '',
            'ticket.number': str(context.ticket_number) if context.ticket_number else '',
            'ticket.subject': context.ticket_subject,
            'organization.name': await self._names.organization(tenant_id),
        }

    async def reply_draft(self, context: Context) -> str:
        """Salutation, room for the text, signature: what the composer starts a reply with."""
        settings = await self._queues.find(context.tenant_id, context.queue_id)
        if settings is None:
            return ''
        values = await self.values(context)
        parts: list[str] = []
        for template_id in (settings.salutation_id, settings.signature_id):
            template = await self._templates.find(context.tenant_id, template_id) if template_id else None
            parts.append(render(template.body, values) if template else '')
        salutation, signature = parts
        if not (salutation or signature):
            return ''
        # A free line between them, where the reply goes.
        text = '\n\n'.join([salutation, '', signature]).strip('\n')
        return text if signature else text + '\n\n'

    async def auto_reply(self, context: Context) -> tuple[str, str] | None:
        """Subject and text of the queue's auto reply, if it has one."""
        settings = await self._queues.find(context.tenant_id, context.queue_id)
        if settings is None or not settings.auto_reply:
            return None
        values = await self.values(context)
        return render(settings.auto_reply_subject, values), render(settings.auto_reply_body, values)
