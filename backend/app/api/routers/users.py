"""Users router.

  GET /api/users           -> all users table        (was ``/satchemon/``)
  GET /api/users/{did}     -> a user's profile header (was ``/satchemon/user/<did>``)
  GET /api/me              -> the caller's profile    (was ``/satchemon/mycards``)
  GET /api/me/roles        -> roles the caller may pick (their completed sets)
  PUT /api/me/role         -> set/clear the caller's role
"""

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentDid
from app.api.dependencies.services import UserServiceDep
from app.schemas.user import RoleOption, RoleResult, RoleUpdate, UserProfile, UserSummary

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserSummary], summary="List all users")
def list_users(service: UserServiceDep) -> list[UserSummary]:
    return service.list_users()


@router.get("/users/{did}", response_model=UserProfile, summary="Get a user profile")
def get_user(did: int, service: UserServiceDep) -> UserProfile:
    return service.get_profile(did)


@router.get("/me", response_model=UserProfile, summary="Get the current user's profile")
def get_me(did: CurrentDid, service: UserServiceDep) -> UserProfile:
    return service.get_profile(did)


@router.get("/me/roles", response_model=list[RoleOption], summary="Roles the caller may select")
def my_roles(did: CurrentDid, service: UserServiceDep) -> list[RoleOption]:
    return service.role_options(did)


@router.put("/me/role", response_model=RoleResult, summary="Set or clear the caller's role")
def set_my_role(body: RoleUpdate, did: CurrentDid, service: UserServiceDep) -> RoleResult:
    return service.set_role(did, body.roleid)
