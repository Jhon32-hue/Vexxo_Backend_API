from finance.transactions.Models.transacciones import Transaction

POSTED_STATUSES = {Transaction.Status.POSTED, Transaction.Status.RECONCILED}
CREDIT_TYPES = {Transaction.Type.INCOME}
DEBIT_TYPES = {Transaction.Type.EXPENSE, Transaction.Type.TRANSFER}
FAILED_OR_CANCELLED_STATUSES = {Transaction.Status.FAILED, Transaction.Status.CANCELED}
