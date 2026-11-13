from uuid import uuid7


class UuidGenerator:
    """UUIDv7: unique and sortable by creation time, which keeps database indexes compact."""

    def new_id(self) -> str:
        return str(uuid7())


uuid_generator = UuidGenerator()
