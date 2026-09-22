from django.urls import include, path
from rest_framework.routers import DefaultRouter

from documents.files.views import DocumentDownloadView, DocumentFileViewSet

router = DefaultRouter()
router.register("files", DocumentFileViewSet, basename="document-file")
router.register("downloads", DocumentDownloadView, basename="document-download")

urlpatterns = [path("", include(router.urls))]
