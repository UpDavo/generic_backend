import re
import pandas as pd
from datetime import datetime


class PocService:

    def analizar_chat(POC_NAME, ruta_archivo, fecha_inicio, fecha_fin, modelo_sentimiento):

        patron_linea = re.compile(
            r'^(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2}) - (.*?): (.*)$'
        )
        datos = []
        ultima_fecha = None
        ultima_hora = None
        ultima_persona = None
        ultimo_mensaje = []

        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            for linea in f:
                linea = linea.strip()
                match = patron_linea.match(linea)
                if match:
                    if ultima_fecha and ultima_persona is not None:
                        datos.append([
                            ultima_fecha,
                            ultima_hora,
                            ultima_persona,
                            "\n".join(ultimo_mensaje)
                        ])
                    fecha_str = match.group(1)
                    hora_str = match.group(2)
                    persona = match.group(3)
                    mensaje = match.group(4)

                    try:
                        fecha_hora = datetime.strptime(
                            f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M"
                        )
                    except ValueError:
                        continue

                    ultima_fecha = fecha_hora.date()
                    ultima_hora = fecha_hora.time()
                    ultima_persona = persona
                    ultimo_mensaje = [mensaje]

                else:
                    if ultima_persona is not None:
                        ultimo_mensaje.append(linea)

        if ultima_fecha and ultima_persona is not None:
            datos.append([
                ultima_fecha,
                ultima_hora,
                ultima_persona,
                "\n".join(ultimo_mensaje)
            ])

        df_chats = pd.DataFrame(
            datos, columns=['Fecha', 'Hora', 'Persona', 'Mensaje'])

        df_chats['FechaHora'] = df_chats.apply(
            lambda x: datetime.combine(x['Fecha'], x['Hora']), axis=1
        )

        df_chats.sort_values(by='FechaHora', inplace=True, ignore_index=True)

        asesores = df_chats[
            df_chats['Mensaje'].str.contains(
                "Me pongo a sus órdenes", case=False, na=False)
        ]['Persona'].unique()

        df_chats['EsAsesor'] = df_chats['Persona'].isin(asesores)

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

        df_chats_filtrados = df_chats_filtrados[
            df_chats_filtrados['Mensaje'] != "<Multimedia omitido>"
        ].copy()

        fecha_i = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        fecha_f = datetime.strptime(fecha_fin, "%Y-%m-%d")

        df_chats_filtrados = df_chats_filtrados[
            (df_chats_filtrados['FechaHora'] >= fecha_i) &
            (df_chats_filtrados['FechaHora'] <= fecha_f)
        ]

        if df_chats_filtrados.empty:
            return {
                "start": fecha_inicio,
                "end": fecha_fin,
                "response_time": 0,
                "total_time": 0,
                "score": 0,
                "sentiment_distribution": {}

            }

        df_chats_filtrados.sort_values(
            by='FechaHora', inplace=True, ignore_index=True)

        df_chats_filtrados['NextPersona'] = df_chats_filtrados['Persona'].shift(
            -1)
        df_chats_filtrados['NextFechaHora'] = df_chats_filtrados['FechaHora'].shift(
            -1)
        df_chats_filtrados['NextMensaje'] = df_chats_filtrados['Mensaje'].shift(
            -1)

        mask_asesor_tienda = (
            (df_chats_filtrados['EsAsesor'] == True) &
            (df_chats_filtrados['NextPersona'].str.upper(
            ).str.contains("TIENDA"))
        )
        df_respuestas = df_chats_filtrados[mask_asesor_tienda].copy()

        if df_respuestas.empty:
            return {
                "start": fecha_inicio,
                "end": fecha_fin,
                "response_time": 0,
                "total_time": 0,
                "score": 0,
                "sentiment_distribution": {}
            }

        df_respuestas['TiempoRespuestaMin'] = (
            df_respuestas['NextFechaHora'] - df_respuestas['FechaHora']
        ).dt.total_seconds() / 60.0

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

        # float (min)
        tiempo_promedio = df_respuestas['TiempoRespuestaMin'].mean()
        # float (min)
        tiempo_total = df_respuestas['TiempoRespuestaMin'].sum()
        # float (0-100)
        puntaje_promedio = df_respuestas['Puntaje'].mean()

        def analizar_sentimiento(texto):
            if not isinstance(texto, str) or not texto.strip():
                return "Neutral"

            resultado = modelo_sentimiento(texto)[0]
            estrellas = int(resultado['label'][0])

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

        df_respuestas['Sentimiento'] = df_respuestas['Sentimiento'].replace({
            "Muy Positivo": "Positivo",
            "Muy Negativo": "Negativo"
        })

        porcentaje_sentimientos = df_respuestas['Sentimiento'].value_counts(
            normalize=True).mul(100).to_dict()

        def formatear_tiempo_en_horas_minutos(minutos):
            total_segundos = int(minutos * 60)
            horas = total_segundos // 3600
            sobrante_segundos = total_segundos % 3600
            mins = sobrante_segundos // 60
            return f"{horas}h:{mins}m"

        tiempo = formatear_tiempo_en_horas_minutos(tiempo_promedio)
        horas = formatear_tiempo_en_horas_minutos(tiempo_total)

        puntaje = round(puntaje_promedio, 2)

        return {"start": fecha_inicio, "end": fecha_fin, "response_time": tiempo, "total_time": horas, "score": puntaje, "sentiment_distribution": porcentaje_sentimientos}
