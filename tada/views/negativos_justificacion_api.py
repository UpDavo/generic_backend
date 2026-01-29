from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models import Q
import pandas as pd
from io import BytesIO
from datetime import datetime
from tqdm import tqdm

from tada.models import NegativosJustificacion, POC
from tada.serializers import (
    NegativosJustificacionSerializer,
    NegativosJustificacionListSerializer,
    NegativosJustificacionCreateSerializer,
    NegativosJustificacionUpdateSerializer,
    NegativosJustificacionSimpleSerializer
)


class NegativosJustificacionListCreateView(APIView):
    """
    View to list all NegativosJustificacion or create a new one.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        List all NegativosJustificacion with optional filters.

        Query params:
        - id_ticket: Search by ticket ID (contains)
        - titulo_caso: Search by case title (contains)
        - fecha_inicio: Filter by start date (YYYY-MM-DD)
        - fecha_fin: Filter by end date (YYYY-MM-DD)
        - hora_inicio_desde: Filter by start datetime (YYYY-MM-DD HH:MM:SS)
        - hora_inicio_hasta: Filter by end datetime (YYYY-MM-DD HH:MM:SS)
        - es_tienda: Filter by store flag (true/false)
        - poc: Filter by POC ID
        - poc_name: Search by POC name (contains)
        - search: Search in id_ticket, titulo_caso, and justificacion (contains)
        - page: Page number (default: 1)
        - page_size: Items per page (default: varies)
        """
        queryset = NegativosJustificacion.objects.all()

        # Filter by id_ticket
        id_ticket = request.query_params.get('id_ticket')
        if id_ticket:
            queryset = queryset.filter(id_ticket__icontains=id_ticket)

        # Filter by titulo_caso
        titulo_caso = request.query_params.get('titulo_caso')
        if titulo_caso:
            queryset = queryset.filter(titulo_caso__icontains=titulo_caso)

        # Filter by fecha_inicio (date only)
        fecha_inicio = request.query_params.get('fecha_inicio')
        if fecha_inicio:
            queryset = queryset.filter(hora_inicio__date__gte=fecha_inicio)

        # Filter by fecha_fin (date only)
        fecha_fin = request.query_params.get('fecha_fin')
        if fecha_fin:
            queryset = queryset.filter(hora_inicio__date__lte=fecha_fin)
        
        # Filter by hora_inicio_desde (datetime)
        hora_inicio_desde = request.query_params.get('hora_inicio_desde')
        if hora_inicio_desde:
            queryset = queryset.filter(hora_inicio__gte=hora_inicio_desde)
        
        # Filter by hora_inicio_hasta (datetime)
        hora_inicio_hasta = request.query_params.get('hora_inicio_hasta')
        if hora_inicio_hasta:
            queryset = queryset.filter(hora_inicio__lte=hora_inicio_hasta)
        
        # Filter by es_tienda
        es_tienda = request.query_params.get('es_tienda')
        if es_tienda is not None:
            es_tienda_bool = es_tienda.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(es_tienda=es_tienda_bool)
        
        # Filter by POC
        poc = request.query_params.get('poc')
        if poc:
            queryset = queryset.filter(poc_id=poc)
        
        # Filter by POC name
        poc_name = request.query_params.get('poc_name')
        if poc_name:
            queryset = queryset.filter(poc__name__icontains=poc_name)

        # Search by id_ticket, titulo_caso, or justificacion
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(id_ticket__icontains=search) |
                Q(titulo_caso__icontains=search) |
                Q(justificacion__icontains=search)
            )

        queryset = queryset.order_by('-hora_inicio')

        # Apply pagination
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = NegativosJustificacionListSerializer(
            paginated_queryset, many=True)

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """
        Create a new NegativosJustificacion.
        """
        serializer = NegativosJustificacionCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response(
                NegativosJustificacionSerializer(serializer.instance).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NegativosJustificacionRetrieveUpdateDestroyView(APIView):
    """
    View to retrieve, update or delete a specific NegativosJustificacion.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """
        Retrieve a specific NegativosJustificacion by ID.
        """
        justificacion = get_object_or_404(NegativosJustificacion, pk=pk)
        serializer = NegativosJustificacionSerializer(justificacion)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Update a specific NegativosJustificacion by ID.
        """
        justificacion = get_object_or_404(NegativosJustificacion, pk=pk)
        serializer = NegativosJustificacionUpdateSerializer(
            justificacion, data=request.data, partial=False
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                NegativosJustificacionSerializer(serializer.instance).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Partially update a specific NegativosJustificacion by ID.
        """
        justificacion = get_object_or_404(NegativosJustificacion, pk=pk)
        serializer = NegativosJustificacionUpdateSerializer(
            justificacion, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                NegativosJustificacionSerializer(serializer.instance).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Delete a specific NegativosJustificacion by ID.
        """
        justificacion = get_object_or_404(NegativosJustificacion, pk=pk)
        justificacion.delete()
        return Response(
            {'message': 'Justificación eliminada exitosamente'},
            status=status.HTTP_204_NO_CONTENT
        )


class NegativosJustificacionSearchView(APIView):
    """
    View to search NegativosJustificacion with advanced filters.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        Search NegativosJustificacion with multiple filters.

        Query params:
        - id_ticket: Exact match or contains
        - titulo_caso: Contains (case insensitive)
        - fecha_inicio_desde: Start date from (YYYY-MM-DD)
        - fecha_inicio_hasta: Start date to (YYYY-MM-DD)
        - fecha_fin_desde: End date from (YYYY-MM-DD)
        - fecha_fin_hasta: End date to (YYYY-MM-DD)
        - hora_inicio_desde: Start datetime from (YYYY-MM-DD HH:MM:SS)
        - hora_inicio_hasta: Start datetime to (YYYY-MM-DD HH:MM:SS)
        - hora_fin_desde: End datetime from (YYYY-MM-DD HH:MM:SS)
        - hora_fin_hasta: End datetime to (YYYY-MM-DD HH:MM:SS)
        - es_tienda: Filter by store flag (true/false)
        - poc: Filter by POC ID
        - region: Filter by POC region (costa/sierra/oriente/insular)
        - city: Filter by POC city (contains)
        - justificacion: Search in justification text (contains)
        - page: Page number
        - page_size: Items per page
        """
        queryset = NegativosJustificacion.objects.all()

        # Filter by id_ticket
        id_ticket = request.query_params.get('id_ticket')
        if id_ticket:
            queryset = queryset.filter(id_ticket__icontains=id_ticket)

        # Filter by titulo_caso
        titulo_caso = request.query_params.get('titulo_caso')
        if titulo_caso:
            queryset = queryset.filter(titulo_caso__icontains=titulo_caso)

        # Filter by fecha_inicio_desde (date only)
        fecha_inicio_desde = request.query_params.get('fecha_inicio_desde')
        if fecha_inicio_desde:
            queryset = queryset.filter(hora_inicio__date__gte=fecha_inicio_desde)

        # Filter by fecha_inicio_hasta (date only)
        fecha_inicio_hasta = request.query_params.get('fecha_inicio_hasta')
        if fecha_inicio_hasta:
            queryset = queryset.filter(hora_inicio__date__lte=fecha_inicio_hasta)

        # Filter by fecha_fin_desde (date only)
        fecha_fin_desde = request.query_params.get('fecha_fin_desde')
        if fecha_fin_desde:
            queryset = queryset.filter(hora_fin__date__gte=fecha_fin_desde)

        # Filter by fecha_fin_hasta (date only)
        fecha_fin_hasta = request.query_params.get('fecha_fin_hasta')
        if fecha_fin_hasta:
            queryset = queryset.filter(hora_fin__date__lte=fecha_fin_hasta)
        
        # Filter by hora_inicio_desde (datetime)
        hora_inicio_desde = request.query_params.get('hora_inicio_desde')
        if hora_inicio_desde:
            queryset = queryset.filter(hora_inicio__gte=hora_inicio_desde)
        
        # Filter by hora_inicio_hasta (datetime)
        hora_inicio_hasta = request.query_params.get('hora_inicio_hasta')
        if hora_inicio_hasta:
            queryset = queryset.filter(hora_inicio__lte=hora_inicio_hasta)
        
        # Filter by hora_fin_desde (datetime)
        hora_fin_desde = request.query_params.get('hora_fin_desde')
        if hora_fin_desde:
            queryset = queryset.filter(hora_fin__gte=hora_fin_desde)
        
        # Filter by hora_fin_hasta (datetime)
        hora_fin_hasta = request.query_params.get('hora_fin_hasta')
        if hora_fin_hasta:
            queryset = queryset.filter(hora_fin__lte=hora_fin_hasta)
        
        # Filter by es_tienda
        es_tienda = request.query_params.get('es_tienda')
        if es_tienda is not None:
            es_tienda_bool = es_tienda.lower() in ['true', '1', 'yes']
            queryset = queryset.filter(es_tienda=es_tienda_bool)
        
        # Filter by POC
        poc = request.query_params.get('poc')
        if poc:
            queryset = queryset.filter(poc_id=poc)
        
        # Filter by POC region
        region = request.query_params.get('region')
        if region:
            queryset = queryset.filter(poc__region=region)
        
        # Filter by POC city
        city = request.query_params.get('city')
        if city:
            queryset = queryset.filter(poc__city__icontains=city)

        # Filter by justificacion
        justificacion = request.query_params.get('justificacion')
        if justificacion:
            queryset = queryset.filter(justificacion__icontains=justificacion)

        queryset = queryset.order_by('-hora_inicio')

        # Apply pagination
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = NegativosJustificacionListSerializer(
            paginated_queryset, many=True
        )

        return paginator.get_paginated_response(serializer.data)


class NegativosJustificacionBulkCreateFromExcelView(APIView):
    """
    View to bulk create NegativosJustificacion from an Excel file.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Bulk create NegativosJustificacion from Excel file.

        Expected Excel columns:
        - id_ticket: Ticket ID (required)
        - titulo_caso: Case title (required)
        - hora_inicio: Start time (datetime, required)
        - hora_fin: End time (datetime, required)
        - justificacion: Justification text (required)
        - es_tienda: Whether it's a store case (true/false, optional, default: false)
        - id_poc: POC identifier (optional, required if es_tienda is true)

        Returns:
        - created_count: Number of records created
        - updated_count: Number of records updated
        - error_count: Number of errors
        - errors: List of error messages
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No se proporcionó ningún archivo'},
                status=status.HTTP_400_BAD_REQUEST
            )

        excel_file = request.FILES['file']

        try:
            # Read Excel file
            df = pd.read_excel(excel_file)

            required_columns = [
                'id_ticket', 'titulo_caso', 'hora_inicio', 'hora_fin', 'justificacion'
            ]
            missing_columns = [
                col for col in required_columns if col not in df.columns]
            if missing_columns:
                return Response(
                    {'error': f'Faltan columnas requeridas: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_count = 0
            updated_count = 0
            error_count = 0
            errors = []

            for idx, row in tqdm(df.iterrows(), total=len(df), desc='Processing rows'):
                try:
                    # Clean and validate data
                    id_ticket = str(row['id_ticket']).strip() if pd.notna(
                        row['id_ticket']) else None
                    titulo_caso = str(row['titulo_caso']).strip() if pd.notna(
                        row['titulo_caso']) else None
                    hora_inicio = pd.to_datetime(
                        row['hora_inicio']) if pd.notna(row['hora_inicio']) else None
                    hora_fin = pd.to_datetime(
                        row['hora_fin']) if pd.notna(row['hora_fin']) else None
                    justificacion = str(row['justificacion']).strip() if pd.notna(
                        row['justificacion']) else None
                    
                    # Handle es_tienda (optional, default False)
                    es_tienda = False
                    if 'es_tienda' in row and pd.notna(row['es_tienda']):
                        es_tienda_val = str(row['es_tienda']).strip().lower()
                        es_tienda = es_tienda_val in ['true', '1', 'yes', 'si', 'sí', 's', 'y']
                    
                    # Handle POC (optional, but required if es_tienda is True)
                    poc = None
                    if 'id_poc' in row and pd.notna(row['id_poc']):
                        id_poc_val = str(row['id_poc']).strip().upper()
                        try:
                            poc = POC.objects.get(id_poc=id_poc_val)
                        except POC.DoesNotExist:
                            errors.append(
                                f'Fila {idx + 2}: POC con id_poc "{id_poc_val}" no existe')
                            error_count += 1
                            continue

                    if not id_ticket:
                        errors.append(
                            f'Fila {idx + 2}: id_ticket es requerido')
                        error_count += 1
                        continue

                    if not titulo_caso:
                        errors.append(
                            f'Fila {idx + 2}: titulo_caso es requerido')
                        error_count += 1
                        continue

                    if not hora_inicio:
                        errors.append(
                            f'Fila {idx + 2}: hora_inicio es requerido')
                        error_count += 1
                        continue

                    if not hora_fin:
                        errors.append(
                            f'Fila {idx + 2}: hora_fin es requerido')
                        error_count += 1
                        continue

                    if hora_fin <= hora_inicio:
                        errors.append(
                            f'Fila {idx + 2}: hora_fin debe ser posterior a hora_inicio')
                        error_count += 1
                        continue
                    
                    # Validate POC requirement
                    if es_tienda and not poc:
                        errors.append(
                            f'Fila {idx + 2}: POC es requerido cuando es_tienda es verdadero')
                        error_count += 1
                        continue

                    # Create or update
                    defaults = {
                        'titulo_caso': titulo_caso,
                        'hora_inicio': hora_inicio,
                        'hora_fin': hora_fin,
                        'justificacion': justificacion,
                        'es_tienda': es_tienda,
                        'poc': poc
                    }
                    
                    # Add created_by only on creation
                    try:
                        justificacion_obj = NegativosJustificacion.objects.get(id_ticket=id_ticket)
                        # Update existing
                        for key, value in defaults.items():
                            setattr(justificacion_obj, key, value)
                        justificacion_obj.save()
                        created = False
                    except NegativosJustificacion.DoesNotExist:
                        # Create new with created_by
                        defaults['created_by'] = request.user
                        justificacion_obj = NegativosJustificacion.objects.create(
                            id_ticket=id_ticket,
                            **defaults
                        )
                        created = True

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    error_count += 1
                    errors.append(f'Fila {idx + 2}: {str(e)}')

            return Response({
                'message': 'Proceso completado',
                'created_count': created_count,
                'updated_count': updated_count,
                'error_count': error_count,
                'errors': errors[:50]  # Limit errors to first 50
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'Error procesando archivo: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class NegativosJustificacionDownloadTemplateView(APIView):
    """
    View to download an Excel template for NegativosJustificacion.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Download an Excel template for NegativosJustificacion.
        """
        # Create sample data
        data = {
            'id_ticket': ['TICKET-001', 'TICKET-002', 'TICKET-003'],
            'titulo_caso': ['Caso ejemplo 1', 'Caso ejemplo tienda', 'Caso ejemplo 3'],
            'hora_inicio': ['2026-01-29 10:00:00', '2026-01-29 11:00:00', '2026-01-29 14:00:00'],
            'hora_fin': ['2026-01-29 11:00:00', '2026-01-29 12:00:00', '2026-01-29 15:30:00'],
            'justificacion': ['Justificación ejemplo 1', 'Cliente insatisfecho con servicio en tienda', 'Justificación ejemplo 3'],
            'es_tienda': [False, True, False],
            'id_poc': ['', 'POC001', '']
        }

        df = pd.DataFrame(data)

        # Create Excel file with instructions
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Justificaciones')
            
            # Create instructions sheet
            instructions_data = {
                'Columna': [
                    'id_ticket',
                    'titulo_caso',
                    'hora_inicio',
                    'hora_fin',
                    'justificacion',
                    'es_tienda',
                    'id_poc'
                ],
                'Requerido': [
                    'SÍ',
                    'SÍ',
                    'SÍ',
                    'SÍ',
                    'SÍ',
                    'Opcional (default: false)',
                    'Requerido si es_tienda=true'
                ],
                'Descripción': [
                    'ID único del ticket',
                    'Título del caso',
                    'Fecha y hora de inicio (formato: YYYY-MM-DD HH:MM:SS)',
                    'Fecha y hora de fin (formato: YYYY-MM-DD HH:MM:SS)',
                    'Justificación del caso negativo',
                    'Si el caso es de tienda (true/false)',
                    'Código del POC (debe existir en la base de datos)'
                ],
                'Ejemplo': [
                    'TICKET-001',
                    'Cliente insatisfecho con atención',
                    '2026-01-29 10:00:00',
                    '2026-01-29 11:00:00',
                    'El cliente reportó demora en la atención debido a...',
                    'true',
                    'POC001'
                ]
            }
            
            instructions_df = pd.DataFrame(instructions_data)
            instructions_df.to_excel(writer, index=False, sheet_name='Instrucciones')

        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=negativos_justificacion_template.xlsx'

        return response


class NegativosJustificacionDownloadAllView(APIView):
    """
    View to download all NegativosJustificacion as Excel file.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Download all NegativosJustificacion as Excel file with optional filters.

        Query params:
        - fecha_inicio_desde: Start date from (YYYY-MM-DD)
        - fecha_inicio_hasta: Start date to (YYYY-MM-DD)
        """
        queryset = NegativosJustificacion.objects.all()

        # Apply filters
        fecha_inicio_desde = request.query_params.get('fecha_inicio_desde')
        if fecha_inicio_desde:
            queryset = queryset.filter(hora_inicio__date__gte=fecha_inicio_desde)

        fecha_inicio_hasta = request.query_params.get('fecha_inicio_hasta')
        if fecha_inicio_hasta:
            queryset = queryset.filter(hora_inicio__date__lte=fecha_inicio_hasta)

        queryset = queryset.order_by('-hora_inicio')

        # Create DataFrame
        data = []
        for obj in queryset:
            data.append({
                'ID': obj.id,
                'ID Ticket': obj.id_ticket,
                'Título del Caso': obj.titulo_caso,
                'Hora Inicio': obj.hora_inicio,
                'Hora Fin': obj.hora_fin,
                'Duración (minutos)': obj.duracion_caso,
                'Justificación': obj.justificacion,
                'Es Tienda': 'Sí' if obj.es_tienda else 'No',
                'POC ID': obj.poc.id_poc if obj.poc else '',
                'POC Nombre': obj.poc.name if obj.poc else '',
                'POC Ciudad': obj.poc.city if obj.poc else '',
                'POC Región': obj.poc.region if obj.poc else '',
                'Creado Por': obj.created_by.email if obj.created_by else '',
                'Fecha Creación': obj.created_at,
                'Fecha Actualización': obj.updated_at
            })

        df = pd.DataFrame(data)

        # Create Excel file
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Justificaciones')

        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=negativos_justificacion_{timestamp}.xlsx'

        return response
