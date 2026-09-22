from django.urls import path, include
from rest_framework.routers import DefaultRouter
from planning.goals.views import GoalContributionViewSet, GoalMilestoneViewSet, MetaViewSet

router = DefaultRouter()
router.register(r'metas', MetaViewSet, basename='meta')
router.register(r'aportes', GoalContributionViewSet, basename='goal-contribution')
router.register(r'milestones', GoalMilestoneViewSet, basename='goal-milestone')

urlpatterns = [
    path('', include(router.urls)),
]
