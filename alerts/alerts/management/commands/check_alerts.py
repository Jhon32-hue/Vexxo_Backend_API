from django.core.management.base import BaseCommand
from alerts.alerts.services import generate_scheduled_payment_alerts


class Command(BaseCommand):
    help = 'Generate alerts (scheduled payments, etc.)'

    def handle(self, *args, **options):
        generate_scheduled_payment_alerts()
        self.stdout.write(self.style.SUCCESS('Alerts generation completed'))
