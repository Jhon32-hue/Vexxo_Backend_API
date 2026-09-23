from django.urls import include, path
from rest_framework.routers import DefaultRouter

from social.shared_expenses.views import SharedExpenseViewSet

router = DefaultRouter()
router.register("shared-expenses", SharedExpenseViewSet, basename="shared-expense")

urlpatterns = [path("", include(router.urls))]
