from string import Template

from zendilohub.core.domain.mailer import Mailer, MailMessage

from ..domain.models.registration import Registration
from ..domain.models.user import Locale, User

TEMPLATES: dict[str, dict[Locale, tuple[str, str]]] = {
    'confirm_registration': {
        'en': (
            'Confirm your zendiloHUB account',
            """Hello,

please confirm your e-mail address to activate your zendiloHUB account:

$link

The link is valid for 48 hours. If you did not sign up, just ignore this e-mail; no account will be created.

zendiloHUB""",
        ),
        'de': (
            'Bestätige dein zendiloHUB-Konto',
            """Hallo,

bitte bestätige deine E-Mail-Adresse, um dein zendiloHUB-Konto zu aktivieren:

$link

Der Link ist 48 Stunden gültig. Wenn du dich nicht registriert hast, ignoriere diese E-Mail einfach;
es wird kein Konto angelegt.

zendiloHUB""",
        ),
    },
    'already_registered': {
        'en': (
            'Your zendiloHUB account',
            """Hello,

someone tried to sign up for zendiloHUB with this e-mail address, but you already have an account.
Log in here:

$link

If you forgot your password, use "Forgot password?" on that page. If it was not you, you can ignore this e-mail.

zendiloHUB""",
        ),
        'de': (
            'Dein zendiloHUB-Konto',
            """Hallo,

jemand wollte sich mit dieser E-Mail-Adresse bei zendiloHUB registrieren, du hast aber bereits ein Konto.
Hier kannst du dich anmelden:

$link

Falls du dein Passwort vergessen hast, nutze dort „Passwort vergessen?“. Warst du das nicht, kannst du diese
E-Mail ignorieren.

zendiloHUB""",
        ),
    },
    'reset_password': {
        'en': (
            'Reset your zendiloHUB password',
            """Hello,

you can set a new password for your zendiloHUB account here:

$link

The link is valid for one hour. If you did not ask for it, ignore this e-mail; your password stays the same.

zendiloHUB""",
        ),
        'de': (
            'Setze dein zendiloHUB-Passwort zurück',
            """Hallo,

hier kannst du ein neues Passwort für dein zendiloHUB-Konto festlegen:

$link

Der Link ist eine Stunde gültig. Wenn du das nicht angefordert hast, ignoriere diese E-Mail; dein Passwort
bleibt unverändert.

zendiloHUB""",
        ),
    },
}


class MailAccountNotifier:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def confirm_registration(self, registration: Registration, link: str) -> None:
        await self._send('confirm_registration', registration.email, registration.locale, link)

    async def already_registered(self, user: User, link: str) -> None:
        await self._send('already_registered', user.email, user.locale, link)

    async def reset_password(self, user: User, link: str) -> None:
        await self._send('reset_password', user.email, user.locale, link)

    async def _send(self, template: str, to: str, locale: Locale, link: str) -> None:
        subject, text = TEMPLATES[template][locale]
        await self._mailer.send(MailMessage(to=to, subject=subject, text=Template(text).substitute(link=link)))
