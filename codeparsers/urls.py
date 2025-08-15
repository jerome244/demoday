from django.urls import path
from .views import ParseAPI, ParseZipAPI, GraphView

urlpatterns = [
    path("parse-zip/", ParseZipAPI.as_view(), name="codeparsers-parse-zip"),
    path("parse-zip",  ParseZipAPI.as_view(), name="codeparsers-parse-zip-noslash"),  # optional alias
    path("parse/",     ParseAPI.as_view(),     name="codeparsers-parse"),
    path("parse",      ParseAPI.as_view(),     name="codeparsers-parse-noslash"),     # optional alias
    path("graph/",     GraphView.as_view(),    name="codeparsers-graph"),
]
