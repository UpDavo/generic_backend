from django.contrib import admin
from django.urls import include, path
from authentication.urls import urlpatterns as auth_urls
from tada.urls import urlpatterns as tada_urls

urlpatterns = [
    path('auth/', include(auth_urls)),
    path('tada/', include(tada_urls)),
    path('admin/', admin.site.urls),
]
