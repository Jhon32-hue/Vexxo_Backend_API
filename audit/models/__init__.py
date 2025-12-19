from django.db import models
class AuditLog(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=40)   # create/update/delete
    model = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    diff = models.JSONField(default=dict, blank=True)
    ts = models.DateTimeField(auto_now_add=True)

