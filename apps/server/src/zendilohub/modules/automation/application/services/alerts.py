import logging

from zendilohub.core.domain.automation import TicketFacts
from zendilohub.core.domain.mailer import Mailer, MailMessage
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

from ...domain.models.rules import Rule
from ...domain.ports.repositories import Tickets

logger = logging.getLogger(__name__)

ALERTS_PER_TENANT = RateLimit('automation-alerts', limit=500, window_seconds=60 * 60)
"""A rule that fires over and over (or a flood of e-mails) must not flood the alert inboxes."""


class AlertMailer:
    """Sends a rule's alert (`notify_emails`) about a ticket: who should look, what it is and where to find it."""

    def __init__(self, mailer: Mailer, tickets: Tickets, limiter: RateLimiter, link_base: str) -> None:
        self._mailer = mailer
        self._tickets = tickets
        self._limiter = limiter
        self._link_base = link_base.rstrip('/')

    async def send(self, rule: Rule, facts: TicketFacts) -> int:
        """Returns how many alerts went out."""
        addresses = rule.actions.notify_emails
        if not addresses:
            return 0
        queue = await self._tickets.queue_name(rule.tenant_id, facts.queue_id) or ''
        excerpt = await self._tickets.excerpt(rule.tenant_id, facts.id)
        subject = f'[#{facts.number}] {facts.subject}'
        lines = [
            *([rule.actions.notify_text, ''] if rule.actions.notify_text else []),
            f'#{facts.number} {facts.subject}',
            f'Queue: {queue}',
            f'Priority: {facts.priority}',
            f'State: {facts.state}',
            *([f'Customer: {facts.customer_email}'] if facts.customer_email else []),
            *(['', excerpt] if excerpt else []),
            '',
            f'{self._link_base}/t/{rule.tenant_id}/tickets/{facts.id}',
            '',
            f'Sent by the rule "{rule.name}" of zendiloHUB.',
        ]
        sent = 0
        for address in addresses:
            if not (await self._limiter.hit(ALERTS_PER_TENANT, rule.tenant_id)).allowed:
                logger.warning('Too many alerts; this one is not sent', extra={'rule': rule.id, 'to': address})
                break
            await self._mailer.send(MailMessage(to=address, subject=subject, text='\n'.join(lines) + '\n'))
            sent += 1
        return sent
