from rest_framework import mixins, status, viewsets, views
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from finance.budgets.Serializers import (
    BudgetListQuerySerializer,
    CategoryBudgetListQuerySerializer,
    CategoryBudgetPeriodOperationSerializer,
    CategoryBudgetWriteSerializer,
    SharedBudgetListQuerySerializer,
    SharedBudgetTemplateLinkSerializer,
    SharedBudgetTransactionLinkSerializer,
    SharedBudgetWriteSerializer,
)
from finance.budgets.services import (
    build_budget_monthly_overview,
    create_category_budget,
    create_shared_budget,
    delete_category_budget,
    delete_shared_budget,
    get_category_budget_detail,
    get_shared_budget_detail,
    link_template_to_shared_budget,
    link_transaction_to_shared_budget,
    list_category_budgets_with_metrics,
    list_shared_budgets_with_metrics,
    merge_category_budget_period,
    replace_category_budget_period,
    unlink_template_from_shared_budget,
    unlink_transaction_from_shared_budget,
    update_category_budget,
    update_shared_budget,
)


class CategoryBudgetViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CategoryBudgetWriteSerializer
        if self.action in {"merge_period", "replace_period"}:
            return CategoryBudgetPeriodOperationSerializer
        return CategoryBudgetListQuerySerializer

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(
            list_category_budgets_with_metrics(
                owner=request.user,
                month=serializer.validated_data.get("month"),
                category_id=serializer.validated_data.get("category"),
            )
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(get_category_budget_detail(owner=request.user, budget_id=int(kwargs["pk"])))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        category_id = validated_data.pop("category", None)
        payload = create_category_budget(
            owner=request.user,
            category_id=category_id,
            source="finance.budgets.api.category.create",
            **validated_data,
        )
        return Response(payload, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        category_id = validated_data.pop("category", None)
        payload = update_category_budget(
            owner=request.user,
            budget_id=int(kwargs["pk"]),
            category_id=category_id,
            source="finance.budgets.api.category.update",
            **validated_data,
        )
        return Response(payload)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        delete_category_budget(owner=request.user, budget_id=int(kwargs["pk"]), source="finance.budgets.api.category.delete")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="merge-period")
    def merge_period(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            merge_category_budget_period(
                owner=request.user,
                source="finance.budgets.api.category.merge",
                **serializer.validated_data,
            )
        )

    @action(detail=False, methods=["post"], url_path="replace-period")
    def replace_period(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            replace_category_budget_period(
                owner=request.user,
                source="finance.budgets.api.category.replace",
                **serializer.validated_data,
            )
        )


class SharedBudgetViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in {"link_transaction", "unlink_transaction"}:
            return SharedBudgetTransactionLinkSerializer
        if self.action in {"link_template", "unlink_template"}:
            return SharedBudgetTemplateLinkSerializer
        if self.action in {"create", "update", "partial_update"}:
            return SharedBudgetWriteSerializer
        return SharedBudgetListQuerySerializer

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(
            list_shared_budgets_with_metrics(
                user=request.user,
                month=serializer.validated_data.get("month"),
                team_id=serializer.validated_data.get("team"),
            )
        )

    def retrieve(self, request, *args, **kwargs):
        return Response(get_shared_budget_detail(user=request.user, budget_id=int(kwargs["pk"])))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = create_shared_budget(user=request.user, source="finance.budgets.api.shared.create", **serializer.validated_data)
        return Response(payload, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        payload = update_shared_budget(
            user=request.user,
            budget_id=int(kwargs["pk"]),
            source="finance.budgets.api.shared.update",
            **serializer.validated_data,
        )
        return Response(payload)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        delete_shared_budget(user=request.user, budget_id=int(kwargs["pk"]), source="finance.budgets.api.shared.delete")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="link-transaction")
    def link_transaction(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            link_transaction_to_shared_budget(
                user=request.user,
                budget_id=int(pk),
                source="finance.budgets.api.shared.link_transaction",
                **serializer.validated_data,
            )
        )

    @action(detail=True, methods=["post"], url_path="unlink-transaction")
    def unlink_transaction(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            unlink_transaction_from_shared_budget(
                user=request.user,
                budget_id=int(pk),
                source="finance.budgets.api.shared.unlink_transaction",
                **serializer.validated_data,
            )
        )

    @action(detail=True, methods=["post"], url_path="link-template")
    def link_template(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            link_template_to_shared_budget(
                user=request.user,
                budget_id=int(pk),
                source="finance.budgets.api.shared.link_template",
                **serializer.validated_data,
            )
        )

    @action(detail=True, methods=["post"], url_path="unlink-template")
    def unlink_template(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            unlink_template_from_shared_budget(
                user=request.user,
                budget_id=int(pk),
                source="finance.budgets.api.shared.unlink_template",
                **serializer.validated_data,
            )
        )


class BudgetMonthlyOverviewView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = BudgetListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        month = serializer.validated_data.get("month")
        if not month:
            return Response({"detail": "Debes enviar month=YYYY-MM."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(build_budget_monthly_overview(owner=request.user, month=month))
