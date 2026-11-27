"""Provision least-privilege groups; never silently grant a live account access."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.users.account_administration import audit_account, lock_administration
from apps.users.models import User


GROUPS = {
    'OHAYO Admin Read': {'users.view_user', 'users.view_teacherapproval', 'users.view_teacherapprovalevent',
        'users.view_institution', 'users.view_platform_overview', 'admin.view_logentry',
        'ai.view_generationevent', 'documents.view_ingestionjob'},
    'OHAYO Account Manager': {'users.view_user', 'users.add_user', 'users.change_user',
        'users.view_teacherapproval', 'users.change_teacherapproval', 'users.view_teacherapprovalevent',
        'admin.view_logentry'},
    'OHAYO Role Manager': {'users.view_user', 'users.change_user', 'users.assign_user_role'},
    'OHAYO Institution Manager': {'users.view_institution', 'users.add_institution', 'users.change_institution'},
}


class Command(BaseCommand):
    help = 'Create fixed Admin permission groups; optionally grant one to an explicitly named active ADMIN.'

    def add_arguments(self, parser):
        parser.add_argument('--assign')
        parser.add_argument('--group', choices=tuple(GROUPS))
        parser.add_argument('--reason')
        parser.add_argument('--actor')

    @transaction.atomic
    def handle(self, *args, **options):
        lock_administration()
        if bool(options['assign']) != bool(options['group']):
            raise CommandError('--assign and --group must be provided together.')
        if options['assign'] and (not options['reason'] or not options['reason'].strip() or len(options['reason']) > 1000):
            raise CommandError('Provide --reason when assigning a group.')
        actor = None
        if options['assign']:
            actor = User.objects.filter(username=options['actor'], role='ADMIN', status='ACTIVE', is_active=True).first()
            required = GROUPS[options['group']] | {'users.assign_user_role', 'auth.change_group'}
            if actor is None or not all(actor.has_perm(label) for label in required):
                raise CommandError('Provide --actor naming an active ADMIN allowed to delegate every permission in this group.')
        for name, required in GROUPS.items():
            permissions = []
            for label in sorted(required):
                app, codename = label.split('.')
                try:
                    permissions.append(Permission.objects.get(content_type__app_label=app, codename=codename))
                except Permission.DoesNotExist as exc:
                    raise CommandError('Run migrations before provisioning Admin groups.') from exc
            group, _ = Group.objects.get_or_create(name=name)
            # Do not remove permissions from existing groups while they may be in use.
            group.permissions.add(*permissions)
        if options['assign']:
            try:
                user = User.objects.select_for_update().get(username=options['assign'], role='ADMIN', status='ACTIVE', is_active=True)
            except User.DoesNotExist as exc:
                raise CommandError('Assignment requires an existing active ADMIN; no role is promoted by this command.') from exc
            group = Group.objects.get(name=options['group'])
            actual = group.permissions.select_related('content_type')
            if not all(actor.has_perm(permission.content_type.app_label + '.' + permission.codename) for permission in actual):
                raise CommandError('Existing group contains permissions this actor cannot delegate.')
            if not user.groups.filter(pk=group.pk).exists():
                user.groups.add(group)
                audit_account(actor, user, 'OPERATOR_GROUP_GRANTED', options['reason'], {}, ['group:' + group.name])
        self.stdout.write(self.style.SUCCESS('Admin groups ready. No account assignment unless --assign was supplied.'))
