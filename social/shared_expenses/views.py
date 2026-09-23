from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from social.shared_expenses.models import SharedExpense, SharedExpenseShare
from social.shared_expenses.serializers import (
    SharedExpenseActionSerializer,
    SharedExpenseCreateSerializer,
    SharedExpenseRevisionSerializer,
    SharedExpenseSerializer,
    SharedExpenseSettlementInputSerializer,
    SharedExpenseVersionSerializer,
)
from social.shared_expenses.services import (
    SharedExpenseConflict,
    accept_share,
    cancel_shared_expense,
    canonical_request_hash,
    dispute_share,
    revise_shared_expense,
    settle_share,
)


class SharedExpenseViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "public_id"

    def get_queryset(self):
        user = self.request.user
        email = str(user.email or "").strip().lower()
        return (
            SharedExpense.objects.filter(
                Q(owner=user)
                | Q(shares__participant_user=user)
                | Q(shares__email__iexact=email)
                | Q(team__memberships__user=user, team__memberships__is_active=True)
            )
            .select_related("owner", "transaction", "team")
            .prefetch_related("shares__participant_user", "shares__contact", "settlements")
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == "create":
            return SharedExpenseCreateSerializer
        return SharedExpenseSerializer

    def list(self, request):
        queryset = self.get_queryset()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return Response(SharedExpenseSerializer(queryset, many=True, context={"request": request}).data)

    def retrieve(self, request, public_id=None):
        return Response(SharedExpenseSerializer(self.get_object(), context={"request": request}).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            expense = serializer.save()
        except SharedExpenseConflict as exc:
            return self._conflict_response(exc)
        output = SharedExpenseSerializer(expense, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)

    def _share(self, expense, share_id):
        return get_object_or_404(expense.shares.all(), public_id=share_id)

    def _conflict_response(self, exc: SharedExpenseConflict):
        payload = {"code": "shared_expense_conflict", "detail": str(exc)}
        if exc.expense is not None:
            payload["current"] = SharedExpenseSerializer(
                exc.expense,
                context={"request": self.request},
            ).data
        return Response(payload, status=status.HTTP_409_CONFLICT)

    @action(detail=True, methods=["post"])
    def accept(self, request, public_id=None):
        serializer = SharedExpenseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = self.get_object()
        try:
            updated = accept_share(
                share=self._share(expense, serializer.validated_data.get("share_id")),
                actor=request.user,
                base_version=serializer.validated_data["base_version"],
                request_id=getattr(request, "vexxo_request_id", ""),
            )
        except SharedExpenseConflict as exc:
            return self._conflict_response(exc)
        return Response(SharedExpenseSerializer(updated, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def dispute(self, request, public_id=None):
        serializer = SharedExpenseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = self.get_object()
        try:
            updated = dispute_share(
                share=self._share(expense, serializer.validated_data.get("share_id")),
                actor=request.user,
                base_version=serializer.validated_data["base_version"],
                request_id=getattr(request, "vexxo_request_id", ""),
            )
        except SharedExpenseConflict as exc:
            return self._conflict_response(exc)
        return Response(SharedExpenseSerializer(updated, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def revise(self, request, public_id=None):
        serializer = SharedExpenseRevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = revise_shared_expense(
                expense=self.get_object(),
                actor=request.user,
                split_method=serializer.validated_data["split_method"],
                share_specs=serializer.validated_data["shares"],
                base_version=serializer.validated_data["base_version"],
                request_id=getattr(request, "vexxo_request_id", ""),
            )
        except SharedExpenseConflict as exc:
            return self._conflict_response(exc)
        return Response(SharedExpenseSerializer(updated, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, public_id=None):
        serializer = SharedExpenseVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = cancel_shared_expense(
                expense=self.get_object(),
                actor=request.user,
                base_version=serializer.validated_data["base_version"],
                request_id=getattr(request, "vexxo_request_id", ""),
            )
        except SharedExpenseConflict as exc:
            return self._conflict_response(exc)
        return Response(SharedExpenseSerializer(updated, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def settle(self, request, public_id=None):
        serializer = SharedExpenseSettlementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        expense = self.get_object()
        try:
            settlement, _created = settle_share(
                share=self._share(expense, serializer.validated_data["share_id"]),
                actor=request.user,
                settlement_transaction=serializer.validated_data["transaction"],
                amount=serializer.validated_data["amount"],
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                request_hash=canonical_request_hash(request.data),
                base_version=serializer.validated_data["base_version"],
                request_id=getattr(request, "vexxo_request_id", ""),
            )
        except SharedExpenseConflict as exc:
            return self._conflict_response(exc)
        settlement.shared_expense.refresh_from_db()
        return Response(SharedExpenseSerializer(settlement.shared_expense, context={"request": request}).data)
