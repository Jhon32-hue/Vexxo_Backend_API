from rest_framework import permissions, viewsets
from alerts.rules.models import Rule
from alerts.rules.serializers import ReglaSerializer
from identity.users.services.product_access_service import validate_rules_limit
from identity.users.services.product_usage_projection_service import increment_rules_usage


class ReglaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    queryset = Rule.objects.all().order_by('priority', 'id')
    serializer_class = ReglaSerializer

    def get_queryset(self):
        return Rule.objects.filter(owner=self.request.user).order_by("priority", "id")

    def perform_create(self, serializer):
        is_active = serializer.validated_data.get("active", True)
        if is_active:
            validate_rules_limit(self.request.user, source="alerts.rules.create")
        serializer.save(owner=self.request.user)
        if is_active:
            increment_rules_usage(
                self.request.user.id,
                delta=1,
                source="alerts.rules.views.perform_create",
            )

    def perform_update(self, serializer):
        instance = self.get_object()
        new_active = bool(serializer.validated_data.get("active", instance.active))
        activating = new_active and not instance.active
        deactivating = instance.active and not new_active
        if activating:
            validate_rules_limit(self.request.user, source="alerts.rules.activate")
        serializer.save()
        if activating:
            increment_rules_usage(
                self.request.user.id,
                delta=1,
                source="alerts.rules.views.perform_update.activate",
            )
        elif deactivating:
            increment_rules_usage(
                self.request.user.id,
                delta=-1,
                source="alerts.rules.views.perform_update.deactivate",
            )

    def perform_destroy(self, instance):
        was_active = bool(instance.active)
        super().perform_destroy(instance)
        if was_active:
            increment_rules_usage(
                self.request.user.id,
                delta=-1,
                source="alerts.rules.views.perform_destroy",
            )
