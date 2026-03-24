from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'common'

    def ready(self):
        from common.eventing_bootstrap import bootstrap_domain_eventing

        bootstrap_domain_eventing()
