from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    if not credentials.credentials:
        raise HTTPException(status_code=401, detail="Invalid authorization")

    return credentials.credentials