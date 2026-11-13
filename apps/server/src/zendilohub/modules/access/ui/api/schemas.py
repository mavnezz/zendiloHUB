from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from zendilohub.core.domain.queue_rights import QUEUE_RIGHTS, QueueRight, RightsPreset, ordered, preset_of

from ...application.queries.access import QueueWithRights
from ...domain.models.grant import Grant
from ...domain.models.group import Group


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class QueueRequest(Request):
    name: str = Field(max_length=200)
    description: str = Field(default='', max_length=2000)


class GroupRequest(Request):
    name: str = Field(max_length=200)
    description: str = Field(default='', max_length=2000)


class GroupMembersRequest(Request):
    user_ids: list[str] = Field(max_length=1000)


class QueueRightsRequest(Request):
    group_id: str = Field(max_length=64)
    queue_id: str = Field(max_length=64)
    rights: list[QueueRight] = Field(max_length=len(QUEUE_RIGHTS))
    """Empty takes the group's rights in the queue away."""


class QueueResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    rights: list[QueueRight]
    """What the caller may do in it."""

    @classmethod
    def of(cls, item: QueueWithRights) -> QueueResponse:
        queue = item.queue
        return cls(
            id=queue.id,
            name=queue.name,
            description=queue.description,
            created_at=queue.created_at,
            rights=list(ordered(item.rights)),
        )


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str
    member_ids: list[str]
    created_at: datetime

    @classmethod
    def of(cls, group: Group) -> GroupResponse:
        return cls(
            id=group.id,
            name=group.name,
            description=group.description,
            member_ids=sorted(group.member_ids),
            created_at=group.created_at,
        )


class GrantResponse(BaseModel):
    group_id: str
    queue_id: str
    rights: list[QueueRight]
    preset: RightsPreset | None
    """`read`, `contribute`, `work` or `full` when the rights are exactly one of these levels."""

    @classmethod
    def of(cls, grant: Grant) -> GrantResponse:
        return cls(
            group_id=grant.group_id, queue_id=grant.queue_id, rights=list(grant.rights), preset=preset_of(grant.rights)
        )


class RightsMatrixResponse(BaseModel):
    rights: list[QueueRight]
    """Every right, in order."""
    presets: dict[RightsPreset, list[QueueRight]]
    grants: list[GrantResponse]

    @classmethod
    def of(
        cls, grants: Sequence[Grant], presets: Mapping[RightsPreset, tuple[QueueRight, ...]]
    ) -> RightsMatrixResponse:
        return cls(
            rights=list(QUEUE_RIGHTS),
            presets={name: list(rights) for name, rights in presets.items()},
            grants=[GrantResponse.of(grant) for grant in grants],
        )
