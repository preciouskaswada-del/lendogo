from django.apps import AppConfig

class LendogoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lendogo'

    def ready(self):
        """
        Import signals so the scam detector runs on listing save.
        This method runs once when Django starts.
        """
        import lendogo.signals