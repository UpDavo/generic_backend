from django.contrib import admin
from django.urls import include, path
from authentication.urls import urlpatterns as auth_urls

urlpatterns = [
    path('auth/', include(auth_urls)),
    path('admin/', admin.site.urls),
]
