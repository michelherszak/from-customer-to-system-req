from __future__ import annotations
from fastapi import HTTPException


def check_expected_version(entity, expected_version: int) -> None:
    current = getattr(entity, "lock_version", None)
    if current is None:
        return
    if current != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "optimistic_lock_conflict",
                "expected_version": expected_version,
                "current_version": current,
            },
        )


def bump_version(entity) -> None:
    if hasattr(entity, "lock_version"):
        entity.lock_version += 1
