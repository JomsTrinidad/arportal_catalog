from django.urls import path
from . import views
app_name = "maps"
urlpatterns = [
    path("", views.catalog, name="catalog"),
    path("list/", views.row_list, name="list"),
    path("upload/", views.upload_csv, name="upload"),
    path("<str:row_id>/", views.row_detail, name="detail"),
    path("<str:row_id>/edit/", views.RowEditView.as_view(), name="edit"),
    path("<str:row_id>/delete/", views.request_delete, name="delete"),
    path("<str:row_id>/undelete/", views.request_undelete, name="undelete"),
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/<int:pk>/", views.approval_detail, name="approval_detail"),
    path("view/<str:map_name>/<int:version>/", views.map_version_view, name="map_version"),
    path("propose/<str:row_id>/", views.propose_edit, name="propose_edit"),
    path("view-fragment/<str:map_name>/<int:version>/", views.map_version_fragment, name="map_version_fragment"),
    path("propose-fragment/<str:row_id>/", views.propose_edit_fragment, name="propose_edit_fragment"),
]
