from django.urls import path
from authentication.views.auth_api import LoginView, RegisterView, LogoutView
from authentication.views.user_api import UserDetailUpdateView, UserListView
from authentication.views.role_api import RoleListCreateView, RoleDetailView
from authentication.views.permission_api import PermissionListCreateView, PermissionDetailView

urlpatterns = [
    # Auth
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),

    # Roles
    path("roles/", RoleListCreateView.as_view(), name="list-create-roles"),
    path("roles/<int:pk>/", RoleDetailView.as_view(), name="detail-role"),

    # Permissions
    path("permissions/", PermissionListCreateView.as_view(),
         name="list-create-permissions"),
    path("permissions/<int:pk>/", PermissionDetailView.as_view(),
         name="detail-permission"),

    # userinfo
    path("user/", UserDetailUpdateView.as_view(), name="user-detail"),
    path("users/", UserListView.as_view(), name="user-list"),
]
