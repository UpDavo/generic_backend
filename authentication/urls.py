from django.urls import path
from authentication.views.auth_api import LoginView, RegisterView, LogoutView
from authentication.views.user_api import UserDetailView
from authentication.views.role_api import RoleCreateView
from authentication.views.permission_api import PermissionListCreateView, PermissionDetailView

urlpatterns = [
    # Auth
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),

    # Roles
    path("roles/create/", RoleCreateView.as_view(), name="create-role"),

    # Permissions
    path("permissions/", PermissionListCreateView.as_view(),
         name="list-create-permissions"),
    path("permissions/<int:pk>/", PermissionDetailView.as_view(),
         name="detail-permission"),

    # userinfo
    path("user/<int:user_id>/", UserDetailView.as_view(), name="user-detail"),
]
