from django.core.management.base import BaseCommand, CommandError

from documents.files.models import DocumentFile
from integrations.credentials.models import IntegrationCredential
from security.encryption import configured_keyring


class Command(BaseCommand):
    help = "Impide retirar una KEK mientras existan envelopes que aun dependan de ella."

    def add_arguments(self, parser):
        parser.add_argument("version")

    def handle(self, *args, **options):
        version = options["version"].strip()
        credentials = IntegrationCredential.objects.filter(key_version=version).count()
        documents = DocumentFile.objects.filter(is_encrypted=True, encryption_envelope__key_version=version).count()
        configured = version in configured_keyring()
        self.stdout.write(f"version={version} configured={str(configured).lower()} credentials={credentials} documents={documents}")
        if credentials or documents:
            raise CommandError("La version sigue en uso y no puede retirarse.")
        self.stdout.write("envelope_retirement_safe=true")
        self.stdout.write("jwt_retirement_requires_waiting_for_the_max_refresh_token_ttl=true")
