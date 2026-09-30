"""accounts views: login/logout · profile · user management · roles overview.

Page-level access: enforced by AccessControlMiddleware (URL_PERMISSIONS).
Action-level access: @require_permission (defense in depth on every view).
"""
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.forms import LoginForm, UserCreateForm, UserEditForm
from apps.accounts.models import Role, UserRole
from apps.accounts.permissions import require_permission, user_permission_codes
from apps.accounts.services import create_user, update_user
from apps.governance.services import log_action, log_login_failure

User = get_user_model()


def _safe_next(raw: str) -> str:
    """Allow local redirects only (open-redirect guard)."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "home"


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    next_url = request.GET.get("next", "")
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            if user is not None:
                login(request, user)
                log_action(
                    action="login",
                    entity_type="user",
                    entity_id=user.pk,
                    request=request,
                    actor=user,
                )
                return redirect(_safe_next(request.POST.get("next", next_url)))
            log_login_failure(form.cleaned_data["username"], request=request)
            form.add_error(None, "اسم المستخدم أو كلمة المرور غير صحيحة.")
    else:
        form = LoginForm()
    return render(
        request, "accounts/login.html",
        {"form": form, "next": next_url},
    )


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        log_action(
            action="logout",
            entity_type="user",
            entity_id=request.user.pk,
            request=request,
        )
        logout(request)
        messages.success(request, "تم تسجيل الخروج بأمان.")
    return redirect("home")


@login_required
def profile(request):
    """Own profile — object-level read: users only see their own record."""
    user = request.user
    roles = list(user.role_links.select_related("role"))
    return render(
        request,
        "accounts/profile.html",
        {
            "page_user": user,
            "roles": roles,
            "codes": sorted(user_permission_codes(user)),
        },
    )


@require_permission("users.manage")
def users_list(request):
    users = User.objects.prefetch_related("role_links__role").order_by("username")
    return render(request, "accounts/users_list.html", {"users": users})


@require_permission("users.manage")
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            try:
                user = create_user(
                    actor=request.user,
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password1"],
                    full_name=form.cleaned_data.get("full_name", ""),
                    job_title=form.cleaned_data.get("job_title", ""),
                    role_codes=[r.code for r in form.cleaned_data["roles"]],
                    is_demo=form.cleaned_data.get("is_demo", False),
                    request=request,
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
            else:
                messages.success(request, f"تم إنشاء المستخدم «{user.username}» وتسجيل العملية في سجل التدقيق.")
                return redirect("accounts:user_detail", pk=user.pk)
    else:
        form = UserCreateForm()
    return render(request, "accounts/user_create.html", {"form": form})


@require_permission("users.manage")
def user_detail(request, pk):
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=target)
        if form.is_valid():
            try:
                update_user(
                    actor=request.user,
                    target=target,
                    full_name=form.cleaned_data["full_name"],
                    job_title=form.cleaned_data["job_title"],
                    is_active=form.cleaned_data["is_active"],
                    is_demo=form.cleaned_data["is_demo"],
                    role_codes=[r.code for r in form.cleaned_data["roles"]],
                    request=request,
                )
            except PermissionDenied as exc:
                raise exc  # → 403 page (object-level rule)
            else:
                messages.success(request, "تم حفظ التغييرات وتسجيلها في سجل التدقيق.")
                return redirect("accounts:user_detail", pk=target.pk)
    else:
        form = UserEditForm(instance=target)
    return render(
        request,
        "accounts/user_detail.html",
        {
            "form": form,
            "page_user": target,
            "current_roles": list(target.role_links.select_related("role")),
        },
    )


@require_permission("roles.manage")
def roles_list(request):
    roles = Role.objects.prefetch_related(
        "role_permissions__permission"
    ).order_by("code")
    return render(request, "accounts/roles_list.html", {"roles": roles})
