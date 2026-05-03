# services.api.routes.admin package
# Admin-only endpoints — all require praxya_admin role.

from services.api.routes.admin.soft_delete import router

__all__ = ["router"]
