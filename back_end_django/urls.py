from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from authentication.urls import urlpatterns as auth_urls
from tada.urls import urlpatterns as tada_urls

urlpatterns = [
    path('auth/', include(auth_urls)),
    path('tada/', include(tada_urls)),
    path('core/', include('core.urls')),
    path('admin/', admin.site.urls),
]

# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
