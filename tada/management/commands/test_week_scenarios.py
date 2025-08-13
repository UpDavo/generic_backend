from django.core.management.base import BaseCommand
from datetime import datetime, date, timedelta
import pytz
from tada.services.command_service import get_logical_business_day


class Command(BaseCommand):
    help = 'Simular escenarios específicos de semanas'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Simulando escenarios de semanas...')
        )
        
        # Simulemos un domingo 20:00 específico
        guayaquil_tz = pytz.timezone('America/Guayaquil')
        
        # Crear diferentes horarios de domingo para probar
        test_scenarios = [
            (7, 19, "Domingo 19:00"),
            (7, 20, "Domingo 20:00"),
            (7, 21, "Domingo 21:00"),
            (7, 22, "Domingo 22:00"),
        ]
        
        for day, hour, description in test_scenarios:
            # Simular datetime de Guayaquil
            class MockGuayaquilTime:
                def __init__(self, day_of_week, hour):
                    self.day_of_week = day_of_week
                    self.hour = hour
                    # Usar fecha real del domingo actual
                    base_date = date(2025, 7, 27)  # Domingo 27 julio
                    self._date = base_date
                
                def date(self):
                    return self._date
                    
                def isoweekday(self):
                    return self.day_of_week
            
            mock_time = MockGuayaquilTime(day, hour)
            dia_seleccionado = get_logical_business_day(mock_time)
            
            # Calcular semana lógica
            logical_date = mock_time.date()
            if dia_seleccionado != mock_time.isoweekday():
                logical_date = logical_date - timedelta(days=1)
            
            logical_week = logical_date.isocalendar()[1]
            real_week = mock_time.date().isocalendar()[1]
            
            self.stdout.write(f"{description}:")
            self.stdout.write(f"  - Día lógico: {dia_seleccionado}")
            self.stdout.write(f"  - Semana lógica: {logical_week}")
            self.stdout.write(f"  - Semana real: {real_week}")
            if logical_week != real_week:
                self.stdout.write(self.style.WARNING(f"  ⚠️ DIFERENCIA: lógica={logical_week}, real={real_week}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  ✅ Coincide: semana {logical_week}"))
            self.stdout.write("")
        
        self.stdout.write(
            self.style.SUCCESS('Simulación completada.')
        )
