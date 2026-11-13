from dataclasses import dataclass

from .permissions import Permission


@dataclass(frozen=True, kw_only=True)
class AssistantAccess:
    """
    What an AI assistant (Claude, ChatGPT) a member connected may do: act in one organization for them, with what they
    allowed it and never beyond what their role allows them now. The MCP server calls the API in-process with it.
    """

    connection_id: str
    tenant_id: str
    user_id: str
    email: str
    client_name: str
    permissions: frozenset[Permission]
