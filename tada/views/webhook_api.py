from io import BytesIO
from django.http import HttpResponse
import openpyxl
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q
from decimal import Decimal
from datetime import datetime
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
import pytz
from tada.models.webhookLog import WebhookLog
from tada.models import AppPrice, Price
from tada.utils.constants import APPS, APP_NAMES
from core.services.whatsapp_service import WhatsAppService
from core.models import EmailNotification, EmailNotificationType
from tada.utils.encryption import EncryptionService


class WebhookReceiverCancelledView(APIView):
    """Vista para recibir webhooks de servicios externos"""
    pagination_class = PageNumberPagination

    def get_permissions(self):
        """GET requiere autenticación, POST no"""
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        """
        Obtiene la lista de webhooks cancelados con paginación.

        Query params opcionales:
        - email: Filtrar por email específico
        - start_date: Fecha inicial (YYYY-MM-DD)
        - end_date: Fecha final (YYYY-MM-DD)
        - source: Filtrar por source
        - page: Número de página (por defecto: 1)
        - page_size: Tamaño de página (por defecto: 10)
        """
        try:
            # Obtener parámetros de filtro
            email = request.query_params.get('email')
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            source = request.query_params.get('source')

            # Construir query base
            queryset = WebhookLog.objects.filter(
                deleted_at__isnull=True
            ).order_by('-created_at')

            # Aplicar filtros
            if email:
                queryset = queryset.filter(payload__email=email)

            if start_date:
                try:
                    start_dt = parse_datetime(start_date)
                    if start_dt is None:
                        start_dt = datetime.fromisoformat(start_date)
                    queryset = queryset.filter(date__gte=start_dt.date())
                except (ValueError, TypeError):
                    pass

            if end_date:
                try:
                    end_dt = parse_datetime(end_date)
                    if end_dt is None:
                        end_dt = datetime.fromisoformat(end_date)
                    queryset = queryset.filter(date__lte=end_dt.date())
                except (ValueError, TypeError):
                    pass

            if source:
                queryset = queryset.filter(source=source)

            # Aplicar paginación
            paginator = self.pagination_class()
            paginated_queryset = paginator.paginate_queryset(queryset, request)

            # Serializar resultados
            guayaquil_tz = pytz.timezone('America/Guayaquil')
            results = []
            for log in paginated_queryset:
                # Desencriptar payload
                decrypted_payload = EncryptionService.decrypt_data(log.payload)
                if decrypted_payload is None:
                    decrypted_payload = log.payload  # Fallback si falla la desencriptación
                
                # Convertir created_at a hora de Guayaquil si existe
                created_at_gye = None
                if hasattr(log, 'created_at') and log.created_at:
                    created_at_gye = log.created_at.astimezone(guayaquil_tz).isoformat()
                
                # Convertir edited_at a hora de Guayaquil si existe
                edited_at_gye = None
                if log.edited_at:
                    edited_at_gye = log.edited_at.astimezone(guayaquil_tz).isoformat()
                
                # Obtener nombre del usuario que editó
                edited_by_name = None
                if log.edited_by:
                    edited_by_name = f"{log.edited_by.first_name} {log.edited_by.last_name}".strip() or log.edited_by.email
                
                results.append({
                    'id': log.id,
                    'name': decrypted_payload.get('name', 'N/A'),
                    'email': decrypted_payload.get('email', 'N/A'),
                    'source': log.source,
                    'event_type': log.event_type,
                    'date': log.date.strftime('%Y-%m-%d'),
                    'time': log.time.strftime('%H:%M:%S'),
                    'payload': decrypted_payload,
                    'created_at': created_at_gye,
                    # Campos adicionales de edición
                    'poc': log.poc,
                    'comment': log.comment,
                    'repurchased': log.repurchased,
                    'is_edited': log.is_edited,
                    'edited_by': edited_by_name,
                    'edited_at': edited_at_gye
                })
                
            # print(results)

            # Retornar respuesta paginada
            return paginator.get_paginated_response(results)

        except Exception as e:
            print(f"❌ Error obteniendo webhooks: {str(e)}")
            return Response({
                "error": "Error obteniendo webhooks",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """
        Recibe el webhook y crea un log.

        Ejemplo de payload esperado:
        {
            "name": "Nombre",
            "email": "cancelado@gmail.com"
        }
        """
        try:
            payload = request.data

            # Extraer información del payload
            source = payload.get('source', 'cancelled_orders')
            event_type = payload.get('event_type', 'order_cancelled')
            name = payload.get('name', 'unknown')
            email = payload.get('email', 'unknown')
            
            # Ofuscar email para mostrar parcialmente (ej: j***@gmail.com)
            masked_email = email
            if email and '@' in email:
                local, domain = email.split('@', 1)
                if len(local) > 2:
                    masked_email = f"{local[0]}{'*' * (len(local) - 1)}@{domain}"
                elif len(local) == 2:
                    masked_email = f"{local[0]}*@{domain}"
                else:
                    masked_email = f"*@{domain}"

            # Encriptar el payload antes de guardarlo
            encrypted_payload = EncryptionService.encrypt_data(payload)
            if encrypted_payload is None:
                # Si falla la encriptación, usar el payload original
                encrypted_payload = payload
                print("⚠️ No se pudo encriptar el payload, guardando sin encriptar")

            # Crear el log del webhook con payload encriptado
            webhook_log = WebhookLog.objects.create(
                payload=encrypted_payload,
                source=source,
                event_type=event_type,
                date=now().date(),
                time=now().time(),
                app=str(APPS['WEBHOOK'])
            )

            # Enviar notificación por WhatsApp
            try:
                whatsapp_service = WhatsAppService()

                # Obtener números de teléfono configurados para CANCELLED_WEBHOOK
                phone_numbers = EmailNotification.get_numbers_by_type_constant(
                    notification_type_constant=EmailNotificationType.CANCELLED_WEBHOOK
                )
                phone_numbers = list(phone_numbers)

                # Si no hay números configurados, usar número por defecto
                if not phone_numbers:
                    phone_numbers = ['+593994504722']
                    print(
                        "No hay números configurados para CANCELLED_WEBHOOK, usando número por defecto")

                # Crear mensaje de WhatsApp
                message_text = f"*Nuevo pedido cancelado de:*\n\n{name}\n"
                message_text += f"{masked_email}\n\n"
                message_text += f"Revisar en hint:\n\n"
                message_text += f"https://hint.heimdal.ec/dashboard/webhooks"

                # Enviar mensaje a cada número configurado
                for phone_number in phone_numbers:
                    try:
                        response_data, response = whatsapp_service.send_message(
                            to=phone_number,
                            text=message_text
                        )

                        if response.status_code == 200:
                            print(
                                f"✅ Notificación WhatsApp enviada a {phone_number}")
                        else:
                            print(
                                f"❌ Error al enviar WhatsApp a {phone_number}: {response_data}")
                    except Exception as phone_error:
                        print(
                            f"⚠️ Error al enviar a {phone_number}: {str(phone_error)}")

            except Exception as whatsapp_error:
                print(
                    f"⚠️ Error al enviar notificación WhatsApp: {str(whatsapp_error)}")
                # No fallar el webhook si WhatsApp falla

            return Response({
                "message": "Webhook recibido exitosamente",
                "log_id": webhook_log.id,
                "name": name,
                "email": email
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"❌ Error procesando webhook: {str(e)}")
            return Response({
                "error": "Error procesando webhook",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WebhookLogsStatsView(APIView):
    """Vista para obtener estadísticas de WebhookLogs con precios"""
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
                try:
                    start_dt = parse_datetime(start_date)
                    if start_dt is None:
                        start_dt = datetime.fromisoformat(start_date)
                except (ValueError, TypeError):
                    start_dt = datetime.now()

                # Buscar precio del mes específico
                target_month = start_dt.replace(day=1).date()
                price_obj = Price.objects.filter(
                    app=app,
                    month=target_month,
                    deleted_at__isnull=True
                ).first()

                if price_obj:
                    return price_obj

                # Si no existe, buscar el más reciente anterior a esa fecha
                price_obj = Price.objects.filter(
                    app=app,
                    month__lt=target_month,
                    deleted_at__isnull=True
                ).order_by('-month').first()

                if price_obj:
                    return price_obj

            # Si no hay start_date o no se encontró precio, usar el más reciente
            return Price.objects.filter(
                app=app,
                deleted_at__isnull=True
            ).order_by('-month').first()

        except Exception:
            return None

    def get(self, request):
        # Obtener parámetros de filtro de fecha
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        source = request.query_params.get('source')
        event_type = request.query_params.get('event_type')

        # Construir filtros de fecha
        date_filters = Q()
        if start_date:
            try:
                start_dt = parse_datetime(start_date)
                if start_dt is None:
                    start_dt = datetime.fromisoformat(start_date)
                date_filters &= Q(date__gte=start_dt.date())
            except (ValueError, TypeError):
                pass

        if end_date:
            try:
                end_dt = parse_datetime(end_date)
                if end_dt is None:
                    end_dt = datetime.fromisoformat(end_date)
                date_filters &= Q(date__lte=end_dt.date())
            except (ValueError, TypeError):
                pass

        # Filtros adicionales
        if source:
            date_filters &= Q(source=source)

        if event_type:
            date_filters &= Q(event_type=event_type)

        # Obtener estadísticas generales de webhook logs
        total_logs = WebhookLog.objects.filter(date_filters).count()

        # Obtener desglose por source
        logs_by_source = WebhookLog.objects.filter(date_filters).values('source').annotate(
            count=Count('id')
        ).order_by('-count')

        # Obtener desglose por event_type
        logs_by_event_type = WebhookLog.objects.filter(date_filters).values('event_type').annotate(
            count=Count('id')
        ).order_by('-count')

        # Obtener precio para la app WEBHOOK según el período
        price_instance = self._get_price_for_period(
            str(APPS['WEBHOOK']), start_date, end_date)

        # Obtener el nombre del AppPrice si existe
        app_price_name = None
        try:
            app_price = AppPrice.objects.filter(
                price=price_instance, deleted_at__isnull=True).first()
            if app_price:
                app_price_name = app_price.name
        except AppPrice.DoesNotExist:
            pass

        if price_instance:
            unit_price = Decimal(str(price_instance.value))
            total_cost = unit_price * Decimal(str(total_logs))
            price_month = price_instance.month.strftime('%Y-%m')
        else:
            unit_price = Decimal('0')
            total_cost = Decimal('0')
            price_month = None

        return Response({
            'app_type': 'WEBHOOK',
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'source': source,
                'event_type': event_type
            },
            'summary': {
                'total_logs': total_logs,
                'app_name': APP_NAMES[APPS['WEBHOOK']],
                'app_price_name': app_price_name,
                'unit_price': str(unit_price),
                'total_cost': str(total_cost),
                'price_month': price_month
            },
            'breakdown': {
                'by_source': list(logs_by_source),
                'by_event_type': list(logs_by_event_type)
            }
        }, status=status.HTTP_200_OK)


class WebhookCancelledDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Obtener parámetros de filtro
        email = request.query_params.get('email')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        source = request.query_params.get('source')

        # Construir query base
        queryset = WebhookLog.objects.filter(
            deleted_at__isnull=True
        ).order_by('-created_at')

        # Aplicar filtros
        if email:
            queryset = queryset.filter(payload__email=email)

        if start_date:
            try:
                start_dt = parse_datetime(start_date)
                if start_dt is None:
                    start_dt = datetime.fromisoformat(start_date)
                queryset = queryset.filter(date__gte=start_dt.date())
            except (ValueError, TypeError):
                pass

        if end_date:
            try:
                end_dt = parse_datetime(end_date)
                if end_dt is None:
                    end_dt = datetime.fromisoformat(end_date)
                queryset = queryset.filter(date__lte=end_dt.date())
            except (ValueError, TypeError):
                pass

        if source:
            queryset = queryset.filter(source=source)

        # Crear workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Webhooks Cancelados"

        # Cabeceras
        headers = ["ID", "Nombre", "Email", "Source",
                   "Tipo de Evento", "Fecha", "Hora", "POC", "Comentario", 
                   "Recompró", "Editado Por", "Fecha Edición"]
        ws.append(headers)

        # Configurar zona horaria de Guayaquil
        guayaquil_tz = pytz.timezone('America/Guayaquil')

        # Contenido
        for log in queryset:
            # Desencriptar payload
            decrypted_payload = EncryptionService.decrypt_data(log.payload)
            if decrypted_payload is None:
                decrypted_payload = log.payload  # Fallback si falla la desencriptación
            
            # Obtener nombre del usuario que editó
            edited_by_name = ""
            if log.edited_by:
                edited_by_name = f"{log.edited_by.first_name} {log.edited_by.last_name}".strip() or log.edited_by.email
            
            # Convertir edited_at a hora de Guayaquil
            edited_at_str = ""
            if log.edited_at:
                edited_at_gye = log.edited_at.astimezone(guayaquil_tz)
                edited_at_str = edited_at_gye.strftime("%Y-%m-%d %H:%M:%S")
            
            ws.append([
                log.id,
                decrypted_payload.get('name', 'N/A'),
                decrypted_payload.get('email', 'N/A'),
                log.source,
                log.event_type,
                log.date.strftime("%Y-%m-%d") if log.date else "",
                log.time.strftime("%H:%M:%S") if log.time else "",
                log.poc or "",
                log.comment or "",
                "Sí" if log.repurchased else "No",
                edited_by_name,
                edited_at_str
            ])

        # Preparar archivo
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename=webhook_cancelled_logs.xlsx'
        return response


class WebhookCancelledUpdateView(APIView):
    """Vista para actualizar información adicional de un webhook cancelado (solo una vez)"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        """
        Actualiza un webhook con información adicional.
        Solo se puede editar una vez.
        
        Campos editables:
        - poc: Punto de venta de origen
        - comment: Comentario
        - repurchased: Booleano si volvió a comprar
        """
        try:
            # Obtener el webhook
            webhook = WebhookLog.objects.get(pk=pk, deleted_at__isnull=True)
            
            # Verificar si ya fue editado
            if webhook.is_edited:
                return Response({
                    "error": "Este webhook ya fue editado y no se puede modificar nuevamente",
                    "edited_by": webhook.edited_by.email if webhook.edited_by else None,
                    "edited_at": webhook.edited_at.isoformat() if webhook.edited_at else None
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Obtener datos del request
            poc = request.data.get('poc')
            comment = request.data.get('comment')
            repurchased = request.data.get('repurchased')
            
            # Validar que al menos un campo esté presente
            if poc is None and comment is None and repurchased is None:
                return Response({
                    "error": "Debe proporcionar al menos un campo para actualizar (poc, comment, repurchased)"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Actualizar campos
            if poc is not None:
                webhook.poc = poc
            if comment is not None:
                webhook.comment = comment
            if repurchased is not None:
                webhook.repurchased = repurchased
            
            # Marcar como editado
            webhook.is_edited = True
            webhook.edited_by = request.user
            webhook.edited_at = now()
            webhook.save()
            
            # Desencriptar payload para la respuesta
            decrypted_payload = EncryptionService.decrypt_data(webhook.payload)
            if decrypted_payload is None:
                decrypted_payload = webhook.payload
            
            # Convertir edited_at a hora de Guayaquil
            guayaquil_tz = pytz.timezone('America/Guayaquil')
            edited_at_gye = None
            if webhook.edited_at:
                edited_at_gye = webhook.edited_at.astimezone(guayaquil_tz).isoformat()
            
            return Response({
                "message": "Webhook actualizado exitosamente",
                "webhook": {
                    "id": webhook.id,
                    "name": decrypted_payload.get('name', 'N/A'),
                    "email": decrypted_payload.get('email', 'N/A'),
                    "source": webhook.source,
                    "event_type": webhook.event_type,
                    "date": webhook.date.strftime('%Y-%m-%d'),
                    "time": webhook.time.strftime('%H:%M:%S'),
                    "poc": webhook.poc,
                    "comment": webhook.comment,
                    "repurchased": webhook.repurchased,
                    "is_edited": webhook.is_edited,
                    "edited_by": webhook.edited_by.email if webhook.edited_by else None,
                    "edited_at": edited_at_gye
                }
            }, status=status.HTTP_200_OK)
            
        except WebhookLog.DoesNotExist:
            return Response({
                "error": "Webhook no encontrado"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"❌ Error actualizando webhook: {str(e)}")
            return Response({
                "error": "Error al actualizar webhook",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
