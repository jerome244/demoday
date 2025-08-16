from django.urls import path
from .views import ParseAPI

urlpatterns = [
    path("parse/", ParseAPI.as_view(), name="codeparsers-parse"),
]
