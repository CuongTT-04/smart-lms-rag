from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import Group

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import Institution, StudentProfile, TeacherApproval, TeacherApprovalEvent, TeacherProfile, User
from .institutions import require_catalog_admin, save_institution


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User

    list_display = ("username", "email", "full_name", "role", "status", "is_staff")
    list_filter = ("role", "status", "is_staff", "is_superuser")
    search_fields = ("username", "email", "full_name")
    readonly_fields = ("role", "date_joined", "last_login", "updated_at")

    # Privileged writes are available only through the audited, password-confirmed API.
    # Disabling the older form prevents a second path around last-admin safeguards.
    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        from .account_administration import require_account_admin
        try:
            require_account_admin(request.user, 'view_user')
            return True
        except PermissionError:
            return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields if field.name != 'password') + ('groups', 'user_permissions')

    def user_change_password(self, request, id, form_url=''):
        raise PermissionDenied('Use the account recovery or audited administration workflow.')

    fieldsets = (
        (None, {"fields": ("username",)}),
        ("Profile", {"fields": ("full_name", "email", "avatar_url", "phone")}),
        ("Account", {"fields": ("role", "status")}),
        (
            "Permissions",
            {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("date_joined", "last_login", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username", "email", "full_name", "avatar_url", "phone", "status",
                    "password1", "password2",
                ),
            },
        ),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
    readonly_fields = ("id", "user", "created_at", "updated_at")
    search_fields = ("user__username", "user__full_name")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TeacherProfile)
class TeacherProfileAdmin(StudentProfileAdmin):
    list_display = ("user", "specialization", 'approval_status', "updated_at")
    readonly_fields = StudentProfileAdmin.readonly_fields + ('institution', 'institution_other_name', 'approval_status')

    @admin.display(description='Teacher approval')
    def approval_status(self, obj):
        approval = getattr(obj, 'approval', None)
        return f'{approval.status} / {approval.source or "-"}' if approval else '-'


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = '__all__'

    def clean(self):
        values = super().clean()
        if not self.errors:
            from .institutions import FIELDS, prepare_institution
            try:
                prepare_institution({field: values[field] for field in FIELDS if field in values},
                                    self.instance if not self.instance._state.adding else None)
            except ValidationError as exc:
                if hasattr(exc, 'message_dict'):
                    for field, messages in exc.message_dict.items():
                        self.add_error(field if field in self.fields else None, messages)
                else:
                    self.add_error(None, exc.messages)
        return values


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    form = InstitutionForm
    list_display = ('name', 'province', 'campus', 'active', 'source_checked_at')
    list_filter = ('active', 'province')
    search_fields = ('search_text',)
    readonly_fields = ('id', 'created_at', 'updated_at')

    def _allowed(self, request, action):
        try:
            require_catalog_admin(request.user, action)
            return True
        except PermissionError:
            return False

    def has_view_permission(self, request, obj=None):
        return self._allowed(request, 'view')

    def has_add_permission(self, request):
        return self._allowed(request, 'add')

    def has_change_permission(self, request, obj=None):
        return self._allowed(request, 'change')

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('code',) if obj else ())

    def save_model(self, request, obj, form, change):
        from .institutions import FIELDS
        saved = save_institution(actor=request.user, institution_id=obj.pk if change else None,
                                 values={field: getattr(obj, field) for field in FIELDS})
        obj.pk = saved.pk
        obj._state.adding = False


class ApprovalReadOnlyAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        user = User.objects.filter(pk=request.user.pk, role='ADMIN', status='ACTIVE', is_active=True).first()
        return bool(user and user.has_perm(f'users.view_{self.model._meta.model_name}'))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(TeacherApproval)
class TeacherApprovalAdmin(ApprovalReadOnlyAdmin):
    list_display = ('teacher_profile', 'status', 'source', 'revision', 'updated_at')
    list_filter = ('status', 'source')
    search_fields = ('teacher_profile__user__username', 'teacher_profile__user__full_name')


@admin.register(TeacherApprovalEvent)
class TeacherApprovalEventAdmin(ApprovalReadOnlyAdmin):
    list_display = ('approval', 'action', 'actor', 'revision', 'created_at')
    list_filter = ('action',)


# Group membership can confer administrative permissions, so keep this legacy UI
# read-only too. Initial assignments use the explicit operator management command.
if admin.site.is_registered(Group):
    admin.site.unregister(Group)


@admin.register(Group)
class ReadOnlyGroupAdmin(admin.ModelAdmin):
    readonly_fields = ('name', 'permissions')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
