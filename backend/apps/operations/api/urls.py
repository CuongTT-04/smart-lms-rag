from django.urls import path
from apps.users.api.institution_views import InstitutionAdminDetailView, InstitutionAdminListView, InstitutionImportView
from .account_views import (AccountListView, AccountDetailView, AccountRoleView, AccountHistoryView,
                           TeacherListView, TeacherDecisionView, TeacherHistoryView)
from .overview_views import OverviewView
from .workspace_views import CapabilitiesView, OperationsHealthView

app_name = "operations"

urlpatterns = [
    path('capabilities/', CapabilitiesView.as_view(), name='capabilities'),
    path('health/', OperationsHealthView.as_view(), name='health'),
    path('overview/', OverviewView.as_view(), name='overview'),
    path('users/', AccountListView.as_view(), name='users'),
    path('users/<uuid:user_id>/', AccountDetailView.as_view(), name='user-detail'),
    path('users/<uuid:user_id>/role/', AccountRoleView.as_view(), name='user-role'),
    path('users/<uuid:user_id>/history/', AccountHistoryView.as_view(), name='user-history'),
    path('teachers/', TeacherListView.as_view(), name='teachers'),
    path('teachers/<uuid:user_id>/approval/', TeacherDecisionView.as_view(), name='teacher-decision'),
    path('teachers/<uuid:user_id>/approval/history/', TeacherHistoryView.as_view(), name='teacher-history'),
    path('institutions/', InstitutionAdminListView.as_view(), name='institutions'),
    path('institutions/import/', InstitutionImportView.as_view(), name='institutions-import'),
    path('institutions/<uuid:institution_id>/', InstitutionAdminDetailView.as_view(), name='institution-detail'),
]
