from django.db import models
class InvoiceLine(models.Model):
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
