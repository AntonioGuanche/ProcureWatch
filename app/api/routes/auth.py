"""Mock JWT auth for Lovable (no real users table yet)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

from app.core.security import create_access_token, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


# --- Request/Response schemas ---


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class LoginResponse(BaseModel):
    access_token: str
    user: UserOut


# --- Helpers ---


def _mock_user_id(email: str) -> str:
    """Generate a stable mock user id from email (no DB)."""
    return f"mock-{email.lower().replace('@', '-at-').replace('.', '-')}"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserOut:
    """Validate Bearer token and return user info. Raises 401 if missing/invalid."""
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    sub = payload.get("sub")
    user_id = payload.get("user_id")
    name = payload.get("name") or sub
    if not sub or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return UserOut(id=user_id, email=sub, name=name)


# --- Endpoints ---


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginBody) -> LoginResponse:
    """
    Mock login: accept any email/password and return a JWT.
    Lovable will handle real auth later.
    """
    user_id = _mock_user_id(body.email)
    name = body.email.split("@")[0].replace(".", " ").title()
    token = create_access_token(sub=body.email, user_id=user_id, name=name)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user_id, email=body.email, name=name),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    """Return current user from JWT (Authorization: Bearer <token>)."""
    return current_user


@router.post("/register", response_model=LoginResponse)
async def register(body: RegisterBody) -> LoginResponse:
    """
    Mock register: create a JWT for the user (no DB yet).
    Lovable will handle real user management later.
    """
    user_id = _mock_user_id(body.email)
    name = (body.name or body.email.split("@")[0]).strip() or body.email
    token = create_access_token(sub=body.email, user_id=user_id, name=name)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user_id, email=body.email, name=name),
    )
