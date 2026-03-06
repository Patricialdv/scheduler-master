from django.core.management.base import BaseCommand
from ...scripts.populate_data import generate_test_data 

class Command(BaseCommand):
    help = 'Carga datos de prueba iniciales en la base de datos.'

    def handle(self, *args, **options):
        # Llama a la función principal de tu script de llenado
        generate_test_data() 
        self.stdout.write(self.style.SUCCESS('Carga de datos de prueba finalizada.'))