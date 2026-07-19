"""User business logic."""

from fastapi import HTTPException, status

from app.repositories.set_repository import SetRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import RoleOption, RoleResult, UserProfile, UserSummary


class UserService:
    def __init__(self, repo: UserRepository, set_repo: SetRepository) -> None:
        self.repo = repo
        self.sets = set_repo

    def list_users(self) -> list[UserSummary]:
        """The "All users" table (was ``index`` / users.j2)."""
        return [
            UserSummary(
                name=r._mapping["name"],
                did=r._mapping["did"],
                card_count=r._mapping["card_count"],
                collection_value=r._mapping["collection_value"],
                gp=r._mapping["gp"],
                last_active=r._mapping["last_active"],
            )
            for r in self.repo.list_with_stats()
        ]

    def get_profile(self, did: int) -> UserProfile:
        """Header for a user's collection page (was ``getUserName``)."""
        user = self.repo.get_by_did(did)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
        role = self.sets.role_string(user.roleid) if user.roleid is not None else None
        return UserProfile(
            did=str(did), name=user.name, gp=user.gp, roleid=user.roleid, role=role
        )

    # ── Roles ────────────────────────────────────────────────────────────────
    def role_options(self, did: int) -> list[RoleOption]:
        """Sets the user has completed — the roles they may choose from."""
        return [
            RoleOption(rwid=r._mapping["rwid"], name=r._mapping["name"], role=r._mapping["role"])
            for r in self.sets.completed_sets(did)
        ]

    def set_role(self, did: int, roleid: int | None) -> RoleResult:
        """Set or clear (``roleid=None``) the user's role.

        A non-null ``roleid`` must be one of the user's completed sets, otherwise
        a 400 is raised — you cannot display a role you have not earned.
        """
        user = self.repo.get_by_did(did)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

        if roleid is not None:
            completed = {r._mapping["rwid"] for r in self.sets.completed_sets(did)}
            if roleid not in completed:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="You can only select a role from a set you have completed",
                )

        self.repo.set_role(user.rwid, roleid)
        role = self.sets.role_string(roleid) if roleid is not None else None
        return RoleResult(roleid=roleid, role=role)
