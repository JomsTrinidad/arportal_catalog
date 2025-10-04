from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/v1/", include("maps.api_urls")),
    path("maps/", include("maps.urls")),
    path("", RedirectView.as_view(url="/maps/")),
]
