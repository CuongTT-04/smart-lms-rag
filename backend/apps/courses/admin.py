from django.contrib import admin

from .models import AccessPolicy, Classroom, Course, CourseMember, Enrollment, JoinRequest


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Course)
class CourseAdmin(ReadOnlyAdmin):
    list_display = ("title", "status", "created_at", "published_at")
    list_filter = ("status",)
    search_fields = ("title",)
    readonly_fields = (
        "id", "title", "description", "status",
        "created_at", "updated_at", "published_at",
    )


@admin.register(CourseMember)
class CourseMemberAdmin(ReadOnlyAdmin):
    list_display = ("course", "user", "role", "status", "joined_at", "removed_at")
    list_filter = ("role", "status")
    list_select_related = ("course", "user")
    search_fields = ("course__title", "user__username", "user__email")
    readonly_fields = ("id", "course", "user", "role", "status", "joined_at", "removed_at")


@admin.register(AccessPolicy, Classroom, Enrollment, JoinRequest)
class EnrollmentReadOnlyAdmin(ReadOnlyAdmin):
    pass
