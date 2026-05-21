from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class ProcessingStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [item.value for item in enum_class]
