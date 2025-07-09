from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from decimal import Decimal
from datetime import datetime
from django.utils.dateparse import parse_datetime
from tada.models import NotificationLog, CanvasLog, TrafficLog, ExecutionLog, AppPrice, Price
from tada.utils.constants import APPS, APP_NAMES
from authentication.models import CustomUser


class NotificationLogsStatsView(APIView):
    """Vista para obtener estadísticas de NotificationLogs por usuario con precios"""
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
                # Convertir start_date a datetime si es string
                if isinstance(start_date, str):
                    start_datetime = parse_datetime(start_date)
                    if not start_datetime:
                        start_datetime = datetime.strptime(
                            start_date, '%Y-%m-%d')
                else:
                    start_datetime = start_date

                # Buscar precio para el mes específico
                target_month = start_datetime.replace(day=1).date()
                price = Price.objects.filter(
                    app=app,
                    month=target_month,
                    deleted_at__isnull=True
                ).first()

                if price:
                    return price

                # Si no hay precio para ese mes, buscar el más reciente anterior
                price = Price.objects.filter(
                    app=app,
                    month__lte=target_month,
                    deleted_at__isnull=True
                ).order_by('-month').first()

                if price:
                    return price

            # Fallback: precio más reciente disponible
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

        # Construir filtros de fecha
        date_filters = Q()
        if start_date:
            try:
                start_datetime = parse_datetime(start_date)
                if not start_datetime:
                    # Si no incluye hora, agregar 00:00:00
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                date_filters &= Q(sent_at__gte=start_datetime)
            except ValueError:
                return Response({"error": "Formato de start_date inválido. Use YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS"},
                                status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_datetime = parse_datetime(end_date)
                if not end_datetime:
                    # Si no incluye hora, agregar 23:59:59
                    end_datetime = datetime.strptime(
                        end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                date_filters &= Q(sent_at__lte=end_datetime)
            except ValueError:
                return Response({"error": "Formato de end_date inválido. Use YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS"},
                                status=status.HTTP_400_BAD_REQUEST)

        # Obtener estadísticas agrupadas por usuario con filtros de fecha
        users_stats = []

        # Obtener todos los usuarios que han enviado notificaciones en el rango de fechas
        users_with_logs = NotificationLog.objects.filter(
            date_filters).values('user').distinct()

        for user_data in users_with_logs:
            user_id = user_data['user']
            try:
                user = CustomUser.objects.get(id=user_id)

                # Contar logs por usuario en el rango de fechas
                total_logs = NotificationLog.objects.filter(
                    user=user).filter(date_filters).count()

                # Obtener precio para la app PUSH según la fecha de los logs
                try:
                    # Buscar el precio más apropiado para el período consultado
                    price_instance = self._get_price_for_period(
                        str(APPS['PUSH']), start_date, end_date)

                    if price_instance:
                        unit_price = price_instance.value
                        total_cost = unit_price * total_logs

                        # Obtener el nombre del AppPrice si existe
                        app_price_name = None
                        try:
                            app_price = AppPrice.objects.get(
                                app=str(APPS['PUSH']), deleted_at__isnull=True)
                            app_price_name = app_price.name
                        except AppPrice.DoesNotExist:
                            pass

                        users_stats.append({
                            'user_id': user.id,
                            'user_email': user.email,
                            'user_first_name': user.first_name,
                            'user_last_name': user.last_name,
                            'total_logs': total_logs,
                            'app_name': APP_NAMES[APPS['PUSH']],
                            'app_price_name': app_price_name,
                            'unit_price': str(unit_price),
                            'total_cost': str(total_cost),
                            'price_month': price_instance.month.strftime('%Y-%m-%d')
                        })
                    else:
                        users_stats.append({
                            'user_id': user.id,
                            'user_email': user.email,
                            'user_first_name': user.first_name,
                            'user_last_name': user.last_name,
                            'total_logs': total_logs,
                            'app_name': APP_NAMES[APPS['PUSH']],
                            'app_price_name': None,
                            'unit_price': '0.00',
                            'total_cost': '0.00',
                            'price_month': None
                        })
                except Exception as e:
                    users_stats.append({
                        'user_id': user.id,
                        'user_email': user.email,
                        'user_first_name': user.first_name,
                        'user_last_name': user.last_name,
                        'total_logs': total_logs,
                        'app_name': APP_NAMES[APPS['PUSH']],
                        'app_price_name': None,
                        'unit_price': '0.00',
                        'total_cost': '0.00',
                        'price_month': None
                    })
            except CustomUser.DoesNotExist:
                continue

        # Calcular totales generales
        total_logs_general = sum(stat['total_logs'] for stat in users_stats)
        total_cost_general = sum(
            Decimal(stat['total_cost']) for stat in users_stats)

        return Response({
            'app_type': 'PUSH',
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            },
            'users_stats': users_stats,
            'summary': {
                'total_users': len(users_stats),
                'total_logs': total_logs_general,
                'total_cost': str(total_cost_general)
            }
        }, status=status.HTTP_200_OK)


class CanvasLogsStatsView(APIView):
    """Vista para obtener estadísticas de CanvasLogs por usuario con precios"""
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
                # Convertir start_date a datetime si es string
                if isinstance(start_date, str):
                    start_datetime = parse_datetime(start_date)
                    if not start_datetime:
                        start_datetime = datetime.strptime(
                            start_date, '%Y-%m-%d')
                else:
                    start_datetime = start_date

                # Buscar precio para el mes específico
                target_month = start_datetime.replace(day=1).date()
                price = Price.objects.filter(
                    app=app,
                    month=target_month,
                    deleted_at__isnull=True
                ).first()

                if price:
                    return price

                # Si no hay precio para ese mes, buscar el más reciente anterior
                price = Price.objects.filter(
                    app=app,
                    month__lte=target_month,
                    deleted_at__isnull=True
                ).order_by('-month').first()

                if price:
                    return price

            # Fallback: precio más reciente disponible
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

        # Construir filtros de fecha
        date_filters = Q()
        if start_date:
            try:
                start_datetime = parse_datetime(start_date)
                if not start_datetime:
                    # Si no incluye hora, agregar 00:00:00
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                date_filters &= Q(sent_at__gte=start_datetime)
            except ValueError:
                return Response({"error": "Formato de start_date inválido. Use YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS"},
                                status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_datetime = parse_datetime(end_date)
                if not end_datetime:
                    # Si no incluye hora, agregar 23:59:59
                    end_datetime = datetime.strptime(
                        end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                date_filters &= Q(sent_at__lte=end_datetime)
            except ValueError:
                return Response({"error": "Formato de end_date inválido. Use YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS"},
                                status=status.HTTP_400_BAD_REQUEST)

        # Obtener estadísticas agrupadas por usuario con filtros de fecha
        users_stats = []

        # Obtener todos los usuarios que han enviado canvas en el rango de fechas
        users_with_logs = CanvasLog.objects.filter(
            date_filters).values('user').distinct()

        for user_data in users_with_logs:
            user_id = user_data['user']
            try:
                user = CustomUser.objects.get(id=user_id)

                # Contar logs por usuario en el rango de fechas
                total_logs = CanvasLog.objects.filter(
                    user=user).filter(date_filters).count()

                # Obtener precio para la app CANVAS según la fecha de los logs
                try:
                    # Buscar el precio más apropiado para el período consultado
                    price_instance = self._get_price_for_period(
                        str(APPS['CANVAS']), start_date, end_date)

                    if price_instance:
                        unit_price = price_instance.value
                        total_cost = unit_price * total_logs

                        # Obtener el nombre del AppPrice si existe
                        app_price_name = None
                        try:
                            app_price = AppPrice.objects.get(
                                app=str(APPS['CANVAS']), deleted_at__isnull=True)
                            app_price_name = app_price.name
                        except AppPrice.DoesNotExist:
                            pass

                        users_stats.append({
                            'user_id': user.id,
                            'user_email': user.email,
                            'user_first_name': user.first_name,
                            'user_last_name': user.last_name,
                            'total_logs': total_logs,
                            'app_name': APP_NAMES[APPS['CANVAS']],
                            'app_price_name': app_price_name,
                            'unit_price': str(unit_price),
                            'total_cost': str(total_cost),
                            'price_month': price_instance.month.strftime('%Y-%m-%d')
                        })
                    else:
                        users_stats.append({
                            'user_id': user.id,
                            'user_email': user.email,
                            'user_first_name': user.first_name,
                            'user_last_name': user.last_name,
                            'total_logs': total_logs,
                            'app_name': APP_NAMES[APPS['CANVAS']],
                            'app_price_name': None,
                            'unit_price': '0.00',
                            'total_cost': '0.00',
                            'price_month': None
                        })
                except Exception as e:
                    users_stats.append({
                        'user_id': user.id,
                        'user_email': user.email,
                        'user_first_name': user.first_name,
                        'user_last_name': user.last_name,
                        'total_logs': total_logs,
                        'app_name': APP_NAMES[APPS['CANVAS']],
                        'app_price_name': None,
                        'unit_price': '0.00',
                        'total_cost': '0.00',
                        'price_month': None
                    })
            except CustomUser.DoesNotExist:
                continue

        # Calcular totales generales
        total_logs_general = sum(stat['total_logs'] for stat in users_stats)
        total_cost_general = sum(
            Decimal(stat['total_cost']) for stat in users_stats)

        return Response({
            'app_type': 'CANVAS',
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            },
            'users_stats': users_stats,
            'summary': {
                'total_users': len(users_stats),
                'total_logs': total_logs_general,
                'total_cost': str(total_cost_general)
            }
        }, status=status.HTTP_200_OK)


class TrafficLogsStatsView(APIView):
    """Vista para obtener estadísticas de TrafficLogs generales con precios"""
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
                # Convertir start_date a datetime si es string
                if isinstance(start_date, str):
                    start_datetime = parse_datetime(start_date)
                    if not start_datetime:
                        start_datetime = datetime.strptime(
                            start_date, '%Y-%m-%d')
                else:
                    start_datetime = start_date

                # Buscar precio para el mes específico
                target_month = start_datetime.replace(day=1).date()
                price = Price.objects.filter(
                    app=app,
                    month=target_month,
                    deleted_at__isnull=True
                ).first()

                if price:
                    return price

                # Si no hay precio para ese mes, buscar el más reciente anterior
                price = Price.objects.filter(
                    app=app,
                    month__lte=target_month,
                    deleted_at__isnull=True
                ).order_by('-month').first()

                if price:
                    return price

            # Fallback: precio más reciente disponible
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

        # Construir filtros de fecha
        date_filters = Q()
        if start_date:
            try:
                start_datetime = parse_datetime(start_date)
                if not start_datetime:
                    # Si no incluye hora, usar solo la fecha
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                date_filters &= Q(date__gte=start_datetime.date())
            except ValueError:
                return Response({"error": "Formato de start_date inválido. Use YYYY-MM-DD"},
                                status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_datetime = parse_datetime(end_date)
                if not end_datetime:
                    # Si no incluye hora, usar solo la fecha
                    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                date_filters &= Q(date__lte=end_datetime.date())
            except ValueError:
                return Response({"error": "Formato de end_date inválido. Use YYYY-MM-DD"},
                                status=status.HTTP_400_BAD_REQUEST)

        # Obtener estadísticas generales de traffic logs
        total_logs = TrafficLog.objects.filter(date_filters).count()

        # Obtener precio para la app TRAFFIC según el período
        price_instance = self._get_price_for_period(
            str(APPS['TRAFFIC']), start_date, end_date)

        # Obtener el nombre del AppPrice si existe
        app_price_name = None
        try:
            app_price = AppPrice.objects.get(
                app=str(APPS['TRAFFIC']), deleted_at__isnull=True)
            app_price_name = app_price.name
        except AppPrice.DoesNotExist:
            pass

        if price_instance:
            unit_price = price_instance.value
            total_cost = unit_price * total_logs
            price_month = price_instance.month.strftime('%Y-%m-%d')
        else:
            unit_price = Decimal('0.00')
            total_cost = Decimal('0.00')
            price_month = None

        return Response({
            'app_type': 'TRAFFIC',
            'filters': {
                'start_date': start_date,
                'end_date': end_date
            },
            'summary': {
                'total_logs': total_logs,
                'app_name': APP_NAMES[APPS['TRAFFIC']],
                'app_price_name': app_price_name,
                'unit_price': str(unit_price),
                'total_cost': str(total_cost),
                'price_month': price_month
            }
        }, status=status.HTTP_200_OK)


class CombinedLogsStatsView(APIView):
    """Vista para obtener estadísticas combinadas de todos los tipos de logs"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notification_stats = NotificationLogsStatsView().get(request).data
        canvas_stats = CanvasLogsStatsView().get(request).data
        traffic_stats = TrafficLogsStatsView().get(request).data
        execution_stats = ExecutionLogsStatsView().get(request).data

        # Combinar estadísticas por usuario (solo Push y Canvas)
        all_users = {}

        # Procesar notification logs
        for user_stat in notification_stats['users_stats']:
            user_id = user_stat['user_id']
            all_users[user_id] = {
                'user_info': {
                    'user_id': user_stat['user_id'],
                    'user_email': user_stat['user_email'],
                    'user_first_name': user_stat['user_first_name'],
                    'user_last_name': user_stat['user_last_name']
                },
                'push_logs': {
                    'total_logs': user_stat['total_logs'],
                    'unit_price': user_stat['unit_price'],
                    'total_cost': user_stat['total_cost']
                },
                'canvas_logs': {
                    'total_logs': 0,
                    'unit_price': '0.00',
                    'total_cost': '0.00'
                }
            }

        # Procesar canvas logs
        for user_stat in canvas_stats['users_stats']:
            user_id = user_stat['user_id']
            if user_id in all_users:
                all_users[user_id]['canvas_logs'] = {
                    'total_logs': user_stat['total_logs'],
                    'unit_price': user_stat['unit_price'],
                    'total_cost': user_stat['total_cost']
                }
            else:
                all_users[user_id] = {
                    'user_info': {
                        'user_id': user_stat['user_id'],
                        'user_email': user_stat['user_email'],
                        'user_first_name': user_stat['user_first_name'],
                        'user_last_name': user_stat['user_last_name']
                    },
                    'push_logs': {
                        'total_logs': 0,
                        'unit_price': '0.00',
                        'total_cost': '0.00'
                    },
                    'canvas_logs': {
                        'total_logs': user_stat['total_logs'],
                        'unit_price': user_stat['unit_price'],
                        'total_cost': user_stat['total_cost']
                    }
                }

        # Calcular totales por usuario (solo Push y Canvas)
        users_combined_stats = []
        for user_id, data in all_users.items():
            total_logs = data['push_logs']['total_logs'] + \
                data['canvas_logs']['total_logs']
            total_cost = Decimal(data['push_logs']['total_cost']) + \
                Decimal(data['canvas_logs']['total_cost'])

            users_combined_stats.append({
                **data['user_info'],
                'push_logs': data['push_logs'],
                'canvas_logs': data['canvas_logs'],
                'total_logs': total_logs,
                'total_cost': str(total_cost)
            })

        return Response({
            'notification_logs_summary': notification_stats,
            'canvas_logs_summary': canvas_stats,
            'traffic_logs_summary': traffic_stats,
            'execution_logs_summary': execution_stats,
            'combined_users_stats': users_combined_stats,
            'grand_total': {
                'total_users': len(all_users),
                'total_push_logs': notification_stats['summary']['total_logs'],
                'total_canvas_logs': canvas_stats['summary']['total_logs'],
                'total_traffic_logs': traffic_stats['summary']['total_logs'],
                'total_execution_logs': execution_stats['summary']['total_logs'],
                'total_user_logs': notification_stats['summary']['total_logs'] + canvas_stats['summary']['total_logs'],
                'total_general_logs': traffic_stats['summary']['total_logs'] + execution_stats['summary']['total_logs'],
                'total_combined_logs': notification_stats['summary']['total_logs'] + canvas_stats['summary']['total_logs'] + traffic_stats['summary']['total_logs'] + execution_stats['summary']['total_logs'],
                'total_user_cost': str(Decimal(notification_stats['summary']['total_cost']) + Decimal(canvas_stats['summary']['total_cost'])),
                'total_general_cost': str(Decimal(traffic_stats['summary']['total_cost']) + Decimal(execution_stats['summary']['total_cost'])),
                'total_combined_cost': str(Decimal(notification_stats['summary']['total_cost']) + Decimal(canvas_stats['summary']['total_cost']) + Decimal(traffic_stats['summary']['total_cost']) + Decimal(execution_stats['summary']['total_cost']))
            }
        }, status=status.HTTP_200_OK)


class ExecutionLogsStatsView(APIView):
    """Vista para obtener estadísticas de ExecutionLogs generales con precios usando AppPrice"""
    permission_classes = [IsAuthenticated]

    def _get_price_for_period(self, app, start_date, end_date):
        """
        Obtiene el precio más apropiado para el período consultado.
        Similar a las otras vistas de estadísticas.
        """
        try:
            if start_date:
                # Convertir start_date a datetime si es string
                if isinstance(start_date, str):
                    start_datetime = parse_datetime(start_date)
                    if not start_datetime:
                        start_datetime = datetime.strptime(
                            start_date, '%Y-%m-%d')
                else:
                    start_datetime = start_date

                # Buscar precio para el mes específico
                target_month = start_datetime.replace(day=1).date()
                price = Price.objects.filter(
                    app=app,
                    month=target_month,
                    deleted_at__isnull=True
                ).first()

                if price:
                    return price

                # Si no hay precio para ese mes, buscar el más reciente anterior
                price = Price.objects.filter(
                    app=app,
                    month__lte=target_month,
                    deleted_at__isnull=True
                ).order_by('-month').first()

                if price:
                    return price

            # Fallback: precio más reciente disponible
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
        execution_type = request.query_params.get('execution_type')

        # Construir filtros de fecha
        date_filters = Q()
        if start_date:
            try:
                start_datetime = parse_datetime(start_date)
                if not start_datetime:
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                date_filters &= Q(date__gte=start_datetime.date())
            except ValueError:
                return Response({"error": "Formato de start_date inválido. Use YYYY-MM-DD"},
                                status=status.HTTP_400_BAD_REQUEST)

        if end_date:
            try:
                end_datetime = parse_datetime(end_date)
                if not end_datetime:
                    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                date_filters &= Q(date__lte=end_datetime.date())
            except ValueError:
                return Response({"error": "Formato de end_date inválido. Use YYYY-MM-DD"},
                                status=status.HTTP_400_BAD_REQUEST)

        # Filtro por tipo de ejecución si se especifica
        if execution_type:
            date_filters &= Q(execution_type=execution_type)

        # Obtener conteos por tipo de ejecución
        manual_logs = ExecutionLog.objects.filter(
            execution_type='manual').filter(date_filters).count()
        automatic_logs = ExecutionLog.objects.filter(
            execution_type='automatic').filter(date_filters).count()

        total_logs = manual_logs + automatic_logs

        # Obtener precio para la app EXECUTION usando AppPrice
        price_instance = self._get_price_for_period(
            str(APPS['EXECUTION']), start_date, end_date)

        # Obtener el nombre del AppPrice si existe
        app_price_name = None
        try:
            app_price = AppPrice.objects.get(
                app=str(APPS['EXECUTION']), deleted_at__isnull=True)
            app_price_name = app_price.name
        except AppPrice.DoesNotExist:
            pass

        # Calcular costos con 20% extra para ejecuciones manuales
        if price_instance:
            base_price = Decimal(str(price_instance.value))

            # Precio automático = precio base
            automatic_unit_price = base_price
            automatic_cost = automatic_unit_price * automatic_logs

            # Precio manual = 60% del precio base
            manual_unit_price = base_price * Decimal('0.45')
            manual_cost = manual_unit_price * manual_logs

            total_cost = manual_cost + automatic_cost
            price_month = price_instance.month.strftime('%Y-%m-%d')
        else:
            base_price = Decimal('0.00')
            automatic_unit_price = Decimal('0.00')
            manual_unit_price = Decimal('0.00')
            manual_cost = Decimal('0.00')
            automatic_cost = Decimal('0.00')
            total_cost = Decimal('0.00')
            price_month = None

        return Response({
            'app_type': 'EXECUTION',
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'execution_type': execution_type
            },
            'summary': {
                'total_logs': total_logs,
                'manual_logs': manual_logs,
                'automatic_logs': automatic_logs,
                'app_name': APP_NAMES[APPS['EXECUTION']],
                'app_price_name': app_price_name,
                'base_price': str(base_price),
                'automatic_unit_price': str(automatic_unit_price),
                'manual_unit_price': str(manual_unit_price),
                'manual_cost': str(manual_cost),
                'automatic_cost': str(automatic_cost),
                'total_cost': str(total_cost),
                'price_month': price_month,
                'manual_markup': '60%'  # Indicador del markup aplicado
            }
        }, status=status.HTTP_200_OK)
