"""
Servicio para procesar inventario teórico por POC y generar reporte de cobertura.

Lógica:
  - Lee 3 hojas del Excel: Inventario PT, Inventario EN, Pedido
  - Cruza con SalesRecord del mes para calcular ventas, HLS y días de inventario
  - Calcula LIMITE GARANTÍA = min(10000, ventas_mes)
  - Calcula Cobertura = LIMITE / Total Costo
  - Genera Excel de salida con 2 hojas: Resumen por POC y Días de Inventario
"""

import calendar
import gc
from decimal import Decimal
from io import BytesIO

from django.db.models import Sum
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from tada.models import SalesRecord
from tada.models.poc import POC
from tada.models.ventasProductosCompra import VentasProductosCompra

GARANTIA_LIMITE_MAXIMO = 10000.0

REQUIRED_SHEETS = {'Inventario PT', 'Inventario EN', 'Pedido'}


def _to_float(val, default=0.0):
    """Convierte cualquier valor de celda (int/float/Decimal/str/None) a float."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _to_str(val):
    """Convierte un valor a string limpio; None → ''."""
    if val is None:
        return ''
    return str(val).strip()


class TeoricInventoryService:

    # -------------------------------------------------------------------------
    # Punto de entrada
    # -------------------------------------------------------------------------

    def process(self, file_content: bytes, year: int, month: int) -> BytesIO:
        """
        Procesa el archivo Excel y devuelve un BytesIO con el Excel de resultados.

        Args:
            file_content: bytes del archivo Excel subido
            year: año del período de ventas
            month: mes del período de ventas

        Returns:
            BytesIO con el Excel de salida listo para descargar
        """
        wb = load_workbook(BytesIO(file_content), read_only=True, data_only=True)

        missing = REQUIRED_SHEETS - set(wb.sheetnames)
        if missing:
            wb.close()
            raise ValueError(
                f"El archivo no contiene las hojas requeridas: {', '.join(sorted(missing))}. "
                f"Hojas encontradas: {', '.join(wb.sheetnames)}"
            )

        try:
            pt_rows = self._parse_inventario_pt(wb['Inventario PT'])
            en_rows = self._parse_inventario_en(wb['Inventario EN'])
            pedido_rows = self._parse_pedido(wb['Pedido'])
        finally:
            wb.close()
            del wb
            gc.collect()

        # Recopilar IDs y códigos únicos para las queries
        poc_ids = set()
        for r in pt_rows:
            poc_ids.add(r['poc_id'])
        for r in en_rows:
            poc_ids.add(r['poc_id'])
        for r in pedido_rows:
            if r['poc_id']:
                poc_ids.add(r['poc_id'])

        mat_codes = {r['cod_material'] for r in pedido_rows if r['cod_material']}

        # Queries a la DB
        compra_lookup = self._build_productos_compra_lookup(mat_codes)
        sales_agg = self._build_sales_record_aggregates(year, month, poc_ids)
        poc_lookup = self._build_poc_lookup(poc_ids)

        total_rows = len(pt_rows) + len(en_rows) + len(pedido_rows)

        # Cómputos de negocio
        summary_rows = self._compute_poc_summary(
            pt_rows, en_rows, pedido_rows, compra_lookup, sales_agg, poc_lookup
        )
        detail_rows = self._compute_sku_detail(pt_rows, sales_agg, poc_lookup, year, month)

        return self._build_output_excel(summary_rows, detail_rows), total_rows

    # -------------------------------------------------------------------------
    # Parseo del Excel de entrada
    # -------------------------------------------------------------------------

    def _parse_inventario_pt(self, ws) -> list:
        """
        Parsea la hoja 'Inventario PT'.

        Estructura (col A siempre en blanco):
          B=CIUDAD, C=POC ID, D=POC, E=COD. SAP, F=DESC SAP,
          G=TEORICO CONTEOS, H=COSTO, I=PTR, J=PTC, K=Sum of TEORICO PACK
        Header en fila 1, datos desde fila 2.
        """
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            poc_id = _to_str(row[2]) if len(row) > 2 else ''
            if not poc_id:
                continue
            rows.append({
                'ciudad': _to_str(row[1]) if len(row) > 1 else '',
                'poc_id': poc_id,
                'poc_name': _to_str(row[3]) if len(row) > 3 else '',
                'cod_sap': _to_str(row[4]) if len(row) > 4 else '',
                'desc_sap': _to_str(row[5]) if len(row) > 5 else '',
                'teorico_conteos': _to_float(row[6]) if len(row) > 6 else 0.0,
                'costo': _to_float(row[7]) if len(row) > 7 else 0.0,
            })
        return rows

    def _parse_inventario_en(self, ws) -> list:
        """
        Parsea la hoja 'Inventario EN'.

        Estructura (col A siempre en blanco):
          B=CIUDAD, C=POC ID, D=POC, E=COD. SAP (HOMOLOGADO),
          F=DESC SAP (HOMOLOGADO), G=INV TEÓRICO, H=Sum of DOL COSTO EN
        Header en fila 1, datos desde fila 2.
        """
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            poc_id = _to_str(row[2]) if len(row) > 2 else ''
            if not poc_id:
                continue
            rows.append({
                'ciudad': _to_str(row[1]) if len(row) > 1 else '',
                'poc_id': poc_id,
                'poc_name': _to_str(row[3]) if len(row) > 3 else '',
                'inv_teorico': _to_float(row[6]) if len(row) > 6 else 0.0,
                'dol_costo_en': _to_float(row[7]) if len(row) > 7 else 0.0,
            })
        return rows

    def _parse_pedido(self, ws) -> list:
        """
        Parsea la hoja 'Pedido'.

        Fila 1: grupo de encabezado (ignorar)
        Fila 2: encabezados reales — detección dinámica de columnas por nombre
        Fila 3+: datos

        Columnas requeridas: 'Código Cliente', 'Código Material', 'Cajas / Cant PFN=Und'
        """
        # Leer fila de encabezados (fila 2)
        header_row = None
        for i, row in enumerate(ws.iter_rows(min_row=2, max_row=2, values_only=True)):
            header_row = row
            break

        if header_row is None:
            return []

        # Normalizar encabezados para matching flexible
        def normalize(s):
            if s is None:
                return ''
            return str(s).strip().lower().replace('\n', ' ').replace('/', ' ')

        col_indices = {}
        for idx, cell in enumerate(header_row):
            norm = normalize(cell)
            if 'cliente' in norm:
                col_indices['poc_id'] = idx
            elif 'código' in norm and 'material' in norm:
                col_indices['cod_material'] = idx
            elif 'caja' in norm or ('cant' in norm and 'pfn' in norm):
                col_indices['cajas'] = idx

        rows = []
        # Track último poc_id para filas con Código Cliente vacío (pedido multi-línea)
        last_poc_id = ''
        for row in ws.iter_rows(min_row=3, values_only=True):
            poc_id_raw = row[col_indices['poc_id']] if 'poc_id' in col_indices else None
            cod_mat_raw = row[col_indices['cod_material']] if 'cod_material' in col_indices else None
            cajas_raw = row[col_indices['cajas']] if 'cajas' in col_indices else None

            if cod_mat_raw is None:
                continue

            poc_id = _to_str(poc_id_raw)
            if poc_id:
                last_poc_id = poc_id
            else:
                poc_id = last_poc_id

            rows.append({
                'poc_id': poc_id,
                'cod_material': _to_str(cod_mat_raw),
                'cajas': _to_float(cajas_raw),
            })
        return rows

    # -------------------------------------------------------------------------
    # Queries a la DB (capa repositorio)
    # -------------------------------------------------------------------------

    def _build_productos_compra_lookup(self, codes: set) -> dict:
        """Devuelve {str(code): float(cost_per_box)}."""
        if not codes:
            return {}
        qs = VentasProductosCompra.objects.filter(
            code__in=codes,
            deleted_at__isnull=True
        ).only('code', 'cost_per_box')
        return {
            str(obj.code): _to_float(obj.cost_per_box)
            for obj in qs
        }

    def _build_sales_record_aggregates(self, year: int, month: int, poc_ids: set) -> dict:
        """
        Devuelve:
        {
          poc_id: {
            '__total_hls': float,
            '__total_dolars': float,
            sku_padre: {'units': float},
            ...
          }
        }
        """
        if not poc_ids:
            return {}

        qs = SalesRecord.objects.filter(
            year=year,
            month=month,
            poc_id__in=poc_ids,
            deleted_at__isnull=True
        ).values('poc_id', 'sku_padre').annotate(
            total_units=Sum('units_per_sku'),
            total_hls=Sum('hectolitros'),
            total_dolars=Sum('dolars')
        )

        result = {}
        for row in qs:
            pid = _to_str(row['poc_id'])
            if pid not in result:
                result[pid] = {'__total_hls': 0.0, '__total_dolars': 0.0}

            hls = _to_float(row['total_hls'])
            dolars = _to_float(row['total_dolars'])
            result[pid]['__total_hls'] += hls
            result[pid]['__total_dolars'] += dolars

            sku = _to_str(row['sku_padre'])
            if sku:
                if sku not in result[pid]:
                    result[pid][sku] = {'units': 0.0}
                result[pid][sku]['units'] += _to_float(row['total_units'])

        return result

    def _build_poc_lookup(self, poc_ids: set) -> dict:
        """Devuelve {id_poc: {'city': str, 'name': str}}."""
        if not poc_ids:
            return {}
        qs = POC.objects.filter(
            id_poc__in=poc_ids,
            deleted_at__isnull=True
        ).only('id_poc', 'city', 'name')
        return {
            str(obj.id_poc): {'city': obj.city or '', 'name': obj.name or ''}
            for obj in qs
        }

    # -------------------------------------------------------------------------
    # Lógica de negocio
    # -------------------------------------------------------------------------

    def _compute_poc_summary(
        self, pt_rows, en_rows, pedido_rows,
        compra_lookup, sales_agg, poc_lookup
    ) -> list:
        """Calcula el resumen por POC."""

        # Agregar PT por POC
        inv_pt_by_poc = {}
        for r in pt_rows:
            pid = r['poc_id']
            if pid not in inv_pt_by_poc:
                inv_pt_by_poc[pid] = {'cost': 0.0, 'units': 0.0, 'ciudad': r['ciudad'], 'poc_name': r['poc_name']}
            inv_pt_by_poc[pid]['cost'] += r['costo']
            inv_pt_by_poc[pid]['units'] += r['teorico_conteos']

        # Agregar EN por POC
        inv_en_by_poc = {}
        for r in en_rows:
            pid = r['poc_id']
            if pid not in inv_en_by_poc:
                inv_en_by_poc[pid] = {'cost': 0.0, 'ciudad': r['ciudad'], 'poc_name': r['poc_name']}
            inv_en_by_poc[pid]['cost'] += r['dol_costo_en']

        # Agregar Pedido por POC
        pedido_by_poc = {}
        for r in pedido_rows:
            pid = r['poc_id']
            if not pid:
                continue
            cost_per_box = compra_lookup.get(r['cod_material'], 0.0)
            pedido_value = r['cajas'] * cost_per_box
            pedido_by_poc[pid] = pedido_by_poc.get(pid, 0.0) + pedido_value

        # Union de todos los POC IDs
        all_poc_ids = set(inv_pt_by_poc) | set(inv_en_by_poc) | set(pedido_by_poc)

        summary_rows = []
        for pid in sorted(all_poc_ids):
            inv_pt_costo = inv_pt_by_poc.get(pid, {}).get('cost', 0.0)
            inv_en_costo = inv_en_by_poc.get(pid, {}).get('cost', 0.0)
            pedido_usd = pedido_by_poc.get(pid, 0.0)
            total_costo = inv_pt_costo + inv_en_costo + pedido_usd

            sales = sales_agg.get(pid, {})
            suma_hls = sales.get('__total_hls', 0.0)
            ventas_mes = sales.get('__total_dolars', 0.0)

            limite_garantia = min(GARANTIA_LIMITE_MAXIMO, ventas_mes)
            if total_costo > 0:
                cobertura = limite_garantia / total_costo
            else:
                cobertura = None
            revisar = 'ALERTA' if total_costo > limite_garantia else 'OK'

            # Resolver ciudad y nombre: DB > Excel
            db_poc = poc_lookup.get(pid, {})
            ciudad = db_poc.get('city') or inv_pt_by_poc.get(pid, {}).get('ciudad') or inv_en_by_poc.get(pid, {}).get('ciudad') or ''
            poc_name = db_poc.get('name') or inv_pt_by_poc.get(pid, {}).get('poc_name') or inv_en_by_poc.get(pid, {}).get('poc_name') or ''

            summary_rows.append({
                'CIUDAD': ciudad,
                'Código Cliente': pid,
                'POC': poc_name,
                'Pedido En $': round(pedido_usd, 2),
                'Suma de HLS': round(suma_hls, 4),
                'Inv PT al Costo': round(inv_pt_costo, 2),
                'Inv EN al Costo': round(inv_en_costo, 2),
                'Total Costo': round(total_costo, 2),
                'LIMITE GARANTÍA': round(limite_garantia, 2),
                'Revisar': revisar,
                '_cobertura_raw': cobertura,  # float decimal para formato %
            })

        return summary_rows

    def _compute_sku_detail(self, pt_rows, sales_agg, poc_lookup, year: int, month: int) -> list:
        """Calcula los días de inventario por POC + SKU."""
        days_in_month = calendar.monthrange(year, month)[1]

        detail_rows = []
        for r in pt_rows:
            pid = r['poc_id']
            cod_sap = r['cod_sap']
            inv_units = r['teorico_conteos']

            sku_data = sales_agg.get(pid, {}).get(cod_sap, {})
            monthly_units = sku_data.get('units', 0.0)
            avg_daily = monthly_units / days_in_month if days_in_month > 0 else 0.0
            dias_inv = round(inv_units / avg_daily, 1) if avg_daily > 0 else None

            db_poc = poc_lookup.get(pid, {})
            ciudad = db_poc.get('city') or r['ciudad']
            poc_name = db_poc.get('name') or r['poc_name']

            detail_rows.append({
                'POC ID': pid,
                'POC': poc_name,
                'CIUDAD': ciudad,
                'COD. SAP': cod_sap,
                'DESC SAP': r['desc_sap'],
                'Inv Units': r['teorico_conteos'],
                'Ventas Mes Units': round(monthly_units, 4),
                'Avg Diario': round(avg_daily, 4),
                'Días de Inventario': dias_inv,
            })

        return detail_rows

    # -------------------------------------------------------------------------
    # Generación del Excel de salida
    # -------------------------------------------------------------------------

    def _build_output_excel(self, summary_rows: list, detail_rows: list) -> BytesIO:
        """Genera el Excel de salida con dos hojas."""
        from openpyxl import Workbook

        USD_FMT = '$#,##0.00'
        wb = Workbook()

        # ---- Sheet 1: Resumen por POC ----
        ws_summary = wb.active
        ws_summary.title = 'Resumen por POC'

        summary_headers = [
            'CIUDAD', 'Código Cliente', 'POC',
            'Pedido En $', 'Suma de HLS',
            'Inv PT al Costo', 'Inv EN al Costo', 'Total Costo',
            'LIMITE GARANTÍA', 'Revisar', 'Cobertura %',
        ]
        ws_summary.append(summary_headers)
        self._style_header_row(ws_summary, 1, len(summary_headers))

        # Índices (1-based) de columnas con formato USD en sheet 1
        summary_usd_cols = {
            summary_headers.index('Pedido En $') + 1,
            summary_headers.index('Inv PT al Costo') + 1,
            summary_headers.index('Inv EN al Costo') + 1,
            summary_headers.index('Total Costo') + 1,
            summary_headers.index('LIMITE GARANTÍA') + 1,
        }
        cobertura_col_idx = summary_headers.index('Cobertura %') + 1
        revisar_col_idx = summary_headers.index('Revisar') + 1

        # Columnas numéricas a sumar para "Total general"
        numeric_keys = ['Pedido En $', 'Suma de HLS', 'Inv PT al Costo',
                        'Inv EN al Costo', 'Total Costo', 'LIMITE GARANTÍA']
        totals = {k: 0.0 for k in numeric_keys}

        for row_data in summary_rows:
            cobertura_val = row_data.get('_cobertura_raw')
            ws_summary.append([
                row_data['CIUDAD'].upper() if row_data['CIUDAD'] else '',
                row_data['Código Cliente'],
                row_data['POC'].upper() if row_data['POC'] else '',
                row_data['Pedido En $'],
                row_data['Suma de HLS'],
                row_data['Inv PT al Costo'],
                row_data['Inv EN al Costo'],
                row_data['Total Costo'],
                row_data['LIMITE GARANTÍA'],
                row_data['Revisar'].upper() if row_data['Revisar'] else '',
                cobertura_val,
            ])

            cur_row = ws_summary.max_row

            # Acumular totales
            for k in numeric_keys:
                totals[k] += row_data.get(k, 0.0)

            # Formato USD a columnas de dinero
            for col_idx in summary_usd_cols:
                ws_summary.cell(row=cur_row, column=col_idx).number_format = USD_FMT

            # Formato % en Cobertura
            if cobertura_val is not None:
                ws_summary.cell(row=cur_row, column=cobertura_col_idx).number_format = '0.00%'

            # Color Revisar
            revisar_cell = ws_summary.cell(row=cur_row, column=revisar_col_idx)
            if row_data['Revisar'] == 'ALERTA':
                revisar_cell.fill = PatternFill(start_color='FFCCCC', end_color='FFCCCC', fill_type='solid')
            else:
                revisar_cell.fill = PatternFill(start_color='CCFFCC', end_color='CCFFCC', fill_type='solid')

        # Fila "Total general"
        total_costo_total = totals['Total Costo']
        limite_total = totals['LIMITE GARANTÍA']
        cobertura_total = (limite_total / total_costo_total) if total_costo_total > 0 else None

        ws_summary.append([
            'TOTAL GENERAL', '', '',
            round(totals['Pedido En $'], 2),
            round(totals['Suma de HLS'], 4),
            round(totals['Inv PT al Costo'], 2),
            round(totals['Inv EN al Costo'], 2),
            round(total_costo_total, 2),
            round(limite_total, 2),
            '',
            cobertura_total,
        ])
        total_row_idx = ws_summary.max_row

        for col_idx in range(1, len(summary_headers) + 1):
            ws_summary.cell(row=total_row_idx, column=col_idx).font = Font(bold=True)

        for col_idx in summary_usd_cols:
            ws_summary.cell(row=total_row_idx, column=col_idx).number_format = USD_FMT

        if cobertura_total is not None:
            ws_summary.cell(row=total_row_idx, column=cobertura_col_idx).number_format = '0.00%'

        self._autofit_columns(ws_summary)

        # ---- Sheet 2: Días de Inventario ----
        ws_detail = wb.create_sheet(title='Días de Inventario')
        detail_headers = [
            'POC ID', 'POC', 'CIUDAD', 'COD. SAP', 'DESC SAP',
            'Inv Units', 'Ventas Mes Units', 'Avg Diario', 'Días de Inventario',
        ]
        ws_detail.append(detail_headers)
        self._style_header_row(ws_detail, 1, len(detail_headers))

        # Índices (1-based) de columnas de texto en sheet 2
        detail_text_cols = {
            detail_headers.index('POC ID') + 1,
            detail_headers.index('POC') + 1,
            detail_headers.index('CIUDAD') + 1,
            detail_headers.index('COD. SAP') + 1,
            detail_headers.index('DESC SAP') + 1,
        }

        for row_data in detail_rows:
            ws_detail.append([
                row_data['POC ID'],
                row_data['POC'].upper() if row_data['POC'] else '',
                row_data['CIUDAD'].upper() if row_data['CIUDAD'] else '',
                row_data['COD. SAP'].upper() if row_data['COD. SAP'] else '',
                row_data['DESC SAP'].upper() if row_data['DESC SAP'] else '',
                row_data['Inv Units'],
                row_data['Ventas Mes Units'],
                row_data['Avg Diario'],
                row_data['Días de Inventario'],
            ])

        self._autofit_columns(ws_detail)

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        del wb
        gc.collect()

        return output

    # -------------------------------------------------------------------------
    # Helpers de formato
    # -------------------------------------------------------------------------

    @staticmethod
    def _style_header_row(ws, row_idx: int, num_cols: int):
        """Aplica estilo de encabezado (fondo gris, negrita) a una fila."""
        for col_idx in range(1, num_cols + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color='D9D9D9', end_color='D9D9D9', fill_type='solid')
            cell.alignment = Alignment(horizontal='center', wrap_text=True)

    @staticmethod
    def _autofit_columns(ws):
        """Ajusta el ancho de columnas según el contenido."""
        for col in ws.columns:
            max_len = 0
            for cell in col:
                try:
                    cell_len = len(str(cell.value)) if cell.value is not None else 0
                    if cell_len > max_len:
                        max_len = cell_len
                except Exception:
                    pass
            adjusted = min(max_len + 2, 45)
            ws.column_dimensions[get_column_letter(col[0].column)].width = adjusted
