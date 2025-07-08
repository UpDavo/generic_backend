from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
from django.db.models import Q
from django.shortcuts import get_object_or_404

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
