from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Actor:
    """Who acts: a member (with their name for the history) or an API key; `all_queues` is `queues.all`."""

    user_id: str
    name: str
    all_queues: bool = False
    person: bool = True
    """False for API keys: they have no groups, only `queues.all`."""


SYSTEM = Actor(user_id='', name='zendiloHUB', person=False)
"""Scheduled jobs (closing pending tickets)."""
