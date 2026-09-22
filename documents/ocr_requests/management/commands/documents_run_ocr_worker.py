import time

from django.core.management.base import BaseCommand

from documents.ocr_requests.services import process_ocr_batch


class Command(BaseCommand):
    help = "Procesa solicitudes OCR locales desde PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--sleep-seconds", type=int, default=5)
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, **options):
        while True:
            summary = process_ocr_batch(limit=options["limit"], worker_id=options["worker_id"])
            self.stdout.write(f"documents OCR cycle={summary}")
            if not options["loop"]:
                return
            time.sleep(max(1, options["sleep_seconds"]))
