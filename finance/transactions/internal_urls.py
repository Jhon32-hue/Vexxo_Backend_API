from django.urls import path

from finance.transactions.Views.intake_views import (
    InternalTransactionIntakeBatchApplyView,
    InternalTransactionIntakeBatchView,
    InternalTransactionIntakeReconcileView,
    InternalTransactionReconciliationIssueResolveView,
    InternalTransactionIntakeRowView,
)

urlpatterns = [
    path("intake/batches/", InternalTransactionIntakeBatchView.as_view(), name="transactions-intake-batches"),
    path("intake/batches/<uuid:batch_id>/apply/", InternalTransactionIntakeBatchApplyView.as_view(), name="transactions-intake-batch-apply"),
    path("intake/row/", InternalTransactionIntakeRowView.as_view(), name="transactions-intake-row"),
    path("intake/reconcile/", InternalTransactionIntakeReconcileView.as_view(), name="transactions-intake-reconcile"),
    path("reconciliation/issues/<int:issue_id>/resolve/", InternalTransactionReconciliationIssueResolveView.as_view(), name="transactions-reconciliation-issue-resolve"),
]
