from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

import pandas as pd
from datetime import datetime
from dateutil.rrule import rrule, MONTHLY
from transformers import pipeline

# Asegúrate de que este servicio esté correctamente implementado
from tada.services.poc_service import PocService


class PocAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            pocs = request.data.get('pocs')
            fecha_inicio_global = request.data.get('fecha_inicio')
            fecha_fin_global = request.data.get('fecha_fin')

            if not pocs or not fecha_inicio_global or not fecha_fin_global:
                return Response(
                    {"error": "Faltan parámetros: pocs, fecha_inicio o fecha_fin"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Convertir las fechas a objetos datetime
            dt_inicio = datetime.strptime(fecha_inicio_global, "%Y-%m-%d")
            dt_fin = datetime.strptime(fecha_fin_global, "%Y-%m-%d")

            # Preparar el modelo de análisis de sentimiento
            modelo_sentimiento = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment"
            )

            response = []

            # Iterar por cada POC
            for poc in pocs:
                POC_NAME = poc.get("POC_NAME")
                name = poc.get("name")
                ruta_archivo = poc.get("ruta_archivo")

                # Validar que cada POC tenga datos necesarios
                if not POC_NAME or not ruta_archivo:
                    continue

                item = {
                    "name": name,
                    "poc": POC_NAME,
                    "dates": []
                }

                # Iterar mes a mes dentro del rango global
                for dt in rrule(MONTHLY, dtstart=dt_inicio, until=dt_fin):
                    # Fecha de inicio del mes
                    fecha_inicio_str = dt.strftime("%Y-%m-%d")

                    # Calcular el último día del mes:
                    # Avanzamos al siguiente mes
                    mes_siguiente = dt.replace(day=28) + pd.DateOffset(days=4)
                    ultimo_dia_mes = mes_siguiente - \
                        pd.DateOffset(days=mes_siguiente.day)
                    # Asegurarse de no exceder el rango global
                    if ultimo_dia_mes > dt_fin:
                        ultimo_dia_mes = dt_fin
                    fecha_fin_str = ultimo_dia_mes.strftime("%Y-%m-%d")

                    # Ejecutar el análisis para este POC y periodo
                    data = PocService.analizar_chat(
                        POC_NAME=POC_NAME,
                        ruta_archivo=ruta_archivo,
                        fecha_inicio=fecha_inicio_str,
                        fecha_fin=fecha_fin_str,
                        modelo_sentimiento=modelo_sentimiento
                    )
                    item['dates'].append(data)

                response.append(item)

            return Response(
                response,
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
