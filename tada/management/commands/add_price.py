from django.core.management.base import BaseCommand
from tada.models import Price


class Command(BaseCommand):
    help = "Agrega un precio para el mes actual con valor 0.09"

    def handle(self, *args, **kwargs):
        value = 0.09
        price = Price.create_price_for_current_month(value)

        if price:
            self.stdout.write(self.style.SUCCESS(
                f"Precio agregado para el mes {price.month} con valor {price.value}"))
        else:
            self.stdout.write(self.style.WARNING(
                "Ya existe un precio para este mes."))
