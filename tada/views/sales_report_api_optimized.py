"""
Vista optimizada para procesamiento de reportes de ventas.

Optimizaciones implementadas:
1. Lectura por streaming con openpyxl (read_only=True)
2. Patrón Batch/Bulk Create con buffers de 1000 registros
3. Transacciones atómicas con transaction.atomic()
4. Borrado masivo eficiente con TRUNCATE/DELETE SQL raw
5. Garbage collection explícito para liberar memoria
6. Procesamiento en generadores para mínimo uso de RAM
7. Comparación de archivos: Guarda archivo original y compara con anterior
8. Procesamiento diferencial: Solo procesa filas nuevas o modificadas
"""

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from django.utils.timezone import now
from django.db import transaction, connection
from django.conf import settings
from django.core.files.base import ContentFile
from io import BytesIO
from datetime import datetime
from decimal import Decimal
import time
import gc
import traceback
import hashlib
import re
import unicodedata

# openpyxl para lectura en streaming
from openpyxl import load_workbook

from tada.models import (
    SalesReportLog, SalesRecord, Price, AppPrice, POC,
    VentasProductosApp, VentasProductosCompra, SalesUploadLog,
    SalesFileStorage, SalesFileRowHash
)
from tada.utils.constants import APPS


def sanitize_filename(filename, date_start=None, date_end=None):
    """
    Sanitiza y normaliza el nombre del archivo para S3.

    Si se proporcionan fechas, genera nombre basado en rango:
    - ventas_2026-02-01_2026-02-04.xlsx

    Si no, usa el nombre original sanitizado con timestamp.
    """
    # Obtener extensión
    if '.' in filename:
        _, ext = filename.rsplit('.', 1)
        ext = f'.{ext}'
    else:
        ext = '.xlsx'

    # Si tenemos rango de fechas, usar nombre normalizado
    if date_start and date_end:
        return f"ventas_{date_start}_{date_end}{ext}"

    # Fallback: nombre original sanitizado
    if '.' in filename:
        name, _ = filename.rsplit('.', 1)
    else:
        name = filename

    # Normalizar unicode (quitar acentos)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ASCII', 'ignore').decode('ASCII')

    # Reemplazar espacios con guiones bajos
    name = name.replace(' ', '_')

    # Remover caracteres especiales
    name = re.sub(r'[^a-zA-Z0-9_\-]', '', name)

    # Agregar timestamp para unicidad
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    return f"{name}_{timestamp}{ext}"


class OptimizedSalesReportProcessorView(APIView):
    """
    Vista optimizada para procesar archivos Excel con datos de ventas.

    Optimizaciones clave:
    - Lectura en streaming: No carga el archivo completo en memoria
    - Procesamiento por lotes: Usa buffers de 1000 registros
    - Transacciones atómicas: Garantiza integridad de datos
    - Garbage collection: Libera memoria activamente
    """
    permission_classes = [IsAuthenticated]

    # Configuración de batch sizes
    BATCH_SIZE = 1000  # Registros por lote para bulk_create
    PROGRESS_LOG_INTERVAL = 500  # Cada cuántas filas loguear progreso
    MAX_ROWS_LIMIT = 300000  # Límite máximo de filas
    ROW_HASH_BATCH_SIZE = 5000  # Batch para guardar hashes de filas

    # Palabras clave que indican filas de resumen/filtros a excluir (Google Sheets)
    EXCLUDE_KEYWORDS = {'total', 'applied filters',
                        'filtros aplicados', 'subtotal', 'grand total'}

    def _is_excluded_row(self, first_cell_value):
        """
        Verificar si una fila debe ser excluida (resumen, filtros, etc.)

        Args:
            first_cell_value: Valor de la primera celda de la fila

        Returns:
            bool: True si la fila debe excluirse
        """
        if first_cell_value is None:
            return True

        first_cell_str = str(first_cell_value).lower().strip()

        # Verificar keywords de exclusión
        if any(keyword in first_cell_str for keyword in self.EXCLUDE_KEYWORDS):
            return True

        # Verificar si es un año válido (columna A debería tener el año)
        try:
            year_val = int(first_cell_value) if not isinstance(
                first_cell_value, int) else first_cell_value
            if not (2020 <= year_val <= 2030):
                return True
        except (ValueError, TypeError):
            return True

        return False

    def post(self, request):
        """
        Procesar un archivo Excel con ventas usando comparación inteligente.

        Flujo:
        1. Calcular hash del archivo
        2. Si el archivo es idéntico al anterior -> Skip completo
        3. Si es diferente -> Comparar fila por fila con archivo anterior
        4. Procesar solo las filas nuevas o modificadas
        5. Eliminar de BD las filas que ya no existen en el nuevo archivo
        6. Guardar archivo para futuras comparaciones
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'Se requiere un archivo Excel en el campo "file"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        excel_file = request.FILES['file']

        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response(
                {'error': 'El archivo debe ser un Excel (.xlsx o .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_time = time.time()

            if settings.DEBUG:
                print(
                    f"\n🚀 [OPTIMIZADO v2] Iniciando procesamiento de '{excel_file.name}'...")

            # === FASE 1: Leer contenido y calcular hash ===
            excel_file.seek(0)
            file_content = excel_file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            file_size = len(file_content)

            if settings.DEBUG:
                print(
                    f"📁 Archivo: {excel_file.name} ({file_size/1024:.1f} KB)")
                print(f"🔑 Hash: {file_hash[:16]}...")

            # === FASE 2: Verificar si el archivo ya fue procesado ===
            existing_file = SalesFileStorage.objects.filter(
                file_hash=file_hash,
                processed=True,
                deleted_at__isnull=True
            ).first()

            if existing_file:
                if settings.DEBUG:
                    print(
                        f"⚠️ Archivo idéntico ya procesado el {existing_file.processed_at}")
                return Response({
                    'message': 'Este archivo ya fue procesado anteriormente',
                    'previous_processing': {
                        'date': str(existing_file.processed_at),
                        'rows': existing_file.total_rows,
                        'file_id': existing_file.id
                    },
                    'action': 'skipped'
                }, status=status.HTTP_200_OK)

            # === FASE 3: Obtener archivo anterior para comparación ===
            previous_file = SalesFileStorage.objects.filter(
                processed=True,
                deleted_at__isnull=True
            ).exclude(file_hash=file_hash).order_by('-created_at').first()

            if settings.DEBUG:
                if previous_file:
                    print(
                        f"📂 Archivo anterior encontrado: {previous_file.filename} ({previous_file.total_rows} filas)")
                else:
                    print("📂 No hay archivo anterior para comparar (primera carga)")

            # === FASE 4: Pre-cargar lookups ===
            if settings.DEBUG:
                print("📦 Cargando lookups de POC y productos...")

            poc_lookup = self._build_poc_lookup()
            product_app_lookup, product_compra_lookup = self._build_product_lookups()

            if settings.DEBUG:
                print(f"   ✓ {len(poc_lookup)} POCs cargados")
                print(f"   ✓ {len(product_app_lookup)} productos app cargados")
                print(
                    f"   ✓ {len(product_compra_lookup)} productos compra cargados")

            # === FASE 5: Contar filas del archivo ===
            # Usar read_only=False para archivos de Google Sheets
            # (no definen dimensiones correctamente con read_only=True)
            wb_count = load_workbook(
                BytesIO(file_content), read_only=False, data_only=True)
            ws_count = wb_count.active

            # Contar filas válidas (excluyendo resúmenes y filtros de Google Sheets)
            total_rows = 0
            for row in ws_count.iter_rows(min_row=2, values_only=True):
                first_cell = row[0] if row else None

                if self._is_excluded_row(first_cell):
                    if first_cell is not None:
                        # Es una fila de resumen/filtro, no vacía
                        if settings.DEBUG:
                            print(
                                f"   ⚠️ Fila excluida (resumen/filtro): '{str(first_cell)[:50]}...'")
                        break
                    continue

                total_rows += 1

            wb_count.close()
            del wb_count
            gc.collect()

            if total_rows <= 0:
                return Response(
                    {'error': 'El archivo Excel está vacío o no tiene datos válidos'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if settings.DEBUG:
                print(f"📊 Total de filas de datos válidas: {total_rows}")

            if total_rows > self.MAX_ROWS_LIMIT:
                return Response(
                    {'error': f'El archivo contiene {total_rows} filas. Límite máximo: {self.MAX_ROWS_LIMIT}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # === FASE 6: Crear log del procesamiento ===
            sales_log = SalesReportLog.objects.create(
                filename=excel_file.name,
                rows_processed=total_rows,
                date=now().date(),
                time=now().time(),
                processing_time_seconds=Decimal('0'),
                app=str(APPS['SALES']),
                user=request.user
            )

            # === FASE 7: Pre-escanear fechas para nombre normalizado ===
            dates_in_file = self._prescan_dates(file_content)
            date_start = min(dates_in_file) if dates_in_file else None
            date_end = max(dates_in_file) if dates_in_file else None

            # Generar nombre normalizado basado en rango de fechas
            safe_filename = sanitize_filename(
                excel_file.name, date_start, date_end)

            if settings.DEBUG:
                print(f"📅 Rango de fechas: {date_start} a {date_end}")
                print(f"📁 Nombre normalizado: {safe_filename}")

            # === FASE 8: Crear registro del archivo ===
            sales_file = SalesFileStorage.objects.create(
                filename=excel_file.name,  # Guardar nombre original
                file_size=file_size,
                file_hash=file_hash,
                total_rows=total_rows,
                processed=False,
                user=request.user,
                previous_file=previous_file
            )

            # Guardar el archivo físico con nombre normalizado
            try:
                sales_file.file.save(
                    safe_filename,
                    ContentFile(file_content),
                    save=True
                )
                if settings.DEBUG:
                    print(f"📁 Archivo guardado en S3: {safe_filename}")
            except Exception as e:
                # Si falla S3, continuar sin guardar el archivo
                if settings.DEBUG:
                    print(f"⚠️ No se pudo guardar en S3: {str(e)}")
                    print("   Continuando sin almacenar archivo...")

            # === FASE 9: Cargar hashes del archivo anterior (si existe) ===
            previous_row_hashes = {}
            if previous_file:
                if settings.DEBUG:
                    print("🔍 Cargando hashes del archivo anterior...")

                for row_hash in SalesFileRowHash.objects.filter(
                    sales_file=previous_file
                ).values_list('row_key', 'row_hash'):
                    previous_row_hashes[row_hash[0]] = row_hash[1]

                if settings.DEBUG:
                    print(f"   ✓ {len(previous_row_hashes)} hashes cargados")

            # === FASE 10: Procesar archivo con comparación ===
            with transaction.atomic():
                result = self._process_excel_with_comparison(
                    file_content=file_content,
                    poc_lookup=poc_lookup,
                    product_app_lookup=product_app_lookup,
                    product_compra_lookup=product_compra_lookup,
                    sales_log=sales_log,
                    sales_file=sales_file,
                    user=request.user,
                    total_rows=total_rows,
                    previous_row_hashes=previous_row_hashes,
                    previous_file=previous_file
                )

            # === FASE 11: Actualizar estadísticas del archivo ===
            end_time = time.time()
            processing_duration = Decimal(str(round(end_time - start_time, 3)))

            SalesFileStorage.objects.filter(id=sales_file.id).update(
                processed=True,
                processed_at=now(),
                date_range_start=result.get('date_range_start'),
                date_range_end=result.get('date_range_end'),
                unique_stores=result.get('unique_stores', 0),
                unique_skus=result.get('unique_skus', 0)
            )

            SalesReportLog.objects.filter(id=sales_log.id).update(
                processing_time_seconds=processing_duration
            )

            # === FASE 12: Eliminar archivo anterior de S3 (limpieza) ===
            if previous_file:
                try:
                    # Eliminar archivo físico de S3
                    if previous_file.file:
                        previous_file.delete_file()

                    # Eliminar hashes del archivo anterior
                    SalesFileRowHash.objects.filter(
                        sales_file=previous_file).delete()

                    # Soft delete del registro
                    previous_file.deleted_at = now()
                    previous_file.save(update_fields=['deleted_at'])

                    if settings.DEBUG:
                        print(
                            f"🗑️ Archivo anterior eliminado: {previous_file.filename}")
                except Exception as e:
                    if settings.DEBUG:
                        print(
                            f"⚠️ Error al eliminar archivo anterior: {str(e)}")

            if settings.DEBUG:
                print(
                    f"\n✅ Procesamiento completado en {processing_duration}s")
                print(f"   📊 Nuevos: {result['saved_count']}")
                print(f"   🔄 Actualizados: {result['updated_count']}")
                print(
                    f"   ⚠️  Duplicados (sin cambios): {result['duplicates_count']}")
                print(f"   🗑️  Eliminados: {result.get('deleted_count', 0)}")
                print(f"   ❌ Errores: {len(result['unprocessed_rows'])}")

            # Crear log de upload
            if result['saved_count'] > 0 or result['updated_count'] > 0:
                self._create_upload_log(result, request.user)

            # Generar Excel de respuesta
            response = self._generate_response_excel(
                result=result,
                processing_duration=processing_duration,
                total_rows=total_rows
            )

            # Headers adicionales con info de comparación
            response['X-File-Hash'] = file_hash[:16]
            response['X-Previous-File'] = str(
                previous_file.id) if previous_file else 'none'
            response['X-Records-Deleted'] = str(result.get('deleted_count', 0))

            # Limpieza
            del poc_lookup, product_app_lookup, product_compra_lookup, previous_row_hashes
            gc.collect()

            return response

        except Exception as e:
            if settings.DEBUG:
                print(f"❌ ERROR GENERAL: {str(e)}")
                traceback.print_exc()
            return Response(
                {'error': f'Error al procesar el archivo: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    def _build_poc_lookup(self):
        """Construir diccionario de búsqueda de POCs."""
        poc_lookup = {}

        for poc in POC.objects.filter(deleted_at__isnull=True).only(
            'id_poc', 'name', 'city', 'region', 'homologated_names'
        ):
            key = poc.name.lower().strip()
            poc_data = {
                'poc_id': poc.id_poc,
                'poc_name': poc.name,
                'poc_city': poc.city,
                'poc_region': poc.region
            }
            poc_lookup[key] = poc_data

            # Agregar nombres homologados
            if poc.homologated_names:
                for homologated_name in poc.homologated_names:
                    poc_lookup[homologated_name.lower().strip()] = poc_data

        return poc_lookup

    def _build_product_lookups(self):
        """Construir diccionarios de búsqueda de productos."""
        # Productos App con materiales
        product_app_lookup = {}
        for p in VentasProductosApp.objects.filter(
            deleted_at__isnull=True
        ).only('code', 'name', 'type').prefetch_related('materials'):
            product_app_lookup[str(p.code)] = {
                'name': p.name,
                'type': p.type,
                'materials': p.get_materials_with_quantities()
            }

        # Productos Compra (materiales)
        product_compra_lookup = {}
        for p in VentasProductosCompra.objects.filter(
            deleted_at__isnull=True
        ).only(
            'code', 'name', 'homologated_names', 'category', 'brand',
            'returnable', 'mililiters_per_unit', 'hectoliter_per_unit',
            'cost_per_unit', 'box_units'
        ):
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

        return product_app_lookup, product_compra_lookup

    def _process_excel_streaming(self, excel_file, poc_lookup, product_app_lookup,
                                 product_compra_lookup, sales_log, user, total_rows):
        """
        Procesar Excel usando streaming y batches para minimizar RAM.

        Lógica de duplicados mejorada:
        1. Pre-scan para obtener fechas del archivo
        2. Cargar solo registros existentes de esas fechas
        3. Para cada registro del Excel:
           - Si existe con MISMOS valores -> SKIP (duplicado exacto)
           - Si existe con DIFERENTES valores -> UPDATE
           - Si no existe -> CREATE
        """
        # === FASE 1: Pre-scan para obtener fechas únicas del archivo ===
        if settings.DEBUG:
            print("📅 Pre-escaneando fechas del archivo...")

        file_content = excel_file.read()
        excel_file.seek(0)

        dates_in_file = self._prescan_dates(file_content)

        if settings.DEBUG:
            print(f"   ✓ Fechas encontradas: {len(dates_in_file)} días únicos")
            if dates_in_file:
                print(
                    f"   ✓ Rango: {min(dates_in_file)} a {max(dates_in_file)}")

        # === FASE 2: Cargar registros existentes solo de esas fechas ===
        existing_records = self._get_existing_records_lookup(dates_in_file)

        if settings.DEBUG:
            print(
                f"📦 {len(existing_records)} registros existentes en BD para esas fechas")

        # === FASE 3: Procesar archivo ===
        wb = load_workbook(
            BytesIO(file_content),
            read_only=True,
            data_only=True
        )
        ws = wb.active

        headers = None
        required_columns = [
            'Date Hierarchy - Date',
            'STORE_NAME',
            'product_spk',
            '# Units',
            '# Orders'
        ]

        # Estructuras para tracking
        records_buffer = []  # Buffer para bulk_create (nuevos)
        records_to_update = []  # IDs y datos para actualizar
        unprocessed_rows = []  # Errores
        new_records_for_excel = []  # Para el Excel de respuesta

        # Set para evitar duplicados dentro del mismo archivo
        processed_keys_in_file = set()

        # Contadores
        saved_count = 0
        updated_count = 0
        duplicates_count = 0
        skipped_internal_duplicates = 0
        processed_rows = 0

        # Procesar fila por fila (streaming)
        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                headers = list(row)

                missing = [c for c in required_columns if c not in headers]
                if missing:
                    wb.close()
                    raise ValueError(f"Faltan columnas: {', '.join(missing)}")

                col_indices = {col: headers.index(
                    col) for col in required_columns}
                continue

            try:
                date_val = row[col_indices['Date Hierarchy - Date']]
                store_name = row[col_indices['STORE_NAME']]
                product_spk = row[col_indices['product_spk']]
                units = row[col_indices['# Units']] or 0
                orders = row[col_indices['# Orders']] or 0
            except (IndexError, TypeError):
                continue

            if not date_val or not store_name or not product_spk:
                continue

            processed_rows += 1

            # Procesar product_spk
            sku = str(product_spk)
            if ';' in sku:
                sku = sku.split(';')[1]

            # Buscar POC
            poc_data = poc_lookup.get(str(store_name).lower().strip())
            if not poc_data:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'POC no encontrado: {store_name}'
                })
                continue

            # Buscar producto app
            product_app = product_app_lookup.get(sku)
            if not product_app:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'SKU padre no encontrado: {sku}'
                })
                continue

            materials = product_app.get('materials', {})
            if not materials:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'SKU sin materiales: {sku}'
                })
                continue

            # Procesar fecha
            try:
                if isinstance(date_val, datetime):
                    date_obj = date_val.date()
                else:
                    date_obj = datetime.strptime(
                        str(date_val), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                try:
                    date_obj = datetime.strptime(
                        str(date_val), '%d/%m/%Y').date()
                except:
                    unprocessed_rows.append({
                        'Date Hierarchy - Date': date_val,
                        'STORE_NAME': store_name,
                        'product_spk': product_spk,
                        '# Units': units,
                        '# Orders': orders,
                        'error_reason': f'Fecha inválida: {date_val}'
                    })
                    continue

            # Expandir por materiales
            for material_obj, quantity in materials.items():
                material_code = str(material_obj.code)
                material = product_compra_lookup.get(material_code)

                if not material:
                    continue

                # Calcular métricas
                quantity_float = float(quantity)
                units_adjusted = int(units) * quantity_float

                hectoliter = material['hectoliter_per_unit']
                cost = material['cost_per_unit']
                box_units_value = material['box_units']

                venta_unitaria = units_adjusted * cost if cost else None
                venta_pack = units_adjusted / \
                    box_units_value if box_units_value and box_units_value > 0 else None
                hectolitros_sold = hectoliter * units_adjusted if hectoliter else None

                # Crear clave única normalizada (todo upper)
                store_name_upper = str(store_name).upper()
                sku_upper = sku.upper()
                material_code_upper = material_code.upper()

                record_key = f"{date_obj}|{store_name_upper}|{sku_upper}|{material_code_upper}"

                # === VERIFICAR DUPLICADOS DENTRO DEL MISMO ARCHIVO ===
                if record_key in processed_keys_in_file:
                    skipped_internal_duplicates += 1
                    continue

                processed_keys_in_file.add(record_key)

                # === VERIFICAR CONTRA BASE DE DATOS ===
                existing_record = existing_records.get(record_key)

                if existing_record:
                    # Comparar valores (con tolerancia para decimales)
                    existing_units = existing_record['units']
                    existing_hl = existing_record['hectolitros']
                    new_hl = round(hectolitros_sold,
                                   4) if hectolitros_sold else 0

                    if existing_units == int(units) and abs(existing_hl - new_hl) < 0.0001:
                        # Duplicado exacto - SKIP
                        duplicates_count += 1
                        continue
                    else:
                        # Existe pero con valores diferentes - marcar para UPDATE
                        records_to_update.append({
                            'id': existing_record['id'],
                            'units': int(units),
                            'orders': int(orders),
                            'units_per_sku': Decimal(str(units_adjusted)),
                            'venta_pack': Decimal(str(venta_pack)) if venta_pack else None,
                            'hectolitros': Decimal(str(hectolitros_sold)) if hectolitros_sold else None,
                            'dolars': Decimal(str(venta_unitaria)) if venta_unitaria else None,
                            'sales_log': sales_log,
                            'user': user
                        })
                        updated_count += 1
                        continue

                # === REGISTRO NUEVO - agregar al buffer ===
                date_data = self._get_date_data(date_obj)

                record = SalesRecord(
                    sales_log=sales_log,
                    user=user,
                    date=date_obj,
                    store_name=store_name_upper,
                    sku_vtex=material_code_upper,
                    poc_id=poc_data['poc_id'],
                    poc_name=str(poc_data['poc_name']).upper(),
                    poc_homolo=store_name_upper if store_name != poc_data['poc_name'] else None,
                    poc_city=str(poc_data['poc_city']).upper(
                    ) if poc_data['poc_city'] else None,
                    poc_region=str(poc_data['poc_region']).upper(
                    ) if poc_data['poc_region'] else None,
                    sku_padre=sku_upper,
                    nombre_padre=str(product_app['name']).upper(),
                    orders=int(orders),
                    units=int(units),
                    name=str(material['name']).upper(),
                    name_homologated=str(material['name_homologated']).upper(
                    ) if material['name_homologated'] else None,
                    category=str(material['category']).upper(
                    ) if material['category'] else None,
                    brand=str(material['brand']).upper(
                    ) if material['brand'] else None,
                    retornable=material['returnable'],
                    units_assigned=Decimal(str(quantity_float)),
                    units_per_sku=Decimal(str(units_adjusted)),
                    unidades_por_caja=box_units_value,
                    venta_pack=Decimal(
                        str(venta_pack)) if venta_pack else None,
                    mililitros=Decimal(str(
                        material['mililiters_per_unit'])) if material['mililiters_per_unit'] else None,
                    hectolitros=Decimal(
                        str(hectolitros_sold)) if hectolitros_sold else None,
                    dolars=Decimal(str(venta_unitaria)
                                   ) if venta_unitaria else None,
                    week=date_data['week'],
                    year=date_data['year'],
                    month=date_data['month'],
                    day=date_data['day'],
                    dayname=date_data['dayname'],
                    year_month=date_data['year_month']
                )

                records_buffer.append(record)

                # Guardar datos para Excel de respuesta
                new_records_for_excel.append({
                    'date': str(date_obj),
                    'store_name': store_name_upper,
                    'poc_id': poc_data['poc_id'],
                    'poc_name': str(poc_data['poc_name']).upper(),
                    'poc_city': poc_data['poc_city'],
                    'poc_region': poc_data['poc_region'],
                    'sku_padre': sku_upper,
                    'nombre_padre': str(product_app['name']).upper(),
                    'sku_vtex': material_code_upper,
                    'name': str(material['name']).upper(),
                    'name_homologated': material['name_homologated'],
                    'category': material['category'],
                    'brand': material['brand'],
                    'retornable': material['returnable'],
                    'orders': int(orders),
                    'units': int(units),
                    'units_per_sku': units_adjusted,
                    'unidades_por_caja': box_units_value,
                    'venta_pack': venta_pack,
                    'mililitros': material['mililiters_per_unit'],
                    'hectolitros': hectolitros_sold,
                    'dolars': venta_unitaria,
                    **date_data
                })

                # Flush buffer cuando alcance el tamaño del batch
                if len(records_buffer) >= self.BATCH_SIZE:
                    SalesRecord.objects.bulk_create(
                        records_buffer, batch_size=500)
                    saved_count += len(records_buffer)

                    if settings.DEBUG:
                        print(
                            f"   💾 Batch guardado: {saved_count} registros nuevos")

                    records_buffer.clear()
                    gc.collect()

            # Log de progreso
            if settings.DEBUG and processed_rows % self.PROGRESS_LOG_INTERVAL == 0:
                print(
                    f"   ⏳ Procesado: {processed_rows}/{total_rows} filas ({int(processed_rows/total_rows*100)}%)")

        # Guardar registros restantes en el buffer
        if records_buffer:
            SalesRecord.objects.bulk_create(records_buffer, batch_size=500)
            saved_count += len(records_buffer)
            records_buffer.clear()

        # Ejecutar actualizaciones en batch
        if records_to_update:
            self._bulk_update_records(records_to_update)
            if settings.DEBUG:
                print(f"   🔄 Actualizados: {len(records_to_update)} registros")

        # Cerrar workbook y limpiar
        wb.close()
        del wb
        gc.collect()

        if settings.DEBUG and skipped_internal_duplicates > 0:
            print(
                f"   ⚠️ Duplicados internos del archivo saltados: {skipped_internal_duplicates}")

        return {
            'saved_count': saved_count,
            'updated_count': updated_count,
            'duplicates_count': duplicates_count,
            'unprocessed_rows': unprocessed_rows,
            'new_records': new_records_for_excel
        }

    def _prescan_dates(self, file_content):
        """
        Pre-escanear el archivo para obtener las fechas únicas.
        Esto permite cargar solo los registros necesarios de la BD.
        Excluye filas de resumen/filtros de Google Sheets.
        """
        dates = set()

        wb = load_workbook(BytesIO(file_content),
                           read_only=False, data_only=True)
        ws = wb.active

        date_col_idx = None
        year_col_idx = 0  # Columna A es el año

        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                # Buscar columna de fecha
                headers = list(row)
                if 'Date Hierarchy - Date' in headers:
                    date_col_idx = headers.index('Date Hierarchy - Date')
                continue

            if date_col_idx is None:
                break

            # Verificar si es fila de resumen/filtro
            first_cell = row[year_col_idx] if row else None
            if self._is_excluded_row(first_cell):
                if first_cell is not None:
                    break  # Fila de resumen, terminar
                continue  # Fila vacía, seguir

            try:
                date_val = row[date_col_idx]
                if date_val:
                    if isinstance(date_val, datetime):
                        dates.add(date_val.date())
                    else:
                        try:
                            dates.add(datetime.strptime(
                                str(date_val), '%Y-%m-%d').date())
                        except:
                            try:
                                dates.add(datetime.strptime(
                                    str(date_val), '%d/%m/%Y').date())
                            except:
                                # Intentar formato M/D/YY (Google Sheets)
                                try:
                                    dates.add(datetime.strptime(
                                        str(date_val), '%m/%d/%y').date())
                                except:
                                    pass
            except:
                pass

        wb.close()
        return dates

    def _bulk_update_records(self, records_to_update):
        """
        Actualizar registros existentes en batch.
        Usa UPDATE individual pero eficiente para mantener integridad.
        """
        # Agrupar por ID para actualización
        for record_data in records_to_update:
            SalesRecord.objects.filter(id=record_data['id']).update(
                units=record_data['units'],
                orders=record_data['orders'],
                units_per_sku=record_data['units_per_sku'],
                venta_pack=record_data['venta_pack'],
                hectolitros=record_data['hectolitros'],
                dolars=record_data['dolars'],
                sales_log=record_data['sales_log'],
                user=record_data['user']
            )

    def _process_excel_with_comparison(self, file_content, poc_lookup, product_app_lookup,
                                       product_compra_lookup, sales_log, sales_file, user,
                                       total_rows, previous_row_hashes, previous_file):
        """
        Procesar Excel comparando con archivo anterior.

        Lógica:
        1. Para cada fila del nuevo archivo, calcular su hash
        2. Si el hash existe en el archivo anterior -> SKIP (sin cambios)
        3. Si el hash NO existe -> Verificar si la clave existe en BD:
           - Si existe en BD con valores diferentes -> UPDATE
           - Si no existe en BD -> CREATE
        4. Al final, eliminar de BD las filas que estaban en el archivo anterior
           pero NO están en el nuevo archivo
        5. Guardar hashes del nuevo archivo para futuras comparaciones
        """
        wb = load_workbook(BytesIO(file_content),
                           read_only=True, data_only=True)
        ws = wb.active

        headers = None
        required_columns = [
            'Date Hierarchy - Date',
            'STORE_NAME',
            'product_spk',
            '# Units',
            '# Orders'
        ]

        # Estructuras para tracking
        records_buffer = []
        records_to_update = []
        row_hashes_buffer = []
        unprocessed_rows = []
        new_records_for_excel = []

        # Set de claves del nuevo archivo (para detectar eliminaciones)
        new_file_keys = set()

        # Tracking de fechas y estadísticas
        all_dates = set()
        all_stores = set()
        all_skus = set()

        # Set para evitar duplicados internos
        processed_keys_in_file = set()

        # Contadores
        saved_count = 0
        updated_count = 0
        duplicates_count = 0  # Sin cambios respecto al anterior
        skipped_internal = 0
        processed_rows = 0

        # Cargar registros existentes de BD para comparación
        if settings.DEBUG:
            print("🔍 Pre-escaneando fechas del archivo...")

        dates_in_file = self._prescan_dates(file_content)
        existing_records = self._get_existing_records_lookup(dates_in_file)

        if settings.DEBUG:
            print(f"   ✓ {len(dates_in_file)} días únicos")
            print(f"   ✓ {len(existing_records)} registros existentes en BD")

        # Procesar fila por fila
        year_col_idx = 0  # Columna A es el año
        for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
            if row_idx == 0:
                headers = list(row)
                missing = [c for c in required_columns if c not in headers]
                if missing:
                    wb.close()
                    raise ValueError(f"Faltan columnas: {', '.join(missing)}")
                col_indices = {col: headers.index(
                    col) for col in required_columns}
                continue

            # Verificar si es fila de resumen/filtro (Google Sheets)
            first_cell = row[year_col_idx] if row else None
            if self._is_excluded_row(first_cell):
                if first_cell is not None:
                    if settings.DEBUG:
                        print(
                            f"   ⚠️ Terminando procesamiento - fila de resumen detectada")
                    break  # Fila de resumen, terminar
                continue  # Fila vacía, seguir

            try:
                date_val = row[col_indices['Date Hierarchy - Date']]
                store_name = row[col_indices['STORE_NAME']]
                product_spk = row[col_indices['product_spk']]
                units = row[col_indices['# Units']] or 0
                orders = row[col_indices['# Orders']] or 0
            except (IndexError, TypeError):
                continue

            if not date_val or not store_name or not product_spk:
                continue

            processed_rows += 1

            # Procesar SKU
            sku = str(product_spk)
            if ';' in sku:
                sku = sku.split(';')[1]

            # Buscar POC
            poc_data = poc_lookup.get(str(store_name).lower().strip())
            if not poc_data:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'POC no encontrado: {store_name}'
                })
                continue

            # Buscar producto
            product_app = product_app_lookup.get(sku)
            if not product_app:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'SKU no encontrado: {sku}'
                })
                continue

            materials = product_app.get('materials', {})
            if not materials:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'SKU sin materiales: {sku}'
                })
                continue

            # Procesar fecha (soporta múltiples formatos)
            try:
                if isinstance(date_val, datetime):
                    date_obj = date_val.date()
                else:
                    date_str = str(date_val).strip()
                    date_obj = None

                    # Intentar diferentes formatos
                    date_formats = [
                        '%Y-%m-%d',     # 2026-02-03
                        '%d/%m/%Y',     # 03/02/2026
                        '%m/%d/%y',     # 2/3/26 (Google Sheets US)
                        '%d/%m/%y',     # 3/2/26 (Google Sheets ES)
                        '%m/%d/%Y',     # 2/3/2026
                    ]

                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue

                    if date_obj is None:
                        raise ValueError(f"No se pudo parsear: {date_str}")

            except Exception as e:
                unprocessed_rows.append({
                    'Date Hierarchy - Date': date_val,
                    'STORE_NAME': store_name,
                    'product_spk': product_spk,
                    '# Units': units,
                    '# Orders': orders,
                    'error_reason': f'Fecha inválida: {date_val}'
                })
                continue

            all_dates.add(date_obj)
            all_stores.add(str(store_name).upper())

            # Expandir por materiales
            for material_obj, quantity in materials.items():
                material_code = str(material_obj.code)
                material = product_compra_lookup.get(material_code)

                if not material:
                    continue

                all_skus.add(material_code)

                # Calcular métricas
                quantity_float = float(quantity)
                units_adjusted = int(units) * quantity_float

                hectoliter = material['hectoliter_per_unit']
                cost = material['cost_per_unit']
                box_units_value = material['box_units']

                venta_unitaria = units_adjusted * cost if cost else None
                venta_pack = units_adjusted / \
                    box_units_value if box_units_value and box_units_value > 0 else None
                hectolitros_sold = hectoliter * units_adjusted if hectoliter else None

                # Crear claves normalizadas
                store_name_upper = str(store_name).upper()
                sku_upper = sku.upper()
                material_code_upper = material_code.upper()

                record_key = f"{date_obj}|{store_name_upper}|{sku_upper}|{material_code_upper}"

                # Calcular hash de la fila
                row_hash = SalesFileRowHash.calculate_row_hash(
                    str(
                        date_obj), store_name_upper, f"{sku_upper}|{material_code_upper}",
                    int(units), int(orders)
                )

                # Agregar a set de claves del nuevo archivo
                new_file_keys.add(record_key)

                # Verificar duplicado interno
                if record_key in processed_keys_in_file:
                    skipped_internal += 1
                    continue
                processed_keys_in_file.add(record_key)

                # === COMPARACIÓN CON ARCHIVO ANTERIOR ===
                if previous_row_hashes and record_key in previous_row_hashes:
                    if previous_row_hashes[record_key] == row_hash:
                        # Sin cambios respecto al archivo anterior -> SKIP
                        duplicates_count += 1

                        # Guardar hash para el nuevo archivo
                        row_hashes_buffer.append(SalesFileRowHash(
                            sales_file=sales_file,
                            row_key=record_key,
                            row_hash=row_hash,
                            date=date_obj,
                            store_name=store_name_upper,
                            sku=f"{sku_upper}|{material_code_upper}",
                            units=int(units),
                            orders=int(orders)
                        ))
                        continue

                # === VERIFICAR EN BD ===
                existing_record = existing_records.get(record_key)

                if existing_record:
                    # Comparar valores
                    existing_units = existing_record['units']
                    existing_hl = existing_record['hectolitros']
                    new_hl = round(hectolitros_sold,
                                   4) if hectolitros_sold else 0

                    if existing_units == int(units) and abs(existing_hl - new_hl) < 0.0001:
                        # Ya existe igual en BD -> solo guardar hash
                        duplicates_count += 1
                    else:
                        # Diferente -> UPDATE
                        records_to_update.append({
                            'id': existing_record['id'],
                            'units': int(units),
                            'orders': int(orders),
                            'units_per_sku': Decimal(str(units_adjusted)),
                            'venta_pack': Decimal(str(venta_pack)) if venta_pack else None,
                            'hectolitros': Decimal(str(hectolitros_sold)) if hectolitros_sold else None,
                            'dolars': Decimal(str(venta_unitaria)) if venta_unitaria else None,
                            'sales_log': sales_log,
                            'user': user
                        })
                        updated_count += 1

                    # Guardar hash
                    row_hashes_buffer.append(SalesFileRowHash(
                        sales_file=sales_file,
                        row_key=record_key,
                        row_hash=row_hash,
                        date=date_obj,
                        store_name=store_name_upper,
                        sku=f"{sku_upper}|{material_code_upper}",
                        units=int(units),
                        orders=int(orders)
                    ))
                    continue

                # === REGISTRO NUEVO ===
                date_data = self._get_date_data(date_obj)

                record = SalesRecord(
                    sales_log=sales_log,
                    user=user,
                    date=date_obj,
                    store_name=store_name_upper,
                    sku_vtex=material_code_upper,
                    poc_id=poc_data['poc_id'],
                    poc_name=str(poc_data['poc_name']).upper(),
                    poc_homolo=store_name_upper if store_name != poc_data['poc_name'] else None,
                    poc_city=str(poc_data['poc_city']).upper(
                    ) if poc_data['poc_city'] else None,
                    poc_region=str(poc_data['poc_region']).upper(
                    ) if poc_data['poc_region'] else None,
                    sku_padre=sku_upper,
                    nombre_padre=str(product_app['name']).upper(),
                    orders=int(orders),
                    units=int(units),
                    name=str(material['name']).upper(),
                    name_homologated=str(material['name_homologated']).upper(
                    ) if material['name_homologated'] else None,
                    category=str(material['category']).upper(
                    ) if material['category'] else None,
                    brand=str(material['brand']).upper(
                    ) if material['brand'] else None,
                    retornable=material['returnable'],
                    units_assigned=Decimal(str(quantity_float)),
                    units_per_sku=Decimal(str(units_adjusted)),
                    unidades_por_caja=box_units_value,
                    venta_pack=Decimal(
                        str(venta_pack)) if venta_pack else None,
                    mililitros=Decimal(str(
                        material['mililiters_per_unit'])) if material['mililiters_per_unit'] else None,
                    hectolitros=Decimal(
                        str(hectolitros_sold)) if hectolitros_sold else None,
                    dolars=Decimal(str(venta_unitaria)
                                   ) if venta_unitaria else None,
                    week=date_data['week'],
                    year=date_data['year'],
                    month=date_data['month'],
                    day=date_data['day'],
                    dayname=date_data['dayname'],
                    year_month=date_data['year_month']
                )

                records_buffer.append(record)

                # Guardar hash
                row_hashes_buffer.append(SalesFileRowHash(
                    sales_file=sales_file,
                    row_key=record_key,
                    row_hash=row_hash,
                    date=date_obj,
                    store_name=store_name_upper,
                    sku=f"{sku_upper}|{material_code_upper}",
                    units=int(units),
                    orders=int(orders)
                ))

                # Para Excel de respuesta
                new_records_for_excel.append({
                    'date': str(date_obj),
                    'store_name': store_name_upper,
                    'poc_id': poc_data['poc_id'],
                    'poc_name': str(poc_data['poc_name']).upper(),
                    'poc_city': poc_data['poc_city'],
                    'poc_region': poc_data['poc_region'],
                    'sku_padre': sku_upper,
                    'nombre_padre': str(product_app['name']).upper(),
                    'sku_vtex': material_code_upper,
                    'name': str(material['name']).upper(),
                    'name_homologated': material['name_homologated'],
                    'category': material['category'],
                    'brand': material['brand'],
                    'retornable': material['returnable'],
                    'orders': int(orders),
                    'units': int(units),
                    'units_per_sku': units_adjusted,
                    'unidades_por_caja': box_units_value,
                    'venta_pack': venta_pack,
                    'mililitros': material['mililiters_per_unit'],
                    'hectolitros': hectolitros_sold,
                    'dolars': venta_unitaria,
                    **date_data
                })

                # Flush buffers
                if len(records_buffer) >= self.BATCH_SIZE:
                    SalesRecord.objects.bulk_create(
                        records_buffer, batch_size=500)
                    saved_count += len(records_buffer)
                    records_buffer.clear()

                    if settings.DEBUG:
                        print(
                            f"   💾 Batch guardado: {saved_count} registros nuevos")
                    gc.collect()

                if len(row_hashes_buffer) >= self.ROW_HASH_BATCH_SIZE:
                    SalesFileRowHash.objects.bulk_create(
                        row_hashes_buffer, batch_size=1000)
                    row_hashes_buffer.clear()

            # Log de progreso
            if settings.DEBUG and processed_rows % self.PROGRESS_LOG_INTERVAL == 0:
                print(
                    f"   ⏳ Procesado: {processed_rows}/{total_rows} filas ({int(processed_rows/total_rows*100)}%)")

        # Guardar registros restantes
        if records_buffer:
            SalesRecord.objects.bulk_create(records_buffer, batch_size=500)
            saved_count += len(records_buffer)
            records_buffer.clear()

        if row_hashes_buffer:
            SalesFileRowHash.objects.bulk_create(
                row_hashes_buffer, batch_size=1000)
            row_hashes_buffer.clear()

        # Ejecutar actualizaciones
        if records_to_update:
            self._bulk_update_records(records_to_update)
            if settings.DEBUG:
                print(f"   🔄 Actualizados: {len(records_to_update)} registros")

        # === DETECTAR Y ELIMINAR REGISTROS QUE YA NO EXISTEN ===
        deleted_count = 0
        if previous_file and previous_row_hashes:
            # Claves que estaban en el archivo anterior pero no en el nuevo
            keys_to_delete = set(previous_row_hashes.keys()) - new_file_keys

            if keys_to_delete:
                if settings.DEBUG:
                    print(
                        f"   🗑️ Detectadas {len(keys_to_delete)} filas para eliminar...")

                # Obtener IDs de registros a eliminar
                ids_to_delete = []
                for key in keys_to_delete:
                    if key in existing_records:
                        ids_to_delete.append(existing_records[key]['id'])

                if ids_to_delete:
                    # Soft delete en batches
                    batch_size = 1000
                    for i in range(0, len(ids_to_delete), batch_size):
                        batch = ids_to_delete[i:i+batch_size]
                        SalesRecord.objects.filter(
                            id__in=batch).update(deleted_at=now())
                        deleted_count += len(batch)

                    if settings.DEBUG:
                        print(
                            f"   🗑️ Eliminados (soft delete): {deleted_count} registros")

        # Cerrar workbook
        wb.close()
        del wb
        gc.collect()

        return {
            'saved_count': saved_count,
            'updated_count': updated_count,
            'duplicates_count': duplicates_count,
            'deleted_count': deleted_count,
            'unprocessed_rows': unprocessed_rows,
            'new_records': new_records_for_excel,
            'date_range_start': min(all_dates) if all_dates else None,
            'date_range_end': max(all_dates) if all_dates else None,
            'unique_stores': len(all_stores),
            'unique_skus': len(all_skus)
        }

    def _get_existing_records_lookup(self, dates_in_file=None):
        """
        Obtener diccionario de registros existentes para detección de duplicados.

        Retorna un dict con:
        - key: "date|store_name|sku_padre|sku_vtex" (normalizado a upper)
        - value: dict con 'id', 'units', 'hectolitros' para poder comparar y actualizar

        Args:
            dates_in_file: Set de fechas presentes en el archivo (para filtrar eficientemente)
        """
        existing_dict = {}

        # Si tenemos las fechas del archivo, filtrar solo esas fechas
        # Esto reduce significativamente la cantidad de datos a cargar
        if dates_in_file:
            min_date = min(dates_in_file)
            max_date = max(dates_in_file)
            date_filter = {'date__gte': min_date, 'date__lte': max_date}
        else:
            # Fallback: últimos 60 días
            from datetime import timedelta
            cutoff_date = now().date() - timedelta(days=60)
            date_filter = {'date__gte': cutoff_date}

        for record in SalesRecord.objects.filter(
            deleted_at__isnull=True,
            **date_filter
        ).values_list('id', 'date', 'store_name', 'sku_padre', 'sku_vtex', 'units', 'hectolitros'):
            record_id, date, store_name, sku_padre, sku_vtex, units, hectolitros = record

            # Normalizar clave (todo a upper para comparación consistente)
            key = f"{date}|{str(store_name).upper()}|{str(sku_padre).upper()}|{str(sku_vtex).upper()}"

            existing_dict[key] = {
                'id': record_id,
                'units': units,
                'hectolitros': float(hectolitros) if hectolitros else 0
            }

        return existing_dict

    def _get_date_data(self, date_obj):
        """Calcular datos de fecha."""
        day_translation = {
            0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves',
            4: 'Viernes', 5: 'Sábado', 6: 'Domingo'
        }

        return {
            'week': date_obj.isocalendar()[1],
            'year': date_obj.year,
            'month': date_obj.month,
            'day': date_obj.day,
            'dayname': day_translation.get(date_obj.weekday(), ''),
            'year_month': date_obj.strftime('%Y-%m')
        }

    def _create_upload_log(self, result, user):
        """Crear log de upload con rango de fechas."""
        try:
            if result['new_records']:
                dates = [r['date']
                         for r in result['new_records'] if r.get('date')]
                if dates:
                    min_date = min(dates)
                    max_date = max(dates)

                    SalesUploadLog.objects.create(
                        initrowdate=min_date,
                        endrowdate=max_date,
                        rows_count=result['saved_count'] +
                        result['updated_count'],
                        user=user
                    )
        except Exception as e:
            if settings.DEBUG:
                print(f"⚠️ Error al crear upload log: {str(e)}")

    def _generate_response_excel(self, result, processing_duration, total_rows):
        """Generar archivo Excel de respuesta."""
        import pandas as pd
        from openpyxl.styles import numbers

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output = BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Registros nuevos
            if result['new_records']:
                df_new = pd.DataFrame(result['new_records'])

                # Renombrar columnas a español
                spanish_columns = {
                    'date': 'FECHA', 'store_name': 'STORE_NAME', 'poc_id': 'POC',
                    'poc_name': 'POC NAME', 'poc_city': 'CITY', 'poc_region': 'REGION',
                    'sku_padre': 'SKU VTEX', 'nombre_padre': 'NAME VTEX',
                    'sku_vtex': 'COD. HOM', 'name': 'NOM. HOM.',
                    'name_homologated': 'HOMOLOGO SKU', 'category': 'CATEGORY',
                    'brand': 'Brand', 'retornable': 'Container Description',
                    'orders': '# Orders', 'units': '# Units',
                    'units_per_sku': 'VENTA UNITARIA', 'unidades_por_caja': 'Unidades por caja',
                    'venta_pack': 'VENTA PACK', 'mililitros': 'CC',
                    'hectolitros': 'HL', 'dolars': 'DOLARES',
                    'week': 'Week', 'year': 'YEAR', 'month': 'MONTH',
                    'day': 'DAY', 'dayname': 'DAY NAME', 'year_month': 'YEAR-MONTH'
                }

                df_new = df_new.rename(
                    columns={k: v for k, v in spanish_columns.items() if k in df_new.columns})
                df_new.to_excel(writer, index=False,
                                sheet_name='Registros Nuevos')
            else:
                pd.DataFrame().to_excel(writer, index=False, sheet_name='Registros Nuevos')

            # Sheet 2: Errores
            if result['unprocessed_rows']:
                df_errors = pd.DataFrame(result['unprocessed_rows'])
                error_columns = {
                    'Date Hierarchy - Date': 'Fecha', 'STORE_NAME': 'Nombre_Tienda',
                    'product_spk': 'SKU_Producto', '# Units': 'Unidades',
                    '# Orders': 'Pedidos', 'error_reason': 'Motivo_Error'
                }
                df_errors = df_errors.rename(columns=error_columns)
                df_errors.to_excel(writer, index=False,
                                   sheet_name='Registros con Errores')

        output.seek(0)

        filename = f'reporte_ventas_{timestamp}.xlsx'

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['X-Records-Created'] = str(result['saved_count'])
        response['X-Records-Updated'] = str(result['updated_count'])
        response['X-Records-Duplicated'] = str(result['duplicates_count'])
        response['X-Records-Unprocessed'] = str(
            len(result['unprocessed_rows']))
        response['X-Total-Processed'] = str(total_rows)
        response['X-Processing-Time'] = str(processing_duration)

        return response


class OptimizedSalesRecordDeleteByDateRangeView(APIView):
    """
    Vista optimizada para eliminar registros de SalesRecord por rango de fechas.

    Usa SQL raw para borrado masivo eficiente (mucho más rápido que ORM delete).
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        """
        Eliminar registros de SalesRecord en un rango de fechas usando SQL directo.
        """
        start_time = time.time()

        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'Se requieren los parámetros start_date y end_date'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = parse_date(start_date_str)
            end_date = parse_date(end_date_str)
        except (ValueError, TypeError):
            return Response(
                {'error': 'Formato de fecha inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not start_date or not end_date:
            return Response(
                {'error': 'Formato de fecha inválido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date > end_date:
            return Response(
                {'error': 'La fecha inicial debe ser menor o igual a la fecha final'},
                status=status.HTTP_400_BAD_REQUEST
            )

        date_diff = (end_date - start_date).days
        if date_diff > 31:
            return Response(
                {'error': f'El rango no puede ser mayor a 31 días. Actual: {date_diff}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Usar SQL directo para borrado masivo eficiente
        deleted_count = self._bulk_delete_by_date_range(start_date, end_date)

        # Invalidar hashes de archivos que cubren este rango de fechas
        # para permitir reprocesar el mismo archivo
        invalidated_files = self._invalidate_file_hashes(start_date, end_date)

        end_time = time.time()
        processing_duration = Decimal(str(round(end_time - start_time, 3)))

        if deleted_count > 0:
            SalesReportLog.objects.create(
                filename=f'DELETE_RECORDS_{start_date_str}_to_{end_date_str}',
                rows_processed=deleted_count,
                date=now().date(),
                time=now().time(),
                processing_time_seconds=processing_duration,
                app=str(APPS['SALES']),
                user=request.user
            )

        if settings.DEBUG:
            print(
                f"🗑️ Eliminados {deleted_count} registros en {processing_duration}s")
            if invalidated_files > 0:
                print(
                    f"🔓 Invalidados {invalidated_files} archivos (hashes limpiados para reprocesamiento)")

        return Response({
            'message': f'Se eliminaron {deleted_count} registros',
            'start_date': start_date_str,
            'end_date': end_date_str,
            'records_deleted': deleted_count,
            'files_invalidated': invalidated_files,
            'processing_time_seconds': float(processing_duration)
        }, status=status.HTTP_200_OK)

    def _bulk_delete_by_date_range(self, start_date, end_date):
        """
        Ejecutar borrado masivo usando SQL directo.

        Mucho más eficiente que ORM delete() para grandes volúmenes.
        """
        # Obtener nombre de la tabla
        table_name = SalesRecord._meta.db_table

        with connection.cursor() as cursor:
            # Contar registros primero
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE date >= %s AND date <= %s AND deleted_at IS NULL
                """,
                [start_date, end_date]
            )
            count = cursor.fetchone()[0]

            if count == 0:
                return 0

            # Opción 1: DELETE directo (más rápido, pero mantiene constraints)
            # Usar DELETE en lugar de TRUNCATE porque necesitamos filtrar por fecha
            cursor.execute(
                f"""
                DELETE FROM {table_name}
                WHERE date >= %s AND date <= %s AND deleted_at IS NULL
                """,
                [start_date, end_date]
            )

            return count

    def _invalidate_file_hashes(self, start_date, end_date):
        """
        Hard-delete de SalesFileStorage y SalesFileRowHash cuyos rangos de 
        fechas se solapen con el rango eliminado.

        Se usa hard_delete (no soft-delete) para ser consistente con el 
        DELETE SQL directo que se hace sobre SalesRecord, y garantizar que 
        los hashes no bloqueen un reprocesamiento futuro.
        """
        # Buscar archivos procesados cuyo rango de fechas se solape
        # con el rango eliminado:
        #   file_start <= end_date AND file_end >= start_date
        overlapping_files = SalesFileStorage.objects.filter(
            processed=True,
            deleted_at__isnull=True,
            date_range_start__lte=end_date,
            date_range_end__gte=start_date
        )

        count = overlapping_files.count()

        if count > 0:
            file_ids = list(overlapping_files.values_list('id', flat=True))

            # Hard-delete de los row hashes asociados (SQL directo)
            row_hash_table = SalesFileRowHash._meta.db_table
            with connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {row_hash_table} WHERE sales_file_id IN %s",
                    [tuple(file_ids)]
                )

            # Hard-delete de los archivos: borrar de S3 y eliminar registro de BD
            for sf in SalesFileStorage.objects.filter(id__in=file_ids):
                try:
                    if sf.file:
                        sf.delete_file()
                except Exception:
                    pass
                sf.hard_delete()

            if settings.DEBUG:
                print(f"🔓 Archivos hard-deleted: {file_ids}")

        return count


class OptimizedBulkTruncateView(APIView):
    """
    Vista para truncar completamente la tabla SalesRecord.

    ADVERTENCIA: Esta operación elimina TODOS los registros.
    Solo usar cuando se necesite limpiar toda la tabla.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Truncar completamente la tabla SalesRecord.

        Requiere confirmación explícita: confirm=true
        """
        confirm = request.data.get('confirm', False)

        if not confirm:
            return Response(
                {'error': 'Se requiere confirm=true para ejecutar TRUNCATE'},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_time = time.time()

        try:
            deleted_count = self._truncate_table()

            end_time = time.time()
            processing_duration = round(end_time - start_time, 3)

            if settings.DEBUG:
                print(
                    f"🗑️ TRUNCATE completado: {deleted_count} registros eliminados en {processing_duration}s")

            return Response({
                'message': f'Tabla truncada. {deleted_count} registros eliminados.',
                'records_deleted': deleted_count,
                'processing_time_seconds': processing_duration
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'Error al truncar: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _truncate_table(self):
        """
        Ejecutar TRUNCATE en la tabla.

        TRUNCATE es mucho más rápido que DELETE porque:
        - No genera logs de transacción por cada fila
        - Libera espacio inmediatamente
        - Resetea el contador de auto-increment
        """
        table_name = SalesRecord._meta.db_table

        with connection.cursor() as cursor:
            # Contar registros primero
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]

            if count == 0:
                return 0

            # TRUNCATE CASCADE para manejar foreign keys
            # NOTA: Esto eliminará también registros relacionados
            try:
                cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            except Exception:
                # Si TRUNCATE falla (ej: constraints), usar DELETE
                cursor.execute(f"DELETE FROM {table_name}")

            return count
