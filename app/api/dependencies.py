from typing import Annotated

from fastapi import Header, HTTPException, status


async def get_placeholder_owner_id(
    x_internal_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """Temporary ownership boundary until authentication is introduced.

    Clients must explicitly provide an internal user identifier; Phase 6 will replace
    this dependency with authenticated identity resolution.
    """
    if not x_internal_user_id or not x_internal_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Internal-User-ID header is required",
        )
    return x_internal_user_id.strip()
