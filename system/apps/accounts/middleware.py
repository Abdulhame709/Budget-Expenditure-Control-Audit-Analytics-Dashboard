"""Page-level access control middleware.

Enforces URL_PERMISSIONS for every request — including users who type a URL
directly into the browser (not only users clicking navigation links).

- anonymous          → redirect to login (with ?next=)
- logged-in, no perm → 403 (renders templates/403.html)
- unmapped URL       → passes through (public by policy: home, login, static)
"""
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from apps.accounts.permissions import PERMISSIONS, URL_PERMISSIONS, has_perm


class AccessControlMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        if match is None:
            return None
        required = URL_PERMISSIONS.get(match.view_name)
        if not required:
            return None
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not has_perm(request.user, required):
            label = PERMISSIONS.get(required, ("", required))[1]
            raise PermissionDenied(
                f"الوصول مرفوض: هذه الصفحة تتطلب صلاحية «{required}» — {label}"
            )
        return None
