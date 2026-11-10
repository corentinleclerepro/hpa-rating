from pathlib import Path
from django.urls import path, re_path
from hpa_shared.webfiles import frontend
from . import views

page, asset = frontend(Path(__file__).parent / "static", ("console.js", "console.css"))
urlpatterns = [
    path("", page), path("administration", page), path("static/<str:name>", asset),
    path("api/session", views.session_info), path("api/admin/login", views.admin_login),
    path("api/logout/admin", views.admin_logout),
    path("api/admin/setup/start", views.begin_setup), path("api/admin/setup/finish", views.finish_setup),
    path("api/admin/invitations", views.invitations),
    path("api/admin/demandes", views.access_requests),
    re_path(r"^api/admin/demandes/(?P<rid>[0-9a-f]{32})/(?P<action>approve|decline)$", views.access_requests),
    re_path(r"^api/admin/invitations/(?P<gid>[0-9a-f]{32})/(?P<action>rotate|revoke)$", views.invitations),
]
