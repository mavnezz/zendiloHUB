from string import Template

from zendilohub.core.domain.mailer import Mailer, MailMessage

from ..domain.models.invitation import INVITATION_LIFETIME, Invitation
from ..domain.models.tenant import Locale, Tenant

ROLE_NAMES: dict[Locale, dict[str, str]] = {
    'en': {'owner': 'owner', 'admin': 'administrator', 'manager': 'manager', 'agent': 'agent'},
    'de': {'owner': 'Inhaber', 'admin': 'Administrator', 'manager': 'Manager', 'agent': 'Mitarbeiter'},
}

TEMPLATES: dict[Locale, tuple[str, str]] = {
    'en': (
        'Join $tenant on zendiloHUB',
        """Hello,

$inviter invites you to join $tenant on zendiloHUB as $role:

$link

Log in or sign up with this e-mail address ($email) to accept. The invitation is valid for $days days.
If you do not want to join, just ignore this e-mail.

zendiloHUB""",
    ),
    'de': (
        'Einladung zu $tenant bei zendiloHUB',
        """Hallo,

$inviter lädt dich ein, $tenant bei zendiloHUB als $role beizutreten:

$link

Melde dich mit dieser E-Mail-Adresse ($email) an oder registriere dich, um die Einladung anzunehmen.
Sie ist $days Tage gültig. Wenn du nicht beitreten möchtest, ignoriere diese E-Mail einfach.

zendiloHUB""",
    ),
}


class MailInvitationNotifier:
    """Invitations go out in the organization's language."""

    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def invite(
        self, invitation: Invitation, tenant: Tenant, *, inviter: str, link: str, role_name: str | None = None
    ) -> None:
        subject, text = TEMPLATES[tenant.locale]
        values = {
            'tenant': tenant.name,
            'inviter': inviter,
            'role': role_name or ROLE_NAMES[tenant.locale].get(invitation.role, invitation.role),
            'link': link,
            'email': invitation.email,
            'days': INVITATION_LIFETIME.days,
        }
        await self._mailer.send(
            MailMessage(
                to=invitation.email,
                subject=Template(subject).substitute(values),
                text=Template(text).substitute(values),
            )
        )
