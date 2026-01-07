from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.http import HttpResponse
from django.db.models import Count, Q
from django.utils.dateparse import parse_date
import pandas as pd
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from django.utils.timezone import now
from tada.models import SalesReportLog, Price, AppPrice
from tada.utils.constants import APPS, APP_NAMES


class SalesReportProcessorView(APIView):
    """
    Vista para procesar un archivo Excel con datos de ventas y devolver un consolidado.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Procesar un archivo Excel con ventas y devolver el consolidado procesado.
        
        El archivo Excel con datos de ventas se procesa y se devuelve 
        otro Excel con el consolidado de ventas.
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'Se requiere un archivo Excel en el campo "file"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        excel_file = request.FILES['file']

        # Validar que sea un archivo Excel
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response(
                {'error': 'El archivo debe ser un Excel (.xlsx o .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Leer el archivo Excel con datos de ventas
            df = pd.read_excel(BytesIO(excel_file.read()))

            # TODO: Implementar la lógica de procesamiento y consolidado de ventas aquí
            # Por ahora, el DataFrame procesado es el mismo que el original
            consolidated_df = self._process_sales_data(df)

            # Crear log del procesamiento
            sales_log = SalesReportLog.objects.create(
                filename=excel_file.name,
                rows_processed=len(df),
                date=now().date(),
                time=now().time(),
                app=str(APPS['SALES']),
                user=request.user
            )

            # Generar el archivo Excel de salida con el consolidado
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                consolidated_df.to_excel(writer, index=False, sheet_name='Consolidado')
            
            output.seek(0)

            # Generar nombre de archivo con timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'reporte_ventas_consolidado_{timestamp}.xlsx'

            # Crear respuesta HTTP con el archivo Excel
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response

        except Exception as e:
            return Response(
                {'error': f'Error al procesar el archivo de ventas: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _process_sales_data(self, df):
        """
        Procesar los datos de ventas y generar el consolidado.
        
        TODO: Implementar la lógica de procesamiento y consolidado de ventas.
        
        Args:
            df: DataFrame con los datos de ventas originales
            
        Returns:
            DataFrame con el consolidado de ventas procesado
        """
        # TODO: Aquí va la lógica de procesamiento del consolidado de ventas
        # Por ejemplo:
        # - Agrupar ventas por categoría/producto
        # - Calcular totales y subtotales
        # - Generar métricas de ventas
        # - Aplicar fórmulas de negocio
        # - Crear resúmenes y agregaciones
        
        # Por ahora, solo devolvemos el DataFrame original con una columna adicional
        consolidated_df = df.copy()
        
        # Ejemplo: Agregar una columna indicando cuándo fue procesado
        consolidated_df['fecha_procesamiento'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return consolidated_df


class SalesReportLogsStatsView(APIView):
    """Vista para obtener estadísticas de SalesReportLogs con precios"""
    permission_classes = [IsAuthenticated]

    def _get_price_for_period(self, app, start_date, end_date):
        """
        Obtiene el precio más apropiado para el período consultado.

        Lógica:
        1. Si hay start_date, busca el precio del mes de start_date
        2. Si no hay precio para ese mes, busca el precio más reciente anterior
        3. Si no hay start_date, usa el precio más reciente disponible
        """
        try:
            if start_date:
                # Parsear start_date
                if isinstance(start_date, str):
                    start_date = parse_date(start_date)
                
                if start_date:
                    # Buscar precio del mes de start_date
                    first_day_of_month = start_date.replace(day=1)
                    price = Price.objects.filter(
                        app=app,
                        month=first_day_of_month,
                        deleted_at__isnull=True
                    ).first()
                    
                    if price:
                        return price
                    
                    # Si no hay precio para ese mes, buscar el más reciente anterior
                    price = Price.objects.filter(
                        app=app,
                        month__lt=first_day_of_month,
                        deleted_at__isnull=True
                    ).order_by('-month').first()
                    
                    if price:
                        return price

            # Si no hay start_date o no se encontró precio, usar el más reciente
            return Price.objects.filter(
                app=app,
                deleted_at__isnull=True
            ).order_by('-month').first()

        except Exception:
            return None

    def get(self, request):
        """
        Obtener estadísticas de reportes de ventas con pricing.
        
        Query params opcionales:
        - start_date: Fecha inicial (YYYY-MM-DD)
        - end_date: Fecha final (YYYY-MM-DD)
        - user_id: Filtrar por usuario específico
        """
        # Obtener parámetros de filtro de fecha
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        user_id = request.query_params.get('user_id')

        # Construir filtros de fecha
        date_filters = Q()
        if start_date:
            try:
                start_date_parsed = parse_date(start_date)
                if start_date_parsed:
                    date_filters &= Q(date__gte=start_date_parsed)
            except (ValueError, TypeError):
                pass

        if end_date:
            try:
                end_date_parsed = parse_date(end_date)
                if end_date_parsed:
                    date_filters &= Q(date__lte=end_date_parsed)
            except (ValueError, TypeError):
                pass

        # Filtros adicionales
        if user_id:
            date_filters &= Q(user_id=user_id)

        # Obtener estadísticas generales de sales report logs
        total_logs = SalesReportLog.objects.filter(date_filters, deleted_at__isnull=True).count()
        total_rows_processed = SalesReportLog.objects.filter(
            date_filters, deleted_at__isnull=True
        ).aggregate(total=Count('rows_processed'))['total'] or 0

        # Obtener desglose por usuario
        logs_by_user = SalesReportLog.objects.filter(
            date_filters, deleted_at__isnull=True
        ).values(
            'user__email', 'user__first_name', 'user__last_name'
        ).annotate(count=Count('id')).order_by('-count')

        # Obtener precio para la app SALES según el período
        price_instance = self._get_price_for_period(
            str(APPS['SALES']), start_date, end_date)

        # Obtener el nombre del AppPrice si existe
        app_price_name = None
        try:
            if price_instance:
                app_price = AppPrice.objects.filter(
                    price=price_instance, deleted_at__isnull=True
                ).first()
                if app_price:
                    app_price_name = app_price.name
        except AppPrice.DoesNotExist:
            pass

        if price_instance:
            unit_price = Decimal(str(price_instance.value))
            total_cost = unit_price * Decimal(str(total_logs))
            price_month = price_instance.month.strftime('%Y-%m')
        else:
            unit_price = Decimal('0')
            total_cost = Decimal('0')
            price_month = None

        return Response({
            'app_type': 'SALES',
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'user_id': user_id
            },
            'summary': {
                'total_logs': total_logs,
                'total_rows_processed': total_rows_processed,
                'app_name': APP_NAMES[APPS['SALES']],
                'app_price_name': app_price_name,
                'unit_price': str(unit_price),
                'total_cost': str(total_cost),
                'price_month': price_month
            },
            'breakdown': {
                'by_user': list(logs_by_user)
            }
        }, status=status.HTTP_200_OK)


class SalesReportLogsListView(APIView):
    """Vista para listar los logs de procesamiento de reportes de ventas"""
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        Obtiene la lista de logs de sales reports con paginación.

        Query params opcionales:
        - user_id: Filtrar por usuario específico
        - start_date: Fecha inicial (YYYY-MM-DD)
        - end_date: Fecha final (YYYY-MM-DD)
        - page: Número de página (por defecto: 1)
        - page_size: Tamaño de página (por defecto: 10)
        """
        try:
            # Obtener parámetros de filtro
            user_id = request.query_params.get('user_id')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')

            # Construir query base
            queryset = SalesReportLog.objects.filter(
                deleted_at__isnull=True
            ).select_related('user').order_by('-created_at')

            # Aplicar filtros
            if user_id:
                queryset = queryset.filter(user_id=user_id)

            if start_date:
                try:
                    start_date_parsed = parse_date(start_date)
                    if start_date_parsed:
                        queryset = queryset.filter(date__gte=start_date_parsed)
                except (ValueError, TypeError):
                    pass

            if end_date:
                try:
                    end_date_parsed = parse_date(end_date)
                    if end_date_parsed:
                        queryset = queryset.filter(date__lte=end_date_parsed)
                except (ValueError, TypeError):
                    pass

            # Aplicar paginación
            paginator = self.pagination_class()
            paginated_queryset = paginator.paginate_queryset(queryset, request)

            # Serializar resultados
            results = []
            for log in paginated_queryset:
                user_email = log.user.email if log.user else None
                user_name = f"{log.user.first_name} {log.user.last_name}" if log.user else None
                
                results.append({
                    'id': log.id,
                    'filename': log.filename,
                    'rows_processed': log.rows_processed,
                    'date': log.date.strftime('%Y-%m-%d'),
                    'time': log.time.strftime('%H:%M:%S'),
                    'user_email': user_email,
                    'user_name': user_name,
                    'created_at': log.created_at.isoformat()
                })

            # Retornar respuesta paginada
            return paginator.get_paginated_response(results)

        except Exception as e:
            print(f"❌ Error obteniendo logs de sales reports: {str(e)}")
            return Response({
                "error": "Error obteniendo logs de sales reports",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
