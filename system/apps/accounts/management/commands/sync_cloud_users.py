from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from apps.accounts.models import Role, UserRole


class Command(BaseCommand):
    help = "Synchronize Django users and role codes from the cloud DB to local DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            action="append",
            dest="usernames",
            help="Synchronize only this username. Repeat for multiple users.",
        )

    def handle(self, *args, **options):
        if "cloud" not in connections.databases:
            raise CommandError(
                "Cloud database is not configured. Set SUPABASE_DATABASE_URL first."
            )

        User = get_user_model()
        cloud_users = User.objects.using("cloud").all().order_by("id")
        usernames = options.get("usernames") or []
        if usernames:
            cloud_users = cloud_users.filter(username__in=usernames)

        source_users = list(cloud_users)
        if usernames:
            found = {user.username for user in source_users}
            missing = sorted(set(usernames) - found)
            if missing:
                raise CommandError(
                    "Users not found in cloud DB: " + ", ".join(missing)
                )

        synced = 0
        with transaction.atomic(using="default"):
            for source in source_users:
                defaults = {
                    "password": source.password,
                    "email": source.email,
                    "first_name": source.first_name,
                    "last_name": source.last_name,
                    "full_name": source.full_name,
                    "job_title": source.job_title,
                    "is_active": source.is_active,
                    "is_staff": source.is_staff,
                    "is_superuser": source.is_superuser,
                    "is_demo": source.is_demo,
                    "last_login": source.last_login,
                    "date_joined": source.date_joined,
                }
                target, _ = User.objects.using("default").update_or_create(
                    username=source.username,
                    defaults=defaults,
                )

                role_codes = list(
                    UserRole.objects.using("cloud")
                    .filter(user_id=source.pk)
                    .values_list("role__code", flat=True)
                )
                local_roles = list(Role.objects.using("default").filter(
                    code__in=role_codes
                ))
                UserRole.objects.using("default").filter(user=target).delete()
                UserRole.objects.using("default").bulk_create([
                    UserRole(user=target, role=role)
                    for role in local_roles
                ])
                synced += 1
                self.stdout.write(
                    f"Synchronized {source.username} ({len(local_roles)} roles)."
                )

        self.stdout.write(self.style.SUCCESS(
            f"Cloud-to-local user synchronization completed: {synced} user(s)."
        ))
