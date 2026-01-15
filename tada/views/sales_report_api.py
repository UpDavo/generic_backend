from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.http import HttpResponse
from django.db.models import Count, Q
from django.utils.dateparse import parse_date
from django.utils.timezone import now
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.conf import settings
from tada.models import SalesReportLog, SalesRecord, SalesRecordQueryLog, Price, AppPrice, POC, VentasProductosApp, VentasProductosCompra, SalesUploadLog
from tada.utils.constants import APPS, APP_NAMES
import numpy as np
import time


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
            
            # VALIDACIÓN: Advertir si hay demasiados registros
            if len(df) > 50000:
                if settings.DEBUG:
                    print(f"⚠️  ADVERTENCIA: {len(df)} filas a procesar. Esto puede tomar varios minutos.")
            
            # LÍMITE DE SEGURIDAD: Rechazar archivos extremadamente grandes
            if len(df) > 300000:
                return Response(
                    {'error': f'El archivo contiene {len(df)} filas. El límite máximo es 200,000 filas. Por favor, divida el archivo en partes más pequeñas.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Procesar los datos de ventas
            consolidated_df, unprocessed_df = self._process_sales_data(df)

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

            # Filtrar duplicados y obtener solo registros nuevos
            if settings.DEBUG:
                print(f"🔍 Filtrando duplicados...")
                print(f"   📊 Columnas del DF consolidado: {list(consolidated_df.columns)}")

            try:
                new_records_df, update_records_df, duplicates_count = self._filter_duplicates(
                    consolidated_df)

                if settings.DEBUG:
                    print(f"   ✓ {len(new_records_df)} registros nuevos")
                    print(f"   🔄 {len(update_records_df)} registros para actualizar")
                    print(f"   ⚠️  {duplicates_count} registros duplicados exactos (ignorados)")
            except Exception as e:
                if settings.DEBUG:
                    print(f"   ❌ ERROR en _filter_duplicates: {str(e)}")
                    import traceback
                    traceback.print_exc()
                raise

            # Guardar los registros nuevos en el histórico
            # Guardar registros nuevos y actualizar existentes
            saved_count = 0
            updated_count = 0
            
            if len(new_records_df) > 0:
                if settings.DEBUG:
                    print(
                        f"💾 Guardando {len(new_records_df)} registros nuevos en histórico...")

                try:
                    saved_count = self._save_to_history(
                        new_records_df, sales_log, request.user)

                    if settings.DEBUG:
                        print(
                            f"   ✓ {saved_count} registros guardados exitosamente")
                except Exception as e:
                    if settings.DEBUG:
                        print(f"   ❌ ERROR en _save_to_history: {str(e)}")
                        import traceback
                        traceback.print_exc()
                    raise
            
            if len(update_records_df) > 0:
                if settings.DEBUG:
                    print(
                        f"🔄 Actualizando {len(update_records_df)} registros existentes en histórico...")

                try:
                    updated_count = self._update_history(
                        update_records_df, sales_log, request.user)

                    if settings.DEBUG:
                        print(
                            f"   ✓ {updated_count} registros actualizados exitosamente")
                except Exception as e:
                    if settings.DEBUG:
                        print(f"   ❌ ERROR en _update_history: {str(e)}")
                        import traceback
                        traceback.print_exc()
                    raise

            # Crear log de upload con rango de fechas procesadas
            # Usar new_records_df y update_records_df que tienen los datos de fecha
            if (saved_count > 0 or updated_count > 0):
                try:
                    # Obtener rango de fechas de los datos procesados exitosamente
                    # Combinar new_records y update_records para obtener el rango completo
                    date_dfs = []
                    if len(new_records_df) > 0 and 'date' in new_records_df.columns:
                        date_dfs.append(new_records_df['date'])
                    if len(update_records_df) > 0 and 'date' in update_records_df.columns:
                        date_dfs.append(update_records_df['date'])
                    
                    if date_dfs:
                        all_dates = pd.concat(date_dfs)
                        min_date = pd.to_datetime(all_dates).min().date()
                        max_date = pd.to_datetime(all_dates).max().date()
                        
                        SalesUploadLog.objects.create(
                            initrowdate=min_date,
                            endrowdate=max_date,
                            rows_count=saved_count + updated_count,
                            user=request.user
                        )
                        
                        if settings.DEBUG:
                            print(f"📊 Upload log creado: desde {min_date} hasta {max_date}")
                except Exception as e:
                    # No fallar si la tabla no existe aún (migración pendiente)
                    if settings.DEBUG:
                        print(f"⚠️ Error al crear upload log (puede que falte migración): {str(e)}")

            # Generar archivo Excel de salida con múltiples sheets
            if settings.DEBUG:
                print(f"📝 Generando archivo Excel de salida...")
                
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output = BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # SHEET 1: Registros procesados (nuevos)
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
                    
                    # Crear copia para Excel con columnas en español
                    excel_df = new_records_df.copy()
                    columns_to_rename = {
                        k: v for k, v in spanish_columns.items() if k in excel_df.columns
                    }
                    excel_df = excel_df.rename(columns=columns_to_rename)
                    
                    excel_df.to_excel(
                        writer, index=False, sheet_name='Registros Nuevos')
                    
                    # SHEET 2: Registros con errores (si existen)
                    if len(unprocessed_df) > 0:
                        if settings.DEBUG:
                            print(f"   ⚠️  {len(unprocessed_df)} registros con errores - agregando sheet...")
                        
                        # Renombrar columnas del DataFrame de errores a español
                        error_columns = {
                            'Date Hierarchy - Date': 'Fecha',
                            'STORE_NAME': 'Nombre_Tienda',
                            'product_spk': 'SKU_Producto',
                            '# Units': 'Unidades',
                            '# Orders': 'Pedidos',
                            'error_reason': 'Motivo_Error'
                        }
                        
                        excel_errors_df = unprocessed_df.copy()
                        excel_errors_df = excel_errors_df.rename(columns=error_columns)
                        excel_errors_df.to_excel(
                            writer, index=False, sheet_name='Registros con Errores')

                output.seek(0)

                if settings.DEBUG:
                    print(f"   ✓ Archivo Excel generado correctamente")
                    if len(unprocessed_df) > 0:
                        print(f"   ✓ Incluye sheet con {len(unprocessed_df)} registros con errores")
                    
            except Exception as e:
                if settings.DEBUG:
                    print(f"   ❌ ERROR al generar Excel: {str(e)}")
                    import traceback
                    traceback.print_exc()
                raise

            # Generar nombre de archivo con timestamp
            filename = f'reporte_ventas_{timestamp}.xlsx'

            # Crear respuesta HTTP con el archivo Excel
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # Agregar headers con estadísticas del procesamiento
            response['X-Records-Created'] = str(saved_count)
            response['X-Records-Updated'] = str(updated_count)
            response['X-Records-Duplicated'] = str(duplicates_count)
            response['X-Records-Unprocessed'] = str(len(unprocessed_df))
            response['X-Total-Processed'] = str(len(df))
            response['X-Processing-Time'] = str(processing_duration)

            return response

        except Exception as e:
            if settings.DEBUG:
                print(f"❌ ERROR GENERAL: {str(e)}")
                import traceback
                traceback.print_exc()
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
        
        # Guardar las columnas originales para el reporte de errores
        # Esto permitirá mostrar los datos originales cuando un SKU no se procese
        consolidated_df['original_date'] = df['Date Hierarchy - Date']
        consolidated_df['original_store_name'] = df['STORE_NAME']
        consolidated_df['original_product_spk'] = df['product_spk']
        consolidated_df['original_units'] = df['# Units']
        consolidated_df['original_orders'] = df['# Orders']

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
        consolidated_df, unprocessed_poc_df = self._enrich_with_poc_data(consolidated_df)
        if settings.DEBUG and len(unprocessed_poc_df) > 0:
            print(f"   ⚠️  {len(unprocessed_poc_df)} registros sin POC encontrado")

        # Enriquecer datos con información de productos
        if settings.DEBUG:
            print(f"📦 Enriqueciendo datos de productos...")
        consolidated_df, unprocessed_products_df = self._enrich_with_product_data(consolidated_df)
        if settings.DEBUG:
            print(
                f"   ✓ {len(consolidated_df)} filas después de expansión de materiales")
            if len(unprocessed_products_df) > 0:
                print(f"   ⚠️  {len(unprocessed_products_df)} registros no se pudieron procesar")
        
        # Combinar los DataFrames de errores de POC y productos
        if len(unprocessed_poc_df) > 0 and len(unprocessed_products_df) > 0:
            unprocessed_df = pd.concat([unprocessed_poc_df, unprocessed_products_df], ignore_index=True)
        elif len(unprocessed_poc_df) > 0:
            unprocessed_df = unprocessed_poc_df
        else:
            unprocessed_df = unprocessed_products_df

        # Enriquecer datos con información de fechas
        if settings.DEBUG:
            print(f"📅 Enriqueciendo datos de fecha...")
        consolidated_df = self._enrich_with_date_data(consolidated_df)

        # Seleccionar solo las columnas finales (sin las columnas intermedias)
        final_columns = [
            # Datos originales
            'store_name',  # ← Columna original del Excel (requerida en modelo)
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

        # FILTRO DE SEGURIDAD: Eliminar registros con campos críticos None
        # Estos registros ya deberían estar en unprocessed_df, pero por si acaso
        # filtramos cualquier registro que no tenga POC, SKU padre o nombre de producto
        if settings.DEBUG:
            original_count = len(consolidated_df)
        
        # Filtrar registros que NO tengan campos críticos
        # Estos son registros que no pudieron ser procesados correctamente
        critical_columns = ['poc_name', 'sku_padre', 'name']
        for col in critical_columns:
            if col in consolidated_df.columns:
                consolidated_df = consolidated_df[consolidated_df[col].notna()]
        
        if settings.DEBUG and original_count != len(consolidated_df):
            removed_count = original_count - len(consolidated_df)
            print(f"⚠️ Se filtraron {removed_count} registros con datos incompletos")

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

        # NO renombrar columnas aquí - mantener en inglés para filtrado y guardado
        # El renombrado a español se hará solo para el Excel de salida
        
        # Retornar también DataFrame vacío de no procesados (se llenará en _enrich_with_product_data)
        return consolidated_df, pd.DataFrame()

    def _filter_duplicates(self, df):
        """
        Filtrar registros duplicados comparando con el histórico.

        Separa los registros en tres categorías:
        1. Completamente nuevos (no existe en BD)
        2. Para actualizar (existe con misma clave pero diferentes valores)
        3. Duplicados exactos (ignorar)

        Clave de identificación: (date, store_name, sku_padre, sku_vtex)
        Campos actualizables: units, hectolitros, orders, dolars, etc.

        Args:
            df: DataFrame con el consolidado procesado (en inglés, antes de renombrar)

        Returns:
            tuple: (DataFrame con registros nuevos, DataFrame con registros a actualizar, cantidad de duplicados exactos)
        """
        if len(df) == 0:
            return df, pd.DataFrame(), 0

        # Asegurarnos de que las columnas necesarias existen
        required_cols = ['date', 'store_name', 'sku_padre', 'sku_vtex']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            if settings.DEBUG:
                print(
                    f"⚠️ Columnas faltantes para filtro de duplicados: {missing_cols}")
            return df, pd.DataFrame(), 0

        # Convertir date a datetime para comparación
        df_check = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df_check['date']):
            df_check['date'] = pd.to_datetime(
                df_check['date'], errors='coerce')

        # OPTIMIZACIÓN 1: Obtener fechas únicas del DataFrame actual
        unique_dates = df_check['date'].dropna().dt.date.unique()

        if len(unique_dates) == 0:
            return df, pd.DataFrame(), 0

        if settings.DEBUG:
            print(
                f"   🔍 Buscando duplicados en {len(unique_dates)} fechas únicas...")

        # OPTIMIZACIÓN 2: Query filtrada - traer todos los datos del registro
        existing_records_query = SalesRecord.objects.filter(
            deleted_at__isnull=True,
            date__in=unique_dates
        ).values('id', 'date', 'store_name', 'sku_padre', 'sku_vtex', 'units', 'hectolitros', 'orders', 'dolars')

        # Crear estructuras:
        # 1. Dict con datos existentes por clave
        # 2. Set para verificar duplicados exactos
        existing_keys = {}  # key: (date, store_name, sku_padre, sku_vtex) -> value: {'id': X, 'units': Y, 'hectolitros': Z, ...}
        exact_duplicates = set()  # Set de hash completo para duplicados exactos
        
        for record in existing_records_query:
            key = (record['date'], record['store_name'], record['sku_padre'], record['sku_vtex'])
            existing_keys[key] = {
                'id': record['id'],
                'units': record['units'],
                'hectolitros': record['hectolitros'],
                'orders': record['orders'],
                'dolars': record['dolars']
            }
            # Hash completo para duplicados exactos (incluye valores numéricos principales)
            exact_key = f"{record['date']}|{record['store_name']}|{record['sku_padre']}|{record['sku_vtex']}|{record['units']}|{record['hectolitros'] or '0'}"
            exact_duplicates.add(exact_key)

        if settings.DEBUG and len(existing_keys) > 0:
            print(
                f"   📦 {len(existing_keys)} registros históricos en esas fechas")

        # Convertir date a string para comparación
        df_check['date_str'] = df_check['date'].dt.strftime('%Y-%m-%d')
        df_check['date_only'] = df_check['date'].dt.date

        # Crear hash de identificación (clave única de BD)
        df_check['_id_key'] = list(zip(
            df_check['date_only'],
            df_check['store_name'],
            df_check['sku_padre'],
            df_check['sku_vtex']
        ))

        # Crear hash completo (incluye units y hectolitros para detectar cambios)
        df_check['_full_key'] = (
            df_check['date_str'] + '|' +
            df_check['store_name'].astype(str) + '|' +
            df_check['sku_padre'].astype(str) + '|' +
            df_check['sku_vtex'].astype(str) + '|' +
            df_check['units'].astype(str) + '|' +
            df_check['hectolitros'].fillna(0).astype(str)
        )

        # Clasificar registros
        def classify_record(row):
            id_key = row['_id_key']
            full_key = row['_full_key']
            
            # Si el hash completo existe, es duplicado exacto
            if full_key in exact_duplicates:
                return 'exact_duplicate'
            
            # Si existe la clave pero con diferentes valores, necesita actualización
            if id_key in existing_keys:
                existing_data = existing_keys[id_key]
                current_units = row['units']
                current_hl = row['hectolitros']
                
                # Comparar valores principales (units y hectolitros)
                existing_units = existing_data['units'] or 0
                existing_hl = existing_data['hectolitros']
                existing_hl_val = float(existing_hl) if existing_hl is not None else 0.0
                current_hl_val = float(current_hl) if pd.notna(current_hl) else 0.0
                
                # Si algún valor cambió, es UPDATE
                if existing_units != current_units or abs(existing_hl_val - current_hl_val) > 0.001:
                    return 'update'
                else:
                    return 'exact_duplicate'
            
            # Si no existe, es nuevo
            return 'new'

        df_check['_classification'] = df_check.apply(classify_record, axis=1)

        # Separar DataFrames - mantener índices originales
        new_records_mask = df_check['_classification'] == 'new'
        update_records_mask = df_check['_classification'] == 'update'
        exact_duplicates_count = (df_check['_classification'] == 'exact_duplicate').sum()

        # Usar los índices para filtrar el DataFrame original
        new_records_df = df.loc[new_records_mask].copy()
        update_records_df = df.loc[update_records_mask].copy()
        
        # Agregar ID del registro a actualizar usando los índices
        if len(update_records_df) > 0:
            # Obtener las claves de ID de df_check para los registros que se van a actualizar
            update_keys = df_check.loc[update_records_mask, '_id_key']
            update_records_df['_existing_id'] = update_keys.map(
                lambda key: existing_keys[key]['id'] if key in existing_keys else None
            )

        return new_records_df, update_records_df, int(exact_duplicates_count)

    def _save_to_history(self, df, sales_log, user):
        """
        Guardar registros del DataFrame en el histórico (modelo SalesRecord).
        Procesa en chunks para manejar grandes volúmenes de datos.

        Args:
            df: DataFrame con registros a guardar (en inglés, antes de renombrar)
            sales_log: Instancia de SalesReportLog asociada
            user: Usuario que procesó el reporte

        Returns:
            int: Cantidad de registros guardados
        """
        if len(df) == 0:
            return 0
        
        total_rows = len(df)
        if settings.DEBUG:
            print(f"💾 Guardando {total_rows} registros en histórico...")
            if total_rows > 10000:
                print(f"   ⏱️  Esto puede tomar unos minutos...")

        # Convertir DataFrame a lista de objetos SalesRecord
        records_to_create = []

        # Función auxiliar para convertir valores NaN/None a None
        def safe_value(val):
            if pd.isna(val):
                return None
            return val

        # Función para convertir Decimal/float de pandas a Python
        def safe_decimal(val):
            if pd.isna(val):
                return None
            if isinstance(val, (np.integer, np.floating)):
                return Decimal(str(float(val)))
            return Decimal(str(val))

        def safe_int(val):
            if pd.isna(val):
                return None
            return int(val)

        def safe_str(val):
            if pd.isna(val):
                return None
            return str(val)

        # Convertir date a datetime.date si es string
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')

        # Iterar sobre el DataFrame y crear objetos
        for _, row in df.iterrows():
            record = SalesRecord(
                sales_log=sales_log,
                user=user,
                # Datos de identificación únicos
                date=row['date'].date() if pd.notna(row['date']) else None,
                store_name=safe_str(row.get('store_name')),
                sku_vtex=safe_str(row.get('sku_vtex')),
                # Datos de POC
                poc_id=safe_str(row.get('poc_id')),
                poc_name=safe_str(row.get('poc_name')),
                poc_homolo=safe_str(row.get('poc_homolo')),
                poc_city=safe_str(row.get('poc_city')),
                poc_region=safe_str(row.get('poc_region')),
                # Datos de producto padre
                sku_padre=safe_str(row.get('sku_padre')),
                nombre_padre=safe_str(row.get('nombre_padre')),
                # Datos de transacción
                orders=safe_int(row.get('orders', 0)),
                units=safe_int(row.get('units', 0)),
                # Datos de producto material
                name=safe_str(row.get('name')),
                name_homologated=safe_str(row.get('name_homologated')),
                category=safe_str(row.get('category')),
                brand=safe_str(row.get('brand')),
                retornable=safe_str(row.get('retornable')),
                # Métricas de ventas
                units_assigned=safe_decimal(row.get('units_assigned')),
                units_per_sku=safe_decimal(row.get('units_per_sku')),
                unidades_por_caja=safe_int(row.get('unidades_por_caja')),
                venta_pack=safe_decimal(row.get('venta_pack')),
                mililitros=safe_decimal(row.get('mililitros')),
                hectolitros=safe_decimal(row.get('hectolitros')),
                dolars=safe_decimal(row.get('dolars')),
                # Datos de fecha
                week=safe_int(row.get('week')),
                year=safe_int(row.get('year')),
                month=safe_int(row.get('month')),
                day=safe_int(row.get('day')),
                dayname=safe_str(row.get('dayname')),
                year_month=safe_str(row.get('year_month'))
            )
            records_to_create.append(record)

        # Guardar en batch para mejor rendimiento
        # Procesar en chunks para evitar problemas de memoria
        if records_to_create:
            total_saved = 0
            chunk_size = 1000  # Chunks más pequeños para mejor manejo de memoria
            total_chunks = (len(records_to_create) + chunk_size - 1) // chunk_size
            
            for i in range(0, len(records_to_create), chunk_size):
                chunk = records_to_create[i:i + chunk_size]
                SalesRecord.objects.bulk_create(chunk, batch_size=500)
                total_saved += len(chunk)
                
                if settings.DEBUG and total_chunks > 1:
                    current_chunk = (i // chunk_size) + 1
                    print(f"   📊 Progreso: {total_saved}/{len(records_to_create)} registros ({int(total_saved/len(records_to_create)*100)}%)")
            
            if settings.DEBUG:
                print(f"   ✅ {total_saved} registros insertados exitosamente")
            
            return total_saved

        return 0

    def _update_history(self, df, sales_log, user):
        """
        Actualizar registros existentes en el histórico (modelo SalesRecord).
        Se actualizan los campos numéricos cuando ya existe un registro con la misma clave.

        Args:
            df: DataFrame con registros a actualizar (debe incluir columna '_existing_id')
            sales_log: Instancia de SalesReportLog asociada
            user: Usuario que procesó el reporte

        Returns:
            int: Cantidad de registros actualizados
        """
        if len(df) == 0:
            return 0

        if '_existing_id' not in df.columns:
            if settings.DEBUG:
                print("   ⚠️ DataFrame no contiene columna '_existing_id', no se pueden actualizar registros")
            return 0

        # Función para convertir Decimal/float de pandas a Python
        def safe_decimal(val):
            if pd.isna(val):
                return None
            if isinstance(val, (np.integer, np.floating)):
                return Decimal(str(float(val)))
            return Decimal(str(val))
        
        def safe_int(val):
            if pd.isna(val):
                return None
            return int(val)

        updated_count = 0
        records_to_update = []

        # Obtener todos los IDs a actualizar
        existing_ids = df['_existing_id'].dropna().astype(int).tolist()
        
        if not existing_ids:
            if settings.DEBUG:
                print("   ⚠️ No hay IDs válidos para actualizar")
            return 0

        # Obtener registros existentes de la BD
        existing_records = {
            record.id: record 
            for record in SalesRecord.objects.filter(id__in=existing_ids)
        }

        if settings.DEBUG:
            print(f"   📊 Registros encontrados en BD: {len(existing_records)} de {len(existing_ids)} solicitados")

        # Iterar sobre el DataFrame y actualizar valores
        for _, row in df.iterrows():
            existing_id = int(row['_existing_id'])
            
            if existing_id not in existing_records:
                if settings.DEBUG:
                    print(f"   ⚠️ Registro ID {existing_id} no encontrado en BD, saltando...")
                continue

            record = existing_records[existing_id]
            
            # Nuevos valores
            new_units = safe_int(row.get('units'))
            new_hectolitros = safe_decimal(row.get('hectolitros'))
            new_orders = safe_int(row.get('orders'))
            new_dolars = safe_decimal(row.get('dolars'))
            
            # Verificar si algún valor cambió
            changed = False
            changes_detail = []
            
            if new_units is not None and record.units != new_units:
                changes_detail.append(f"units {record.units} → {new_units}")
                record.units = new_units
                changed = True
                
            if new_hectolitros is not None and record.hectolitros != new_hectolitros:
                changes_detail.append(f"HL {record.hectolitros} → {new_hectolitros}")
                record.hectolitros = new_hectolitros
                changed = True
                
            if new_orders is not None and record.orders != new_orders:
                changes_detail.append(f"orders {record.orders} → {new_orders}")
                record.orders = new_orders
                changed = True
                
            if new_dolars is not None and record.dolars != new_dolars:
                changes_detail.append(f"$ {record.dolars} → {new_dolars}")
                record.dolars = new_dolars
                changed = True
            
            if changed:
                records_to_update.append(record)
                
                if settings.DEBUG:
                    print(f"   🔄 Actualizando ID {existing_id}: {', '.join(changes_detail)}")

        # Realizar actualización en batch con chunks para grandes volúmenes
        if records_to_update:
            try:
                total_to_update = len(records_to_update)
                chunk_size = 1000
                total_updated = 0
                
                # Procesar en chunks
                for i in range(0, total_to_update, chunk_size):
                    chunk = records_to_update[i:i + chunk_size]
                    SalesRecord.objects.bulk_update(
                        chunk,
                        ['units', 'hectolitros', 'orders', 'dolars'],
                        batch_size=500
                    )
                    total_updated += len(chunk)
                    
                    if settings.DEBUG and total_to_update > chunk_size:
                        print(f"   📊 Progreso actualización: {total_updated}/{total_to_update} ({int(total_updated/total_to_update*100)}%)")
                
                updated_count = total_updated
                
                if settings.DEBUG:
                    print(f"   ✅ {updated_count} registros actualizados exitosamente")
            except Exception as e:
                if settings.DEBUG:
                    print(f"   ❌ Error al actualizar registros: {str(e)}")
                    import traceback
                    traceback.print_exc()
                raise

        return updated_count

    def _enrich_with_poc_data(self, df):
        """
        Enriquecer el DataFrame con información de POC.

        Args:
            df: DataFrame con columna store_name

        Returns:
            tuple: (DataFrame enriquecido con datos de POC, DataFrame con registros sin POC encontrado)
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

        # Función para buscar POC y marcar si no se encuentra
        def find_poc(store_name):
            if pd.isna(store_name):
                return pd.Series({
                    'poc_id': None,
                    'poc_name': None,
                    'poc_homolo': None,
                    'poc_city': None,
                    'poc_region': None,
                    '_poc_not_found': True  # Marcar como no encontrado
                })

            store_name_lower = str(store_name).lower().strip()
            poc_data = poc_lookup.get(store_name_lower)

            if poc_data:
                return pd.Series({
                    'poc_id': poc_data['poc_id'],
                    'poc_name': poc_data['poc_name'],
                    'poc_homolo': store_name if store_name != poc_data['poc_name'] else None,
                    'poc_city': poc_data['poc_city'],
                    'poc_region': poc_data['poc_region'],
                    '_poc_not_found': False
                })
            else:
                return pd.Series({
                    'poc_id': None,
                    'poc_name': None,
                    'poc_homolo': store_name,
                    'poc_city': None,
                    'poc_region': None,
                    '_poc_not_found': True  # Marcar como no encontrado
                })

        # Aplicar la búsqueda de POC
        poc_data = df['store_name'].apply(find_poc)
        df = pd.concat([df, poc_data], axis=1)
        
        # Separar registros sin POC encontrado
        if '_poc_not_found' in df.columns:
            poc_not_found_mask = df['_poc_not_found'] == True
            unprocessed_poc_df = df[poc_not_found_mask].copy()
            
            if len(unprocessed_poc_df) > 0:
                # Agregar columna de error
                unprocessed_poc_df['error_reason'] = unprocessed_poc_df['store_name'].apply(
                    lambda x: f'POC no encontrado: {x}' if pd.notna(x) else 'POC no encontrado: store_name vacío'
                )
                
                # Mapear a columnas originales del Excel si existen
                if 'original_date' in unprocessed_poc_df.columns:
                    unprocessed_poc_df['Date Hierarchy - Date'] = unprocessed_poc_df['original_date']
                    unprocessed_poc_df['STORE_NAME'] = unprocessed_poc_df['original_store_name']
                    unprocessed_poc_df['product_spk'] = unprocessed_poc_df['original_product_spk']
                    unprocessed_poc_df['# Units'] = unprocessed_poc_df['original_units']
                    unprocessed_poc_df['# Orders'] = unprocessed_poc_df['original_orders']
                    
                    unprocessed_poc_df = unprocessed_poc_df[[
                        'Date Hierarchy - Date', 'STORE_NAME', 'product_spk', 
                        '# Units', '# Orders', 'error_reason'
                    ]]
            
            # Filtrar registros con POC encontrado para continuar procesamiento
            df = df[~poc_not_found_mask].copy()
            df = df.drop('_poc_not_found', axis=1)
        else:
            unprocessed_poc_df = pd.DataFrame()

        return df, unprocessed_poc_df

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
            tuple: (DataFrame enriquecido con datos de productos, DataFrame con registros no procesados)
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
        unprocessed_rows = []  # Lista para registros no procesados

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
                            # Material no encontrado en productos_compra - REGISTRAR ERROR
                            error_row = row_dict.copy()
                            error_row['error_reason'] = f'SKU hijo (material) no encontrado: {material_code}'
                            unprocessed_rows.append(error_row)
                else:
                    # Producto encontrado pero sin materiales (caso raro) - REGISTRAR ERROR
                    error_row = row_dict.copy()
                    error_row['error_reason'] = f'SKU padre encontrado pero sin materiales asociados: {sku}'
                    unprocessed_rows.append(error_row)
            else:
                # SKU no encontrado en productos_app - REGISTRAR ERROR
                error_row = row_dict.copy()
                error_row['error_reason'] = f'SKU padre no encontrado en productos_app: {sku}'
                unprocessed_rows.append(error_row)

        # Crear nuevo DataFrame con las filas expandidas
        if expanded_rows:
            expanded_df = pd.DataFrame(expanded_rows)
        else:
            expanded_df = df.copy()

        # Limpiar columna temporal
        if 'sku_str' in expanded_df.columns:
            expanded_df = expanded_df.drop('sku_str', axis=1)
        
        # Crear DataFrame de registros no procesados (manteniendo columnas originales del Excel)
        if unprocessed_rows:
            unprocessed_df = pd.DataFrame(unprocessed_rows)
            
            # Mapear a las columnas originales del Excel
            if 'original_date' in unprocessed_df.columns:
                unprocessed_df['Date Hierarchy - Date'] = unprocessed_df['original_date']
                unprocessed_df['STORE_NAME'] = unprocessed_df['original_store_name']
                unprocessed_df['product_spk'] = unprocessed_df['original_product_spk']
                unprocessed_df['# Units'] = unprocessed_df['original_units']
                unprocessed_df['# Orders'] = unprocessed_df['original_orders']
                
                # Mantener solo las columnas originales del Excel + error_reason
                unprocessed_df = unprocessed_df[['Date Hierarchy - Date', 'STORE_NAME', 'product_spk', '# Units', '# Orders', 'error_reason']]
            else:
                # Fallback si no hay columnas originales
                original_columns = ['date', 'store_name', 'sku', 'units', 'orders']
                cols_to_keep = [col for col in original_columns if col in unprocessed_df.columns]
                cols_to_keep.append('error_reason')
                unprocessed_df = unprocessed_df[cols_to_keep]
        else:
            unprocessed_df = pd.DataFrame()

        return expanded_df, unprocessed_df

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

            # Contar registros devueltos para el log
            records_count = len(paginated_queryset) if paginated_queryset else 0

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

            # Crear log de la consulta
            try:
                SalesRecordQueryLog.objects.create(
                    query_type='list',
                    records_returned=records_count,
                    filters_applied={
                        'user_id': user_id,
                        'start_date': start_date,
                        'end_date': end_date,
                        'report_type': 'sales_report_logs'
                    },
                    date=now().date(),
                    time=now().time(),
                    app=str(APPS['SALES_CHECK']),
                    user=request.user
                )
            except Exception as log_error:
                # No fallar la operación si falla el log
                if settings.DEBUG:
                    print(f"⚠️ Error creando log de consulta: {str(log_error)}")

            # Retornar respuesta paginada
            return paginator.get_paginated_response(results)

        except Exception as e:
            print(f"❌ Error obteniendo logs de sales reports: {str(e)}")
            return Response({
                "error": "Error obteniendo logs de sales reports",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesRecordHistoryStatsView(APIView):
    """
    Vista para obtener estadísticas de consultas al histórico de ventas (SalesRecordQueryLog).
    Calcula costos basados en la cantidad de registros consultados/descargados.
    """
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
        Obtener estadísticas de consultas al histórico con pricing.

        Query params opcionales:
        - start_date: Fecha inicial (YYYY-MM-DD)
        - end_date: Fecha final (YYYY-MM-DD)
        - user_id: Filtrar por usuario específico
        - query_type: Filtrar por tipo (list/download)
        """
        from django.db.models import Sum

        # Obtener parámetros de filtro
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        user_id = request.query_params.get('user_id')
        query_type = request.query_params.get('query_type')

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

        if query_type:
            date_filters &= Q(query_type=query_type)

        # Obtener estadísticas de SalesRecordQueryLog
        logs_queryset = SalesRecordQueryLog.objects.filter(
            date_filters, deleted_at__isnull=True)

        total_queries = logs_queryset.count()

        # Calcular total de registros devueltos en todas las consultas
        total_records_returned = logs_queryset.aggregate(
            total_records=Sum('records_returned'))['total_records'] or 0

        # Desglose por usuario
        logs_by_user = logs_queryset.values(
            'user__email', 'user__first_name', 'user__last_name'
        ).annotate(
            query_count=Count('id'),
            total_records=Sum('records_returned')
        ).order_by('-total_records')

        # Desglose por tipo de consulta
        logs_by_type = logs_queryset.values('query_type').annotate(
            query_count=Count('id'),
            total_records=Sum('records_returned')
        ).order_by('-total_records')

        # Obtener precio para la app SALES_CHECK según el período
        price_instance = self._get_price_for_period(
            str(APPS['SALES_CHECK']), start_date, end_date)

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

        # Calcular costo basado en CANTIDAD DE CONSULTAS
        # El precio se interpreta como costo por consulta
        if price_instance and total_queries:
            unit_price = Decimal(str(price_instance.value))  # precio por consulta
            total_cost = unit_price * Decimal(str(total_queries))
            price_month = price_instance.month.strftime('%Y-%m')
        else:
            unit_price = Decimal('0')
            total_cost = Decimal('0')
            price_month = None

        return Response({
            'app_type': 'SALES_CHECK',
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'user_id': user_id,
                'query_type': query_type
            },
            'summary': {
                'total_queries': total_queries,
                'total_records_returned': total_records_returned,
                'app_name': APP_NAMES[APPS['SALES_CHECK']],
                'app_price_name': app_price_name,
                'unit_price_per_query': str(unit_price),
                'total_cost': str(total_cost),
                'price_month': price_month,
                'pricing_model': 'per_query'
            },
            'breakdown': {
                'by_user': list(logs_by_user),
                'by_query_type': list(logs_by_type)
            }
        }, status=status.HTTP_200_OK)


class SalesRecordHistoryListView(APIView):
    """
    Vista para listar el histórico de ventas (SalesRecord) con paginación.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        Obtiene la lista de registros de ventas con paginación.

        Query params opcionales:
        - start_date: Fecha inicial (YYYY-MM-DD)
        - end_date: Fecha final (YYYY-MM-DD)
        - poc_name: Filtrar por nombre de POC (búsqueda parcial)
        - sku_vtex: Filtrar por SKU exacto
        - page: Número de página (por defecto: 1)
        - page_size: Tamaño de página (por defecto: 20, máximo: 100)
        """
        try:
            # Obtener parámetros de filtro
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            poc_name = request.query_params.get('poc_name')
            sku_vtex = request.query_params.get('sku_vtex')

            # Construir query base
            queryset = SalesRecord.objects.filter(
                deleted_at__isnull=True
            ).order_by('-date', '-created_at')

            # Aplicar filtros
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

            if poc_name:
                queryset = queryset.filter(poc_name__icontains=poc_name)

            if sku_vtex:
                queryset = queryset.filter(sku_vtex=sku_vtex)

            # Configurar paginación con tamaño personalizado
            paginator = self.pagination_class()
            page_size = request.query_params.get('page_size', 20)
            try:
                # Máximo 100 registros por página
                page_size = min(int(page_size), 100)
            except (ValueError, TypeError):
                page_size = 20

            paginator.page_size = page_size
            paginated_queryset = paginator.paginate_queryset(queryset, request)

            # Contar registros devueltos para el log
            records_count = len(paginated_queryset) if paginated_queryset else 0

            # Serializar resultados
            results = []
            for record in paginated_queryset:
                results.append({
                    'id': record.id,
                    'date': record.date.strftime('%Y-%m-%d'),
                    'store_name': record.store_name,
                    'poc_id': record.poc_id,
                    'poc_name': record.poc_name,
                    'poc_homolo': record.poc_homolo,
                    'poc_city': record.poc_city,
                    'poc_region': record.poc_region,
                    'sku_padre': record.sku_padre,
                    'nombre_padre': record.nombre_padre,
                    'sku_vtex': record.sku_vtex,
                    'name': record.name,
                    'name_homologated': record.name_homologated,
                    'category': record.category,
                    'brand': record.brand,
                    'retornable': record.retornable,
                    'orders': record.orders,
                    'units': record.units,
                    'units_assigned': float(record.units_assigned) if record.units_assigned else None,
                    'units_per_sku': float(record.units_per_sku) if record.units_per_sku else None,
                    'unidades_por_caja': float(record.unidades_por_caja) if record.unidades_por_caja else None,
                    'venta_pack': record.venta_pack,
                    'mililitros': float(record.mililitros) if record.mililitros else None,
                    'hectolitros': float(record.hectolitros) if record.hectolitros else None,
                    'dolars': float(record.dolars) if record.dolars else None,
                    'week': record.week,
                    'year': record.year,
                    'month': record.month,
                    'day': record.day,
                    'dayname': record.dayname,
                    'year_month': record.year_month,
                    'created_at': record.created_at.isoformat()
                })

            # Crear log de la consulta
            try:
                SalesRecordQueryLog.objects.create(
                    query_type='list',
                    records_returned=records_count,
                    filters_applied={
                        'start_date': start_date,
                        'end_date': end_date,
                        'poc_name': poc_name,
                        'sku_vtex': sku_vtex,
                        'page_size': page_size
                    },
                    date=now().date(),
                    time=now().time(),
                    app=str(APPS['SALES_CHECK']),
                    user=request.user
                )
            except Exception as log_error:
                # No fallar la operación si falla el log
                if settings.DEBUG:
                    print(f"⚠️ Error creando log de consulta: {str(log_error)}")

            # Retornar respuesta paginada
            return paginator.get_paginated_response(results)

        except Exception as e:
            print(f"❌ Error obteniendo registros de ventas: {str(e)}")
            return Response({
                "error": "Error obteniendo registros de ventas",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SalesRecordHistoryDownloadView(APIView):
    """
    Vista para descargar el histórico de ventas (SalesRecord) en Excel filtrado por fechas.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar histórico de ventas en Excel filtrado por fechas y otros criterios.

        Query params:
        - start_date: Fecha inicial (YYYY-MM-DD) - opcional
        - end_date: Fecha final (YYYY-MM-DD) - opcional
        - poc_name: Filtrar por nombre de POC (búsqueda parcial) - opcional
        - sku_vtex: Filtrar por SKU exacto - opcional

        Si no se proporcionan fechas, descarga todos los registros (no recomendado para grandes volúmenes).
        """
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        poc_name = request.query_params.get('poc_name')
        sku_vtex = request.query_params.get('sku_vtex')

        # Construir query base
        queryset = SalesRecord.objects.filter(deleted_at__isnull=True)

        # Aplicar filtros de fecha
        if start_date:
            try:
                start_date_obj = parse_date(start_date)
                if start_date_obj:
                    queryset = queryset.filter(date__gte=start_date_obj)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Formato de start_date inválido. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if end_date:
            try:
                end_date_obj = parse_date(end_date)
                if end_date_obj:
                    queryset = queryset.filter(date__lte=end_date_obj)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Formato de end_date inválido. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Aplicar filtros adicionales
        if poc_name:
            queryset = queryset.filter(poc_name__icontains=poc_name)

        if sku_vtex:
            queryset = queryset.filter(sku_vtex=sku_vtex)

        # Ordenar por fecha
        queryset = queryset.order_by('date', 'poc_name', 'sku_vtex')

        # Limitar resultados para evitar timeouts (máximo 100,000 registros)
        total_count = queryset.count()
        if total_count > 100000:
            return Response(
                {
                    'error': f'Demasiados registros ({total_count}). Por favor, use un rango de fechas más específico.',
                    'suggestion': 'Intente filtrar por un máximo de 30 días'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if total_count == 0:
            return Response(
                {'error': 'No se encontraron registros para el rango de fechas especificado'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Obtener datos optimizados (solo campos necesarios)
        records = queryset.values(
            'date',
            'store_name',
            'poc_id',
            'poc_name',
            'poc_homolo',
            'poc_city',
            'poc_region',
            'sku_padre',
            'nombre_padre',
            'sku_vtex',
            'name',
            'name_homologated',
            'category',
            'brand',
            'retornable',
            'orders',
            'units',
            'units_assigned',
            'units_per_sku',
            'unidades_por_caja',
            'venta_pack',
            'mililitros',
            'hectolitros',
            'dolars',
            'week',
            'year',
            'month',
            'day',
            'dayname',
            'year_month'
        )

        # Convertir a DataFrame
        df = pd.DataFrame(list(records))

        if df.empty:
            return Response(
                {'error': 'No se encontraron registros'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Renombrar columnas a español
        df = df.rename(columns={
            'date': 'fecha',
            'store_name': 'tienda_original',
            'poc_id': 'id_poc',
            'poc_name': 'nombre_poc',
            'poc_homolo': 'poc_homologado',
            'poc_city': 'ciudad_poc',
            'poc_region': 'region_poc',
            'orders': 'pedidos',
            'units': 'unidades',
            'units_assigned': 'unidades_asignadas',
            'units_per_sku': 'unidades_por_sku',
            'dolars': 'dolares',
            'week': 'semana',
            'year': 'año',
            'month': 'mes',
            'day': 'dia',
            'dayname': 'nombre_dia',
            'year_month': 'año_mes',
            'name': 'nombre',
            'name_homologated': 'nombre_homologado',
            'category': 'categoria',
            'brand': 'marca'
        })

        # Crear log de la descarga con tipo SALES_CHECK
        try:
            SalesRecordQueryLog.objects.create(
                query_type='download',
                records_returned=len(df),
                filters_applied={
                    'start_date': start_date,
                    'end_date': end_date,
                    'poc_name': poc_name,
                    'sku_vtex': sku_vtex
                },
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                user=request.user
            )
        except Exception as e:
            # No fallar la descarga si no se puede crear el log
            if settings.DEBUG:
                print(f"⚠️ No se pudo crear log de descarga: {str(e)}")

        # Generar archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Histórico Ventas')

            # Obtener worksheet para formato
            worksheet = writer.sheets['Histórico Ventas']

            # Auto-ajustar ancho de columnas
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        output.seek(0)

        # Generar nombre de archivo con timestamp y rango de fechas
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        date_range = ''
        if start_date and end_date:
            date_range = f'_{start_date}_a_{end_date}'
        elif start_date:
            date_range = f'_desde_{start_date}'
        elif end_date:
            date_range = f'_hasta_{end_date}'

        filename = f'historico_ventas{date_range}_{timestamp}.xlsx'

        # Crear respuesta HTTP con el archivo Excel
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response


class SalesUploadLogView(APIView):
    """
    Endpoint para consultar el último upload de ventas.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener información del último upload de ventas.
        
        Returns:
            {
                "last_upload": {
                    "date_processed": "2026-01-15T14:30:00Z",
                    "initrowdate": "2026-01-01",
                    "endrowdate": "2026-01-05",
                    "rows_count": 1500,
                    "user": "john.doe@example.com"
                }
            }
        """
        last_upload = SalesUploadLog.objects.filter(
            deleted_at__isnull=True
        ).select_related('user').first()

        if not last_upload:
            return Response(
                {
                    "last_upload": None,
                    "message": "No se han registrado uploads de ventas"
                },
                status=status.HTTP_200_OK
            )

        return Response(
            {
                "last_upload": {
                    "id": last_upload.id,
                    "date_processed": last_upload.date_processed,
                    "initrowdate": last_upload.initrowdate,
                    "endrowdate": last_upload.endrowdate,
                    "rows_count": last_upload.rows_count,
                    "user": last_upload.user.email if last_upload.user else None
                }
            },
            status=status.HTTP_200_OK
        )
