"""
Comando para eliminar logs de ventas (SalesReportLog, SalesRecord y SalesRecordQueryLog).

Uso:
    # Eliminar TODOS los logs de ventas
    python manage.py delete_logs --all --confirm

    # Eliminar logs específicos
    python manage.py delete_logs --sales-report --confirm
    python manage.py delete_logs --sales-record --confirm
    python manage.py delete_logs --sales-query --confirm

    # Ver estadísticas sin eliminar
    python manage.py delete_logs --all
"""

from django.core.management.base import BaseCommand
from tada.models import SalesReportLog, SalesRecord, SalesRecordQueryLog


class Command(BaseCommand):
    help = 'Elimina logs de ventas (SalesReportLog, SalesRecord y SalesRecordQueryLog)'

    def add_arguments(self, parser):
        # Opciones para tipos de logs de ventas
        parser.add_argument(
            '--sales-report',
            action='store_true',
            help='Eliminar SalesReportLog (logs de procesamiento de reportes)',
        )
        parser.add_argument(
            '--sales-record',
            action='store_true',
            help='Eliminar SalesRecord (histórico completo de ventas)',
        )
        parser.add_argument(
            '--sales-query',
            action='store_true',
            help='Eliminar SalesRecordQueryLog (logs de consultas al histórico)',
        )
        
        # Opción para eliminar todo
        parser.add_argument(
            '--all',
            action='store_true',
            help='Eliminar TODOS los logs de ventas',
        )

        # Confirmación
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirmar la eliminación (requerido para ejecutar)',
        )

        # Opción para hard delete
        parser.add_argument(
            '--hard',
            action='store_true',
            help='Eliminación permanente (hard delete) en lugar de soft delete',
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        hard_delete = options['hard']
        delete_all = options['all']

        # Definir qué logs eliminar
        logs_to_delete = {
            'SalesReportLog': options['sales_report'] or delete_all,
            'SalesRecord': options['sales_record'] or delete_all,
            'SalesRecordQueryLog': options['sales_query'] or delete_all,
        }

        # Si no se seleccionó ningún log, mostrar ayuda
        if not any(logs_to_delete.values()):
            self.stdout.write(self.style.WARNING(
                'Debes especificar al menos un tipo de log o usar --all'
            ))
            self.stdout.write('\nEjemplos de uso:')
            self.stdout.write('  python manage.py delete_logs --all --confirm')
            self.stdout.write('  python manage.py delete_logs --sales-report --confirm')
            self.stdout.write('  python manage.py delete_logs --sales-record --confirm')
            self.stdout.write('  python manage.py delete_logs --sales-query --confirm')
            return

        # Obtener estadísticas actuales
        stats = self._get_stats()

        # Mostrar estadísticas
        self.stdout.write(self.style.HTTP_INFO('\n📊 ESTADÍSTICAS ACTUALES DE LOGS:\n'))
        total_logs = 0
        for log_name, count in stats.items():
            if logs_to_delete.get(log_name, False):
                self.stdout.write(
                    self.style.WARNING(f'  🗑️  {log_name}: {count:,} registros (SERÁ ELIMINADO)')
                )
                total_logs += count
            else:
                self.stdout.write(f'  ✓  {log_name}: {count:,} registros')

        self.stdout.write(self.style.HTTP_INFO(f'\n📋 Total a eliminar: {total_logs:,} registros\n'))

        # Si no hay confirmación, solo mostrar estadísticas
        if not confirm:
            self.stdout.write(self.style.WARNING(
                '⚠️  MODO SIMULACIÓN - No se eliminaron registros'
            ))
            self.stdout.write(self.style.WARNING(
                'Para confirmar la eliminación, agrega el flag --confirm'
            ))
            return

        # Confirmar acción destructiva
        delete_type = 'PERMANENTE (HARD DELETE)' if hard_delete else 'SOFT DELETE (recuperable)'
        self.stdout.write(self.style.ERROR(
            f'\n⚠️  ATENCIÓN: Vas a realizar un {delete_type} de {total_logs:,} registros'
        ))
        
        confirmation = input('Escribe "ELIMINAR" para confirmar: ')
        if confirmation != 'ELIMINAR':
            self.stdout.write(self.style.WARNING('❌ Operación cancelada'))
            return

        # Realizar eliminación
        self.stdout.write(self.style.HTTP_INFO('\n🗑️  Eliminando registros...\n'))
        deleted_counts = {}

        if logs_to_delete['SalesReportLog']:
            count = self._delete_logs(SalesReportLog, hard_delete)
            deleted_counts['SalesReportLog'] = count
            self.stdout.write(f'  ✓ SalesReportLog: {count:,} eliminados')

        if logs_to_delete['SalesRecord']:
            count = self._delete_logs(SalesRecord, hard_delete)
            deleted_counts['SalesRecord'] = count
            self.stdout.write(f'  ✓ SalesRecord: {count:,} eliminados')

        if logs_to_delete['SalesRecordQueryLog']:
            count = self._delete_logs(SalesRecordQueryLog, hard_delete)
            deleted_counts['SalesRecordQueryLog'] = count
            self.stdout.write(f'  ✓ SalesRecordQueryLog: {count:,} eliminados')

        # Resumen final
        total_deleted = sum(deleted_counts.values())
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Eliminación completada: {total_deleted:,} registros eliminados'
        ))

        if not hard_delete:
            self.stdout.write(self.style.HTTP_INFO(
                '\nℹ️  Se realizó un SOFT DELETE - Los registros pueden recuperarse modificando deleted_at'
            ))

    def _get_stats(self):
        """Obtener estadísticas de cada tipo de log de ventas"""
        return {
            'SalesReportLog': SalesReportLog.objects.filter(deleted_at__isnull=True).count(),
            'SalesRecord': SalesRecord.objects.filter(deleted_at__isnull=True).count(),
            'SalesRecordQueryLog': SalesRecordQueryLog.objects.filter(deleted_at__isnull=True).count(),
        }

    def _delete_logs(self, model, hard_delete=False):
        """
        Eliminar logs de un modelo específico.
        
        Args:
            model: Clase del modelo a eliminar
            hard_delete: Si es True, elimina permanentemente. Si es False, hace soft delete.
        
        Returns:
            int: Cantidad de registros eliminados
        """
        if hard_delete:
            # Hard delete - elimina permanentemente de la base de datos
            count, _ = model.objects.filter(deleted_at__isnull=True).delete()
            return count
        else:
            # Soft delete - marca como eliminado
            from django.utils import timezone
            queryset = model.objects.filter(deleted_at__isnull=True)
            count = queryset.count()
            queryset.update(deleted_at=timezone.now())
            return count
