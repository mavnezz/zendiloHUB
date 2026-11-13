from dataclasses import dataclass
from datetime import datetime, timedelta

from zendilohub.core.domain.permissions import TenantRole

INVITATION_LIFETIME = timedelta(days=7)


@dataclass(frozen=True, kw_only=True)
class Invitation:
    """
    An invitation to join a tenant, sent by e-mail. Only the account with the invited address can accept it,
    so a forwarded link is useless. `token_hash` is the one-way hash of the token in the link.
    """

    id: str
    tenant_id: str
    email: str
    role: TenantRole
    token_hash: str
    invited_by: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def send(
        cls, *, id: str, tenant_id: str, email: str, role: TenantRole, token_hash: str, invited_by: str, now: datetime
    ) -> Invitation:
        return cls(
            id=id,
            tenant_id=tenant_id,
            email=email,
            role=role,
            token_hash=token_hash,
            invited_by=invited_by,
            created_at=now,
            expires_at=now + INVITATION_LIFETIME,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
