from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from community.auth import BlockAwareTokenObtainPairView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path("", TemplateView.as_view(template_name="codeparsers/home.html"), name="home"),

    path("admin/", admin.site.urls),

    # existing endpoints
    path("api/community/", include("community.urls")),      # old minimal views
    path("api/code/", include("codeparsers.urls")),

    # ✅ new DRF router (viewsets & actions)
    path("api/community/v2/", include("community.api_urls")),

    # auth
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
