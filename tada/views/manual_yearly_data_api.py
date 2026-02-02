from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from tada.models import ManualYearlyData
from tada.serializers.manual_yearly_data_serializer import (
    ManualYearlyDataSerializer,
    ManualYearlyDataCreateSerializer
)


class ManualYearlyDataListCreateView(APIView):
    """
    Vista para listar y crear datos anuales manuales.

    GET: Listar datos con filtros opcionales
    POST: Crear un nuevo dato manual
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Listar datos manuales con filtros opcionales.

        Query params:
        - year: Filtrar por año
        - start_week: Filtrar por semana inicial
        - end_week: Filtrar por semana final
        - report_type: Filtrar por tipo de reporte (hectolitros/caja)
        - city: Filtrar por ciudad (usar "null" para totales generales)
        """
        queryset = ManualYearlyData.objects.filter(deleted_at__isnull=True)

        # Aplicar filtros
        year = request.query_params.get('year')
        if year:
            try:
                queryset = queryset.filter(year=int(year))
            except ValueError:
                pass

        start_week = request.query_params.get('start_week')
        if start_week:
            try:
                queryset = queryset.filter(start_week=int(start_week))
            except ValueError:
                pass

        end_week = request.query_params.get('end_week')
        if end_week:
            try:
                queryset = queryset.filter(end_week=int(end_week))
            except ValueError:
                pass

        report_type = request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type.lower())

        city = request.query_params.get('city')
        if city:
            if city.lower() == 'null':
                queryset = queryset.filter(city__isnull=True)
            else:
                queryset = queryset.filter(city__iexact=city)

        serializer = ManualYearlyDataSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Crear un nuevo dato manual.

        Body:
        {
            "year": 2025,
            "start_week": 1,
            "end_week": 4,
            "report_type": "hectolitros",
            "city": "QUITO",  # o null para total general
            "value": 1234.56
        }
        """
        serializer = ManualYearlyDataCreateSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()

            return Response(
                ManualYearlyDataSerializer(serializer.instance).data,
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ManualYearlyDataDetailView(APIView):
    """
    Vista para obtener, actualizar y eliminar un dato manual específico.

    GET: Obtener detalle
    PUT/PATCH: Actualizar
    DELETE: Eliminar (soft delete)
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        """Obtener el objeto o retornar None."""
        try:
            return ManualYearlyData.objects.get(pk=pk, deleted_at__isnull=True)
        except ManualYearlyData.DoesNotExist:
            return None

    def get(self, request, pk):
        """Obtener detalle de un dato manual."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Dato manual no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ManualYearlyDataSerializer(obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        """Actualizar completamente un dato manual."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Dato manual no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ManualYearlyDataCreateSerializer(obj, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(
                ManualYearlyDataSerializer(serializer.instance).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """Actualizar parcialmente un dato manual."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Dato manual no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ManualYearlyDataCreateSerializer(
            obj,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                ManualYearlyDataSerializer(serializer.instance).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """Eliminar (soft delete) un dato manual."""
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {'error': 'Dato manual no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        obj.delete()  # BaseModel maneja el soft delete
        return Response(
            {'message': 'Dato manual eliminado exitosamente'},
            status=status.HTTP_204_NO_CONTENT
        )
