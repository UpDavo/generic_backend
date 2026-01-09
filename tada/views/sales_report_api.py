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
from django.conf import settings
from tada.models import SalesReportLog, Price, AppPrice, POC, VentasProductosApp, VentasProductosCompra
from tada.utils.constants import APPS, APP_NAMES
import numpy as np


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
            # Capturar tiempo de inicio del procesamiento
            import time
            start_time = time.time()

            if settings.DEBUG:
                print(f"\n🚀 Iniciando procesamiento de '{excel_file.name}'...")

            # Leer el archivo Excel con datos de ventas
            df = pd.read_excel(BytesIO(excel_file.read()))

            if settings.DEBUG:
                print(f"📊 Archivo leído: {len(df)} filas encontradas")

            # Procesar los datos de ventas
            consolidated_df = self._process_sales_data(df)

            # Calcular tiempo de procesamiento
            end_time = time.time()
            processing_duration = Decimal(str(round(end_time - start_time, 3)))

            if settings.DEBUG:
                print(
                    f"✅ Procesamiento completado: {len(consolidated_df)} filas generadas en {processing_duration}s")

            # Crear log del procesamiento con tiempo de ejecución
            sales_log = SalesReportLog.objects.create(
                filename=excel_file.name,
                rows_processed=len(df),
                date=now().date(),
                time=now().time(),
                processing_time_seconds=processing_duration,
                app=str(APPS['SALES']),
                user=request.user
            )

            # Generar el archivo Excel de salida con el consolidado
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                consolidated_df.to_excel(
                    writer, index=False, sheet_name='Consolidado')

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

        Args:
            df: DataFrame con los datos de ventas originales

        Returns:
            DataFrame con el consolidado de ventas procesado
        """
        # Definir las columnas requeridas
        required_columns = [
            'Date Hierarchy - Date',
            'STORE_NAME',
            'product_spk',
            '# Units',
            '# Orders'
        ]

        # Verificar que todas las columnas requeridas existan en el DataFrame
        missing_columns = [
            col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(
                f"Faltan las siguientes columnas en el archivo: {', '.join(missing_columns)}")

        # Filtrar el DataFrame para incluir solo las columnas requeridas
        consolidated_df = df[required_columns].copy()

        # Procesar la columna product_spk para extraer solo el valor después del ';'
        # Formato original: O1836;14581 -> solo queremos 14581
        consolidated_df['product_spk'] = consolidated_df['product_spk'].astype(str).apply(
            lambda x: x.split(';')[1] if ';' in x else x
        )

        # Renombrar las columnas
        consolidated_df = consolidated_df.rename(columns={
            'Date Hierarchy - Date': 'date',
            'STORE_NAME': 'store_name',
            'product_spk': 'sku',
            '# Units': 'units',
            '# Orders': 'orders'
        })

        # Enriquecer datos con POC
        if settings.DEBUG:
            print(f"🏪 Enriqueciendo datos de POC...")
        consolidated_df = self._enrich_with_poc_data(consolidated_df)

        # Enriquecer datos con información de productos
        if settings.DEBUG:
            print(f"📦 Enriqueciendo datos de productos...")
        consolidated_df = self._enrich_with_product_data(consolidated_df)
        if settings.DEBUG:
            print(
                f"   ✓ {len(consolidated_df)} filas después de expansión de materiales")

        # Enriquecer datos con información de fechas
        if settings.DEBUG:
            print(f"📅 Enriqueciendo datos de fecha...")
        consolidated_df = self._enrich_with_date_data(consolidated_df)

        # Seleccionar solo las columnas finales (sin las columnas intermedias)
        final_columns = [
            # Datos de POC
            'poc_id',
            'poc_name',
            'poc_homolo',
            'poc_city',
            'poc_region',
            # Datos de producto padre (del Excel)
            'sku_padre',
            'nombre_padre',
            # Datos de transacción
            'orders',
            'units',
            # Datos de producto material (de productos_compra)
            'sku_vtex',
            'name',
            'name_homologated',
            'category',
            'brand',
            'retornable',
            'units_assigned',
            # Métricas de ventas
            'units_per_sku',
            'unidades_por_caja',
            'venta_pack',
            'mililitros',
            'hectolitros',
            'dolars',
            # Datos de fecha
            'date',
            'week',
            'year',
            'month',
            'day',
            'dayname',
            'year_month'
        ]

        # Verificar qué columnas existen
        existing_columns = [
            col for col in final_columns if col in consolidated_df.columns]
        missing_columns = [
            col for col in final_columns if col not in consolidated_df.columns]

        if missing_columns:
            print(f"⚠️ Columnas faltantes: {missing_columns}")
            print(f"📊 Columnas disponibles: {list(consolidated_df.columns)}")

        consolidated_df = consolidated_df[existing_columns]

        # Convertir todos los campos de texto a mayúsculas (vectorizado para mejor rendimiento)
        text_columns = ['poc_name', 'poc_homolo', 'poc_city', 'poc_region',
                        'sku_padre', 'nombre_padre', 'sku_vtex', 'name', 'name_homologated', 'category', 'brand', 'dayname']

        existing_text_cols = [
            col for col in text_columns if col in consolidated_df.columns]
        if existing_text_cols:
            consolidated_df[existing_text_cols] = consolidated_df[existing_text_cols].astype(
                str).apply(lambda x: x.str.upper())

        # Ordenar por fecha y luego por poc_name
        sort_columns = []
        if 'date' in consolidated_df.columns:
            sort_columns.append('date')
        if 'poc_name' in consolidated_df.columns:
            sort_columns.append('poc_name')

        if sort_columns:
            if settings.DEBUG:
                print(f"🔄 Ordenando datos...")
            consolidated_df = consolidated_df.sort_values(by=sort_columns)
            consolidated_df = consolidated_df.reset_index(drop=True)

        # Renombrar columnas a español para el Excel de salida
        spanish_columns = {
            'poc_id': 'id_poc',
            'poc_name': 'nombre_poc',
            'poc_homolo': 'poc_homologado',
            'poc_city': 'ciudad_poc',
            'poc_region': 'region_poc',
            'orders': 'pedidos',
            'units': 'unidades',
            'name': 'nombre',
            'name_homologated': 'nombre_homologado',
            'category': 'categoria',
            'brand': 'marca',
            'units_assigned': 'unidades_asignadas',
            'units_per_sku': 'unidades_por_sku',
            'dolars': 'dolares',
            'date': 'fecha',
            'week': 'semana',
            'year': 'año',
            'month': 'mes',
            'day': 'dia',
            'dayname': 'nombre_dia',
            'year_month': 'año_mes'
        }
        
        # Solo renombrar las columnas que existen en el DataFrame
        columns_to_rename = {k: v for k, v in spanish_columns.items() if k in consolidated_df.columns}
        consolidated_df = consolidated_df.rename(columns=columns_to_rename)

        return consolidated_df

    def _enrich_with_poc_data(self, df):
        """
        Enriquecer el DataFrame con información de POC.

        Args:
            df: DataFrame con columna store_name

        Returns:
            DataFrame enriquecido con datos de POC
        """
        # Obtener todos los POCs activos
        pocs = POC.objects.filter(deleted_at__isnull=True)

        # Crear diccionario para búsqueda rápida
        poc_lookup = {}
        for poc in pocs:
            # Agregar nombre principal
            poc_lookup[poc.name.lower().strip()] = {
                'poc_id': poc.id_poc,
                'poc_name': poc.name,
                'poc_city': poc.city,
                'poc_region': poc.region
            }
            # Agregar nombres homologados
            for homologated_name in poc.homologated_names:
                poc_lookup[homologated_name.lower().strip()] = {
                    'poc_id': poc.id_poc,
                    'poc_name': poc.name,
                    'poc_city': poc.city,
                    'poc_region': poc.region
                }

        # Función para buscar POC
        def find_poc(store_name):
            if pd.isna(store_name):
                return pd.Series({
                    'poc_id': None,
                    'poc_name': None,
                    'poc_homolo': None,
                    'poc_city': None,
                    'poc_region': None
                })

            store_name_lower = str(store_name).lower().strip()
            poc_data = poc_lookup.get(store_name_lower)

            if poc_data:
                return pd.Series({
                    'poc_id': poc_data['poc_id'],
                    'poc_name': poc_data['poc_name'],
                    'poc_homolo': store_name if store_name != poc_data['poc_name'] else None,
                    'poc_city': poc_data['poc_city'],
                    'poc_region': poc_data['poc_region']
                })
            else:
                return pd.Series({
                    'poc_id': None,
                    'poc_name': None,
                    'poc_homolo': store_name,
                    'poc_city': None,
                    'poc_region': None
                })

        # Aplicar la búsqueda de POC
        poc_data = df['store_name'].apply(find_poc)
        df = pd.concat([df, poc_data], axis=1)

        return df

    def _enrich_with_product_data(self, df):
        """
        Enriquecer el DataFrame con información de productos.

        LÓGICA:
        1. El SKU del Excel SIEMPRE se busca en productos_app
        2. TODOS los productos_app tienen materiales (mínimo 1)
        3. Se expanden filas según materiales y cantidades
        4. La info final viene de productos_compra para cada material

        Args:
            df: DataFrame con columna sku

        Returns:
            DataFrame enriquecido con datos de productos (puede tener más filas que el original)
        """
        # Obtener todos los productos App activos con sus materiales (optimizado con only)
        products_app = VentasProductosApp.objects.filter(
            deleted_at__isnull=True
        ).only('code', 'name', 'type').prefetch_related('materials')

        # Crear diccionario de lookup para productos app
        product_app_lookup = {str(p.code): p for p in products_app}

        # Obtener todos los productos Compra activos (optimizado con only)
        products_compra = VentasProductosCompra.objects.filter(
            deleted_at__isnull=True
        ).only(
            'code', 'name', 'homologated_names', 'category', 'brand', 'returnable',
            'mililiters_per_unit', 'hectoliter_per_unit', 'cost_per_unit', 'box_units'
        )

        # Crear diccionario de lookup para productos compra (pre-calculado)
        product_compra_lookup = {}
        for p in products_compra:
            product_compra_lookup[str(p.code)] = {
                'code': str(p.code),
                'name': p.name,
                'name_homologated': p.homologated_names[0] if p.homologated_names else None,
                'category': p.category,
                'brand': p.brand,
                'returnable': 'RETORNABLE' if p.returnable else 'NO RETORNABLE',
                'mililiters_per_unit': float(p.mililiters_per_unit) if p.mililiters_per_unit else None,
                'hectoliter_per_unit': float(p.hectoliter_per_unit) if p.hectoliter_per_unit else None,
                'cost_per_unit': float(p.cost_per_unit) if p.cost_per_unit else None,
                'box_units': p.box_units
            }

        # Procesar todas las filas - TODOS se buscan en productos_app
        # Usar itertuples() en lugar de iterrows() para mejor rendimiento (10-100x más rápido)
        df['sku_str'] = df['sku'].astype(str)

        expanded_rows = []

        # Convertir a diccionario de columnas para acceso rápido
        df_dict = df.to_dict('records')
        total_rows = len(df_dict)

        for idx, row_dict in enumerate(df_dict, 1):
            # Mostrar progreso en desarrollo (cada 500 filas)
            if settings.DEBUG and idx % 500 == 0:
                print(
                    f"   ⏳ Procesando: {idx}/{total_rows} filas ({int(idx/total_rows*100)}%)")

            sku = str(row_dict['sku_str'])
            units = row_dict['units'] if not pd.isna(row_dict['units']) else 0
            orders = row_dict['orders'] if not pd.isna(
                row_dict['orders']) else 0

            # Buscar en productos App
            product_app = product_app_lookup.get(sku)

            if product_app:
                # Obtener materiales (TODOS los productos_app tienen materiales)
                materials = product_app.get_materials_with_quantities()

                if materials:
                    # Crear una fila por cada material
                    for material_obj, quantity in materials.items():
                        material_code = str(material_obj.code)
                        material = product_compra_lookup.get(material_code)

                        if material:
                            # Pre-calcular valores
                            quantity_float = float(quantity)
                            units_adjusted = units * quantity_float

                            hectoliter = material['hectoliter_per_unit']
                            cost = material['cost_per_unit']
                            box_units_value = material['box_units']

                            # Calcular métricas
                            venta_unitaria = units_adjusted * cost if cost else None
                            venta_pack = units_adjusted / \
                                box_units_value if box_units_value and box_units_value > 0 else None
                            hectolitros_sold = hectoliter * units_adjusted if hectoliter else None

                            # Crear nueva fila (copia optimizada)
                            new_row = row_dict.copy()
                            # Datos del producto padre (del Excel)
                            new_row['sku_padre'] = sku
                            new_row['nombre_padre'] = product_app.name
                            # Datos del material (de productos_compra) - ya pre-calculados
                            new_row['sku_vtex'] = material_code
                            new_row['name'] = material['name']
                            new_row['name_homologated'] = material['name_homologated']
                            new_row['category'] = material['category']
                            new_row['brand'] = material['brand']
                            # Ya viene formateado
                            new_row['retornable'] = material['returnable']
                            new_row['mililitros'] = material['mililiters_per_unit']
                            new_row['unidades_por_caja'] = box_units_value
                            new_row['units'] = units
                            new_row['orders'] = orders
                            new_row['units_assigned'] = quantity_float
                            new_row['units_per_sku'] = units_adjusted
                            new_row['venta_pack'] = venta_pack
                            new_row['hectolitros'] = hectolitros_sold
                            new_row['dolars'] = venta_unitaria

                            expanded_rows.append(new_row)
                        else:
                            # Material no encontrado en productos_compra
                            new_row = row_dict.copy()
                            new_row['sku_padre'] = sku
                            new_row['nombre_padre'] = product_app.name
                            new_row['sku_vtex'] = material_code
                            new_row['name'] = None
                            new_row['name_homologated'] = None
                            new_row['category'] = None
                            new_row['brand'] = None
                            new_row['retornable'] = None
                            new_row['mililitros'] = None
                            new_row['unidades_por_caja'] = None
                            new_row['units_assigned'] = None
                            new_row['units_per_sku'] = None
                            new_row['venta_pack'] = None
                            new_row['hectolitros'] = None
                            new_row['dolars'] = None
                            expanded_rows.append(new_row)
                else:
                    # Producto encontrado pero sin materiales (caso raro)
                    new_row = row_dict.copy()
                    new_row['sku_padre'] = sku
                    new_row['nombre_padre'] = product_app.name
                    new_row['sku_vtex'] = sku
                    new_row['name'] = None
                    new_row['name_homologated'] = None
                    new_row['category'] = None
                    new_row['brand'] = None
                    new_row['retornable'] = None
                    new_row['mililitros'] = None
                    new_row['unidades_por_caja'] = None
                    new_row['units_assigned'] = None
                    new_row['units_per_sku'] = None
                    new_row['venta_pack'] = None
                    new_row['hectolitros'] = None
                    new_row['dolars'] = None
                    expanded_rows.append(new_row)
            else:
                # SKU no encontrado en productos_app
                new_row = row_dict.copy()
                new_row['sku_padre'] = sku
                new_row['nombre_padre'] = None
                new_row['sku_vtex'] = sku
                new_row['name'] = None
                new_row['name_homologated'] = None
                new_row['category'] = None
                new_row['brand'] = None
                new_row['retornable'] = None
                new_row['mililitros'] = None
                new_row['unidades_por_caja'] = None
                new_row['units_assigned'] = None
                new_row['units_per_sku'] = None
                new_row['venta_pack'] = None
                new_row['hectolitros'] = None
                new_row['dolars'] = None
                expanded_rows.append(new_row)

        # Crear nuevo DataFrame con las filas expandidas
        if expanded_rows:
            expanded_df = pd.DataFrame(expanded_rows)
        else:
            expanded_df = df.copy()

        # Limpiar columna temporal
        if 'sku_str' in expanded_df.columns:
            expanded_df = expanded_df.drop('sku_str', axis=1)

        return expanded_df

    def _enrich_with_date_data(self, df):
        """
        Enriquecer el DataFrame con información de fechas.

        Args:
            df: DataFrame con columna date

        Returns:
            DataFrame enriquecido con datos de fecha
        """
        # Convertir la columna date a datetime
        df['date'] = pd.to_datetime(df['date'], errors='coerce')

        # Extraer componentes de fecha
        df['week'] = df['date'].dt.isocalendar().week
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.month
        df['day'] = df['date'].dt.day
        df['dayname'] = df['date'].dt.day_name()

        # Traducir nombres de días al español
        day_translation = {
            'Monday': 'Lunes',
            'Tuesday': 'Martes',
            'Wednesday': 'Miércoles',
            'Thursday': 'Jueves',
            'Friday': 'Viernes',
            'Saturday': 'Sábado',
            'Sunday': 'Domingo'
        }
        df['dayname'] = df['dayname'].map(day_translation)

        df['year_month'] = df['date'].dt.strftime('%Y-%m')

        # Convertir date de vuelta a string para el Excel
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')

        return df


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
        from django.db.models import Sum

        logs_queryset = SalesReportLog.objects.filter(
            date_filters, deleted_at__isnull=True)

        total_logs = logs_queryset.count()

        # Calcular tiempo total de procesamiento en segundos
        total_processing_time = logs_queryset.aggregate(
            total_seconds=Sum('processing_time_seconds'))['total_seconds'] or Decimal('0')

        # Obtener desglose por usuario (con tiempo de procesamiento)
        logs_by_user = logs_queryset.values(
            'user__email', 'user__first_name', 'user__last_name'
        ).annotate(
            count=Count('id'),
            total_seconds=Sum('processing_time_seconds')
        ).order_by('-count')

        # Convertir total_seconds a string para consistencia
        logs_by_user_list = list(logs_by_user)
        for user_log in logs_by_user_list:
            if user_log['total_seconds']:
                user_log['total_seconds'] = str(user_log['total_seconds'])

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

        # Calcular costo basado en TIEMPO DE PROCESAMIENTO (segundos)
        # El precio se interpreta como costo por segundo de procesamiento
        if price_instance and total_processing_time:
            unit_price = Decimal(str(price_instance.value)
                                 )  # precio por segundo
            total_cost = unit_price * total_processing_time
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
                'total_processing_time_seconds': str(total_processing_time),
                'app_name': APP_NAMES[APPS['SALES']],
                'app_price_name': app_price_name,
                'unit_price_per_second': str(unit_price),
                'total_cost': str(total_cost),
                'price_month': price_month,
                'pricing_model': 'per_second'
            },
            'breakdown': {
                'by_user': logs_by_user_list
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
                    'processing_time_seconds': str(log.processing_time_seconds) if log.processing_time_seconds else None,
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
