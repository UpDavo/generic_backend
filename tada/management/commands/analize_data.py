import re
import pandas as pd
from datetime import datetime
from dateutil.rrule import rrule, MONTHLY

from django.core.management.base import BaseCommand
from transformers import pipeline

import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# Función de análisis individual (similar a tu código original).
# La idea es encapsular la lógica en una sola función que reciba parámetros.
# ----------------------------------------------------------------------


def analizar_chat(POC_NAME, ruta_archivo, fecha_inicio, fecha_fin, modelo_sentimiento):
    """
    Analiza el chat de un archivo dado, para un POC específico,
    entre un rango de fechas dado [fecha_inicio, fecha_fin].
    Devuelve un DataFrame con los resultados, o imprime resultados.
    """

    patron_linea = re.compile(
        r'^(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2}) - (.*?): (.*)$'
    )
    datos = []
    ultima_fecha = None
    ultima_hora = None
    ultima_persona = None
    ultimo_mensaje = []

    # ----------------------------------------------------
    # 1) Lectura y parseo de líneas
    # ----------------------------------------------------
    with open(ruta_archivo, 'r', encoding='utf-8') as f:
        for linea in f:
            linea = linea.strip()
            match = patron_linea.match(linea)
            if match:
                # Guardar mensaje anterior si existe
                if ultima_fecha and ultima_persona is not None:
                    datos.append([
                        ultima_fecha,
                        ultima_hora,
                        ultima_persona,
                        "\n".join(ultimo_mensaje)
                    ])

                # Extraer datos de la nueva línea
                fecha_str = match.group(1)  # "DD/MM/YYYY"
                hora_str = match.group(2)   # "HH:MM"
                persona = match.group(3)
                mensaje = match.group(4)

                # Convertimos a datetime
                try:
                    fecha_hora = datetime.strptime(
                        f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M"
                    )
                except ValueError:
                    # Si falla el parseo, ignoramos la línea o la manejamos
                    continue

                # Guardamos temporalmente para multiline
                ultima_fecha = fecha_hora.date()
                ultima_hora = fecha_hora.time()
                ultima_persona = persona
                ultimo_mensaje = [mensaje]

            else:
                # Continuación del mensaje anterior
                if ultima_persona is not None:
                    ultimo_mensaje.append(linea)

    # Agregamos el último mensaje si quedó pendiente
    if ultima_fecha and ultima_persona is not None:
        datos.append([
            ultima_fecha,
            ultima_hora,
            ultima_persona,
            "\n".join(ultimo_mensaje)
        ])

    # ----------------------------------------------------
    # 2) Construcción del DataFrame
    # ----------------------------------------------------
    df_chats = pd.DataFrame(
        datos, columns=['Fecha', 'Hora', 'Persona', 'Mensaje'])

    # Creamos una columna datetime completa
    df_chats['FechaHora'] = df_chats.apply(
        lambda x: datetime.combine(x['Fecha'], x['Hora']), axis=1
    )

    df_chats.sort_values(by='FechaHora', inplace=True, ignore_index=True)

    # ----------------------------------------------------
    # 3) Identificación de asesores
    # ----------------------------------------------------
    # - Buscar quien mandó la frase clave
    asesores = df_chats[
        df_chats['Mensaje'].str.contains(
            "Me pongo a sus órdenes", case=False, na=False)
    ]['Persona'].unique()

    # - Nueva columna EsAsesor
    df_chats['EsAsesor'] = df_chats['Persona'].isin(asesores)

    # ----------------------------------------------------
    # 4) Filtro de chats para tienda + asesores
    # ----------------------------------------------------
    def es_tienda(row):
        return POC_NAME.upper() in row['Persona'].upper()

    def cambiar_nombre_tienda(row):
        return "TIENDA" if POC_NAME.upper() in row['Persona'].upper() else row['Persona']

    df_chats_filtrados = df_chats[df_chats.apply(
        lambda x: es_tienda(x) or x['EsAsesor'], axis=1
    )].copy()

    df_chats_filtrados['Persona'] = df_chats_filtrados.apply(
        cambiar_nombre_tienda, axis=1
    )

    # Eliminar filas con multimedia omitido
    df_chats_filtrados = df_chats_filtrados[
        df_chats_filtrados['Mensaje'] != "<Multimedia omitido>"
    ].copy()

    # ----------------------------------------------------
    # 5) Filtrar por rango de fechas
    # ----------------------------------------------------
    # Conviertan fecha_inicio / fecha_fin a datetime
    fecha_i = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    fecha_f = datetime.strptime(fecha_fin, "%Y-%m-%d")

    df_chats_filtrados = df_chats_filtrados[
        (df_chats_filtrados['FechaHora'] >= fecha_i) &
        (df_chats_filtrados['FechaHora'] <= fecha_f)
    ]

    if df_chats_filtrados.empty:
        print(
            f"No hay datos para {POC_NAME} en el rango {fecha_inicio} - {fecha_fin}")
        return None  # O podrías devolver un DF vacío

    df_chats_filtrados.sort_values(
        by='FechaHora', inplace=True, ignore_index=True)

    # “Desplazar” filas para conocer mensaje siguiente
    df_chats_filtrados['NextPersona'] = df_chats_filtrados['Persona'].shift(-1)
    df_chats_filtrados['NextFechaHora'] = df_chats_filtrados['FechaHora'].shift(
        -1)
    df_chats_filtrados['NextMensaje'] = df_chats_filtrados['Mensaje'].shift(-1)

    # Filtramos solo casos donde (mensaje actual es de Asesor) y (siguiente mensaje es de la Tienda)
    mask_asesor_tienda = (
        (df_chats_filtrados['EsAsesor'] == True) &
        (df_chats_filtrados['NextPersona'].str.upper().str.contains("TIENDA"))
    )
    df_respuestas = df_chats_filtrados[mask_asesor_tienda].copy()

    # ----------------------------------------------------
    # 6) Cálculo de tiempo de respuesta
    # ----------------------------------------------------
    df_respuestas['TiempoRespuestaMin'] = (
        df_respuestas['NextFechaHora'] - df_respuestas['FechaHora']
    ).dt.total_seconds() / 60.0

    # Función de puntaje
    def calcular_puntaje(minutos):
        if minutos < 5:
            return 100
        elif minutos < 15:
            return 80
        elif minutos < 30:
            return 50
        elif minutos < 60:
            return 30
        else:
            return 0

    df_respuestas['Puntaje'] = df_respuestas['TiempoRespuestaMin'].apply(
        calcular_puntaje)

    tiempo_promedio = df_respuestas['TiempoRespuestaMin'].mean()  # float (min)
    tiempo_total = df_respuestas['TiempoRespuestaMin'].sum()      # float (min)
    # float (0-100)
    puntaje_promedio = df_respuestas['Puntaje'].mean()

    # ----------------------------------------------------
    # 7) Análisis de sentimiento (utiliza modelo multilingüe)
    # ----------------------------------------------------
    def analizar_sentimiento(texto):
        """
        Aplica el pipeline de sentiment-analysis y retorna una etiqueta textual.
        """
        if not isinstance(texto, str) or not texto.strip():
            return "Neutral"

        resultado = modelo_sentimiento(texto)[0]
        estrellas = int(resultado['label'][0])  # extraer el dígito (1-5)

        if estrellas == 1:
            return "Muy Negativo"
        elif estrellas == 2:
            return "Negativo"
        elif estrellas == 3:
            return "Neutral"
        elif estrellas == 4:
            return "Positivo"
        elif estrellas == 5:
            return "Muy Positivo"

    df_respuestas['Sentimiento'] = df_respuestas['Mensaje'].apply(
        analizar_sentimiento)

    # Unir "Muy Positivo" con "Positivo" y "Muy Negativo" con "Negativo"
    df_respuestas['Sentimiento'] = df_respuestas['Sentimiento'].replace({
        "Muy Positivo": "Positivo",
        "Muy Negativo": "Negativo"
    })

    porcentaje_sentimientos = df_respuestas['Sentimiento'].value_counts(
        normalize=True) * 100

    # ----------------------------------------------------
    # 8) Resultados por consola
    # ----------------------------------------------------
    def formatear_tiempo_en_horas_minutos(minutos):
        total_segundos = int(minutos * 60)
        horas = total_segundos // 3600
        sobrante_segundos = total_segundos % 3600
        mins = sobrante_segundos // 60
        return f"{horas}h:{mins}m"

    print("\n=========================================")
    print(f"Resultados para: {POC_NAME}")
    print(f"Rango de fechas: {fecha_inicio} a {fecha_fin}")
    print("-----------------------------------------")

    if not df_respuestas.empty:
        print("Tiempo respuesta promedio:",
              formatear_tiempo_en_horas_minutos(tiempo_promedio))
        # Ejemplo de métrica aleatoria: tiempo mensual consumido
        # Ajusta la lógica según tus cálculos
        print("Tiempo total (min) =", round(tiempo_total, 2), "=>",
              formatear_tiempo_en_horas_minutos(tiempo_total))

        print("Puntaje promedio:", round(puntaje_promedio, 2))
        print("\nPorcentaje de sentimientos:")
        print(porcentaje_sentimientos)
    else:
        print(
            "No hubo mensajes [Asesor -> Tienda] que analizar en este rango.")

    # Retorna el DataFrame si quieres seguir manipulándolo
    return df_respuestas


class Command(BaseCommand):
    help = "Ejecuta análisis de chats para varios POCs, con rango de fechas mensual."

    def handle(self, *args, **options):
        # --------------------------------------------------------
        # 1) Definir la lista de POCs a analizar (quemada)
        # --------------------------------------------------------
        lista_pocs = [
            {
                "POC_NAME": "TADA ALBORADA",
                "ruta_archivo": "./chats/alborada.txt"
            },
            {
                "POC_NAME": "+593 96 239 8472",
                "ruta_archivo": './chats/sangolqui.txt'
            },
            # Agrega más diccionarios con POC_NAME y ruta_archivo según necesites
        ]

        # --------------------------------------------------------
        # 2) Rango global de fechas
        #    (Se realizará un análisis mes a mes dentro de este rango)
        # --------------------------------------------------------
        fecha_inicio_global = "2024-10-01"
        fecha_fin_global = "2024-12-31"

        # Convirtiendo a objetos datetime
        dt_inicio = datetime.strptime(fecha_inicio_global, "%Y-%m-%d")
        dt_fin = datetime.strptime(fecha_fin_global, "%Y-%m-%d")

        # --------------------------------------------------------
        # 3) Preparar el modelo de análisis de sentimiento
        # --------------------------------------------------------
        modelo_sentimiento = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment"
        )

        # --------------------------------------------------------
        # 4) Iteración MENSUAL por cada POC dentro de [dt_inicio, dt_fin]
        # --------------------------------------------------------
        for poc in lista_pocs:
            POC_NAME = poc["POC_NAME"]
            ruta_archivo = poc["ruta_archivo"]

            # Recorremos mes a mes
            for dt in rrule(MONTHLY, dtstart=dt_inicio, until=dt_fin):
                # Fecha de inicio de mes
                fecha_inicio_str = dt.strftime("%Y-%m-%d")

                # Para obtener el último día del mismo mes, podemos usar:
                # 1) sumamos un mes, restamos 1 día
                # 2) o usar rrule con BYMONTHDAY=-1, etc.
                # Aquí, de forma simple:
                # saltar al mes siguiente
                mes_siguiente = dt.replace(day=28) + pd.DateOffset(days=4)
                ultimo_dia_mes = mes_siguiente - \
                    pd.DateOffset(days=mes_siguiente.day)

                # Asegurarnos de no pasarnos del rango global
                if ultimo_dia_mes > dt_fin:
                    ultimo_dia_mes = dt_fin

                fecha_fin_str = ultimo_dia_mes.strftime("%Y-%m-%d")

                # Análisis
                analizar_chat(
                    POC_NAME=POC_NAME,
                    ruta_archivo=ruta_archivo,
                    fecha_inicio=fecha_inicio_str,
                    fecha_fin=fecha_fin_str,
                    modelo_sentimiento=modelo_sentimiento
                )
