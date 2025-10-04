from django.urls import path
from . import api_views
urlpatterns = [
    path("rows/", api_views.RowListView.as_view()),
    path("rows/<str:row_id>/", api_views.RowDetailView.as_view()),
    path("rows/create/", api_views.RowCreateView.as_view()),
    path("rows/update/", api_views.RowUpdateView.as_view()),
    path("rows/delete/", api_views.RowDeleteView.as_view()),
    path("rows/undelete/", api_views.RowUndeleteView.as_view()),
    path("rows/upload/", api_views.RowUploadView.as_view()),
]
