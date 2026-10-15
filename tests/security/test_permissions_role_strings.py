from backend.app.core.permissions import ROLE_PERMISSIONS, permissions_for
from backend.app.models.base import UserRole


def test_permissions_for_accepts_enum_and_membership_strings() -> None:
    assert permissions_for("owner") == ROLE_PERMISSIONS[UserRole.OWNER]
    assert permissions_for(UserRole.OWNER) == ROLE_PERMISSIONS[UserRole.OWNER]
    assert permissions_for("admin") == permissions_for(UserRole.ADMIN)
    assert "ai:use" in permissions_for("user")
