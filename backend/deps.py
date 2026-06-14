import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlmodel import Session

from db import get_session
from models import User
from security import decode_access_token

COOKIE_NAME = "access_token"


def get_current_user(
    access_token: str | None = Cookie(default=None),
    session: Session = Depends(get_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )

    if access_token is None:
        raise credentials_exception

    try:
        payload = decode_access_token(access_token)
    except jwt.PyJWTError:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = session.get(User, int(user_id))
    if user is None:
        raise credentials_exception

    return user
