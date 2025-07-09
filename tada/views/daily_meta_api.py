from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
from django.db.models import Q
from django.shortcuts import get_object_or_404
import pandas as pd
from io import BytesIO

from tada.models import DailyMeta
from tada.serializers import (
    DailyMetaSerializer,
    DailyMetaCreateSerializer,
    DailyMetaUpdateSerializer,
    DailyMetaListSerializer
)


class DailyMetaListCreateView(APIView):
    """
    Vista para listar todas las metas diarias o crear una nueva.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Listar todas las metas diarias con filtros opcionales.
        """
        queryset = DailyMeta.objects.all()

        # Filtrar por fecha específica
        date_param = request.query_params.get('date')
        if date_param:
            try:
                date_obj = parse_date(date_param)
                if date_obj:
                    queryset = queryset.filter(date=date_obj)
            except ValueError:
                pass

        # Filtrar por rango de fechas
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_date_obj = parse_date(start_date)
                if start_date_obj:
                    queryset = queryset.filter(date__gte=start_date_obj)
            except ValueError:
                pass

        if end_date:
            try:
                end_date_obj = parse_date(end_date)
                if end_date_obj:
                    queryset = queryset.filter(date__lte=end_date_obj)
            except ValueError:
                pass

        queryset = queryset.order_by('-date')
        serializer = DailyMetaListSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        Crear una nueva meta diaria.
        """
        serializer = DailyMetaCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DailyMetaRetrieveUpdateDestroyView(APIView):
    """
    Vista para obtener, actualizar o eliminar una meta diaria específica.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(DailyMeta, pk=pk)

    def get(self, request, pk):
        """
        Obtener una meta diaria específica.
        """
        meta = self.get_object(pk)
        serializer = DailyMetaSerializer(meta)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Actualizar completamente una meta diaria.
        """
        meta = self.get_object(pk)
        serializer = DailyMetaUpdateSerializer(meta, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Actualizar parcialmente una meta diaria.
        """
        meta = self.get_object(pk)
        serializer = DailyMetaUpdateSerializer(
            meta, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Eliminar una meta diaria.
        """
        meta = self.get_object(pk)
        meta.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DailyMetaBulkCreateView(APIView):
    """
    Vista para crear múltiples metas de una vez.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Crear múltiples metas de una vez.

        Body esperado:
        {
            "metas": [
                {
                    "date": "2023-12-25",
                    "target_count": 500
                },
                ...
            ]
        }
        """
        metas_data = request.data.get('metas', [])

        if not metas_data or not isinstance(metas_data, list):
            return Response(
                {'error': 'Se requiere una lista de metas en el campo "metas"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        created_metas = []
        errors = []

        for i, meta_data in enumerate(metas_data):
            serializer = DailyMetaCreateSerializer(data=meta_data)
            if serializer.is_valid():
                try:
                    meta = serializer.save()
                    created_metas.append(DailyMetaSerializer(meta).data)
                except Exception as e:
                    errors.append(f"Item {i}: {str(e)}")
            else:
                errors.append(f"Item {i}: {serializer.errors}")

        response_data = {
            'created': len(created_metas),
            'errors': len(errors),
            'results': created_metas
        }

        if errors:
            response_data['error_details'] = errors

        return Response(
            response_data,
            status=status.HTTP_201_CREATED if created_metas else status.HTTP_400_BAD_REQUEST
        )


class DailyMetaBulkCreateFromExcelView(APIView):
    """
    Vista para crear múltiples metas diarias desde un archivo Excel.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Crear o actualizar múltiples metas desde un archivo Excel.

        El archivo Excel debe tener las columnas:
        - date: Fecha en formato YYYY-MM-DD
        - goal: Meta numérica para el día

        Comportamiento:
        - Si la fecha no existe: crea una nueva meta
        - Si la fecha ya existe: actualiza la meta existente
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
            # Leer el archivo Excel
            df = pd.read_excel(BytesIO(excel_file.read()))

            # Validar que las columnas requeridas existan
            required_columns = ['date', 'goal']
            missing_columns = [
                col for col in required_columns if col not in df.columns]

            if missing_columns:
                return Response(
                    {'error': f'Columnas faltantes en el archivo: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_metas = []
            errors = []

            # Procesar cada fila del Excel
            for index, row in df.iterrows():
                try:
                    # Validar y convertir la fecha
                    date_value = row['date']
                    if pd.isna(date_value):
                        # +2 por encabezado y índice 0
                        errors.append(f"Fila {index+2}: Fecha vacía")
                        continue

                    # Si es un timestamp de pandas, convertir a fecha
                    if isinstance(date_value, pd.Timestamp):
                        date_str = date_value.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_value)

                    # Validar y convertir la meta
                    goal_value = row['goal']
                    if pd.isna(goal_value):
                        errors.append(f"Fila {index+2}: Meta vacía")
                        continue

                    try:
                        target_count = int(float(goal_value))
                    except (ValueError, TypeError):
                        errors.append(
                            f"Fila {index+2}: Meta debe ser un número válido")
                        continue

                    # Crear o actualizar el objeto meta
                    meta_data = {
                        'date': date_str,
                        'target_count': target_count
                    }

                    # Verificar si ya existe una meta para esta fecha
                    existing_meta = DailyMeta.objects.filter(
                        date=date_str).first()

                    if existing_meta:
                        # Actualizar meta existente
                        serializer = DailyMetaUpdateSerializer(
                            existing_meta, data=meta_data, partial=True)
                        if serializer.is_valid():
                            try:
                                meta = serializer.save()
                                created_metas.append({
                                    'date': meta.date,
                                    'target_count': meta.target_count,
                                    'id': meta.id,
                                    'action': 'updated'
                                })
                            except Exception as e:
                                errors.append(
                                    f"Fila {index+2}: Error al actualizar - {str(e)}")
                        else:
                            errors.append(
                                f"Fila {index+2}: Error de validación al actualizar - {serializer.errors}")
                    else:
                        # Crear nueva meta
                        serializer = DailyMetaCreateSerializer(data=meta_data)
                        if serializer.is_valid():
                            try:
                                meta = serializer.save()
                                created_metas.append({
                                    'date': meta.date,
                                    'target_count': meta.target_count,
                                    'id': meta.id,
                                    'action': 'created'
                                })
                            except Exception as e:
                                errors.append(
                                    f"Fila {index+2}: Error al crear - {str(e)}")
                        else:
                            errors.append(
                                f"Fila {index+2}: Error de validación al crear - {serializer.errors}")

                except Exception as e:
                    errors.append(
                        f"Fila {index+2}: Error inesperado - {str(e)}")

            # Contar las acciones realizadas
            created_count = len(
                [m for m in created_metas if m.get('action') == 'created'])
            updated_count = len(
                [m for m in created_metas if m.get('action') == 'updated'])

            response_data = {
                'total_processed': len(created_metas),
                'created': created_count,
                'updated': updated_count,
                'total_rows': len(df),
                'errors_count': len(errors),
                'results': created_metas
            }

            if errors:
                response_data['errors'] = errors

            # Si se procesaron algunas metas, devolver 201, sino 400
            status_code = status.HTTP_201_CREATED if created_metas else status.HTTP_400_BAD_REQUEST

            return Response(response_data, status=status_code)

        except Exception as e:
            return Response(
                {'error': f'Error al procesar el archivo Excel: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
