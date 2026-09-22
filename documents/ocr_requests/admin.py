from django.contrib import admin

from documents.ocr_requests.models import OcrFieldObservation, OcrRequest


admin.site.register(OcrRequest)
admin.site.register(OcrFieldObservation)
