from django.urls import path
from tada.views import *

urlpatterns = [
    # Push
    path('send/push/', SendMessage.as_view(), name='send-push'),
    path('send/canvas/', SendPushCanvas.as_view(), name='send-canvas'),

    # Messages
    path('notifications/', NotificationMessageListCreateView.as_view(),
         name='notification-list-create'),
    path('notifications/<int:pk>/',
         NotificationMessageRetrieveUpdateDestroyView.as_view(), name='notification-detail'),

    # messages notifications
    path('notification-logs/', NotificationLogListView.as_view(),
         name='notification-log-list'),
    path('notification-logs/report/', NotificationLogRangeView.as_view(),
         name='notification-log-list'),
    path('notification-logs/report/download', NotificationLogDownloadView.as_view(),
         name='notification-log-download'),

    # canvas
    path('canvas/messages/', CanvasMessageListCreateView.as_view(),
         name='canvas-message-list-create'),
    path('canvas/messages/<int:pk>/',
         CanvasMessageRetrieveUpdateDestroyView.as_view(), name='canvas-message-detail'),

    # canvas notifications
    path('canvas-logs/', CanvasLogListView.as_view(),
         name='canvas-log-list'),
    path('canvas-logs/report/', CanvasLogRangeView.as_view(),
         name='canvas-log-list'),
    path('canvas-logs/report/download', CanvasLogDownloadView.as_view(),
         name='canvas-log-download'),

    # prices
    path('prices/', PriceListCreateView.as_view(),
         name='price-list'),
    path('prices/last/', PriceLastView.as_view(),
         name='price-last'),

    # Pocs
    path('pocs/report/', PocAPI.as_view(),
         name='poc-report'),

    # app prices (CRUD básico - usa Price existente por ID)
    path('app-prices/', AppPriceListCreateView.as_view(),
         name='app-price-list-create'),
    path('app-prices/<int:pk>/',
         AppPriceRetrieveUpdateDestroyView.as_view(), name='app-price-detail'),
    path('app-prices/by-name/<str:name>/',
         AppPriceByNameView.as_view(), name='app-price-by-name'),

    # app prices con Price anidado (permite crear/editar Price junto con AppPrice)
    path('app-prices-with-price/', AppPriceWithPriceListCreateView.as_view(),
         name='app-price-with-price-list-create'),
    path('app-prices-with-price/<int:pk>/',
         AppPriceWithPriceRetrieveUpdateDestroyView.as_view(), name='app-price-with-price-detail'),

    # Estadísticas de logs por usuario con precios
    path('notification-logs/stats/', NotificationLogsStatsView.as_view(),
         name='notification-logs-stats'),
    path('canvas-logs/stats/', CanvasLogsStatsView.as_view(),
         name='canvas-logs-stats'),
    path('traffic-logs/stats/', TrafficLogsStatsView.as_view(),
         name='traffic-logs-stats'),
    path('execution-logs/stats/', ExecutionLogsStatsView.as_view(),
         name='execution-logs-stats'),
    path('webhook-logs/stats/', WebhookLogsStatsView.as_view(),
         name='webhook-logs-stats'),
    path('logs/combined-stats/', CombinedLogsStatsView.as_view(),
         name='combined-logs-stats'),
    
    #dinero consumido al procesar el reporte de ventas
    path('sales-report-logs/stats/', SalesReportLogsStatsView.as_view(),
         name='sales-report-logs-stats'),
    #Dinero consumido al ver los records
    path('sales-record/history/stats/', SalesRecordHistoryStatsView.as_view(),
         name='sales-record-history-stats'),

    # Historial de precios por app
    path('prices/history/<str:app>/', PriceHistoryByAppView.as_view(),
         name='price-history-by-app'),
    path('prices/latest-all/', AllAppsLatestPricesView.as_view(),
         name='latest-prices-all-apps'),
    path('prices/comparison/<str:app>/',
         PriceComparisonView.as_view(), name='price-comparison'),

    # Traffic Events (CRUD completo)
    path('traffic-events/', TrafficEventListCreateView.as_view(),
         name='traffic-event-list-create'),
    path('traffic-events/<int:pk>/',
         TrafficEventRetrieveUpdateDestroyView.as_view(), name='traffic-event-detail'),

    # Traffic Logs (solo lectura)
    path('traffic-logs/', TrafficLogListView.as_view(),
         name='traffic-log-list'),

    # Execution Logs (CRUD completo)
    path('execution-logs/', ExecutionLogListCreateView.as_view(),
         name='execution-log-list-create'),
    path('execution-logs/<int:pk>/',
         ExecutionLogRetrieveUpdateDestroyView.as_view(), name='execution-log-detail'),
    path('execution-logs/list/', ExecutionLogListView.as_view(),
         name='execution-log-list'),

    # Daily Meta (CRUD completo)
    path('daily-meta/', DailyMetaListCreateView.as_view(),
         name='daily-meta-list-create'),
    path('daily-meta/<int:pk>/',
         DailyMetaRetrieveUpdateDestroyView.as_view(), name='daily-meta-detail'),
    path('daily-meta/bulk-create/', DailyMetaBulkCreateView.as_view(),
         name='daily-meta-bulk-create'),
    path('daily-meta/bulk-create-excel/', DailyMetaBulkCreateFromExcelView.as_view(),
         name='daily-meta-bulk-create-excel'),

    # Hectolitres Daily Meta (CRUD completo)
    path('hectolitres-daily-meta/', HectolitresDailyMetaListCreateView.as_view(),
         name='hectolitres-daily-meta-list-create'),
    path('hectolitres-daily-meta/<int:pk>/',
         HectolitresDailyMetaRetrieveUpdateDestroyView.as_view(), name='hectolitres-daily-meta-detail'),
    path('hectolitres-daily-meta/bulk-create/', HectolitresDailyMetaBulkCreateView.as_view(),
         name='hectolitres-daily-meta-bulk-create'),
    path('hectolitres-daily-meta/bulk-create-excel/', HectolitresDailyMetaBulkCreateFromExcelView.as_view(),
         name='hectolitres-daily-meta-bulk-create-excel'),

    # Reporte hectolitros
    path('hectolitres-daily-meta/weekly-report/', HectolitresWeeklyReportView.as_view(),
         name='hectolitres-weekly-report'),
    path('hectolitres-daily-meta/weekly-report/download/', HectolitresWeeklyReportDownloadView.as_view(),
         name='hectolitres-weekly-report-download'),
    
    # Reporte TOP 5 SKUs por región
    path('top-skus-region/weekly-report/', TopSkusByRegionWeeklyReportView.as_view(),
         name='top-skus-region-weekly-report'),
    path('top-skus-region/weekly-report/download/', TopSkusByRegionWeeklyReportDownloadView.as_view(),
         name='top-skus-region-weekly-report-download'),
    
    # Comparativa anual de hectolitros
    path('hectolitres/yearly-comparison/', HectolitresYearlyComparisonReportView.as_view(),
         name='hectolitres-yearly-comparison'),
    path('hectolitres/yearly-comparison/download/', HectolitresYearlyComparisonReportDownloadView.as_view(),
         name='hectolitres-yearly-comparison-download'),
    
    # Datos manuales para comparativa anual
    path('manual-yearly-data/', ManualYearlyDataListCreateView.as_view(),
         name='manual-yearly-data-list-create'),
    path('manual-yearly-data/<int:pk>/', ManualYearlyDataDetailView.as_view(),
         name='manual-yearly-data-detail'),

    # Sales Report Processor
    path('sales-report/process/', SalesReportProcessorView.as_view(),
         name='sales-report-process'),
    path('sales-report-logs/', SalesReportLogsListView.as_view(),
         name='sales-report-logs-list'),
    
    # Sales Report Processor OPTIMIZADO (bajo consumo de RAM)
    path('sales-report/process-optimized/', OptimizedSalesReportProcessorView.as_view(),
         name='sales-report-process-optimized'),
    
    
    #Descargar y listar historico de procesamientos
    path('sales-record/history/', SalesRecordHistoryListView.as_view(),
         name='sales-record-history-list'),
    path('sales-record/history/download/', SalesRecordHistoryDownloadView.as_view(),
         name='sales-record-history-download'),
    
    # Último upload de ventas
    path('sales-upload/last/', SalesUploadLogView.as_view(),
         name='sales-upload-last'),
    
    # Eliminar registros de ventas por rango de fechas
    path('sales-record/delete-by-date/', SalesRecordDeleteByDateRangeView.as_view(),
         name='sales-record-delete-by-date'),
    
    # Eliminar registros OPTIMIZADO (SQL directo)
    path('sales-record/delete-by-date-optimized/', OptimizedSalesRecordDeleteByDateRangeView.as_view(),
         name='sales-record-delete-by-date-optimized'),
    
    # TRUNCATE completo de la tabla (PELIGROSO - usar con cuidado)
    path('sales-record/truncate/', OptimizedBulkTruncateView.as_view(),
         name='sales-record-truncate'),
    
    # Enviar reporte de ventas por WhatsApp
    path('sales-report/send-whatsapp/', SalesReportWhatsAppView.as_view(),
         name='sales-report-send-whatsapp'),
    

    # VentasProductosCompra (CRUD completo)
    path('ventas-productos-compra/', VentasProductosCompraListCreateView.as_view(),
         name='ventas-productos-compra-list-create'),
    path('ventas-productos-compra/search/', VentasProductosCompraSearchView.as_view(),
         name='ventas-productos-compra-search'),
    path('ventas-productos-compra/categories/', VentasProductosCompraCategoriesView.as_view(),
         name='ventas-productos-compra-categories'),
    path('ventas-productos-compra/brands/', VentasProductosCompraBrandsView.as_view(),
         name='ventas-productos-compra-brands'),
    path('ventas-productos-compra/<int:pk>/',
         VentasProductosCompraRetrieveUpdateDestroyView.as_view(), name='ventas-productos-compra-detail'),
    path('ventas-productos-compra/bulk-create-excel/', VentasProductosCompraBulkCreateFromExcelView.as_view(),
         name='ventas-productos-compra-bulk-create-excel'),
    path('ventas-productos-compra/download-template/', VentasProductosCompraDownloadTemplateView.as_view(),
         name='ventas-productos-compra-download-template'),
    path('ventas-productos-compra/download-all/', VentasProductosCompraDownloadAllView.as_view(),
         name='ventas-productos-compra-download-all'),

    # VentasProductosApp (CRUD completo)
    path('ventas-productos-app/', VentasProductosAppListCreateView.as_view(),
         name='ventas-productos-app-list-create'),
    path('ventas-productos-app/search/', VentasProductosAppPrincipalSearchView.as_view(),
         name='ventas-productos-app-principal-search'),
    path('ventas-productos-app/<int:pk>/',
         VentasProductosAppRetrieveUpdateDestroyView.as_view(), name='ventas-productos-app-detail'),
    path('ventas-productos-app/bulk-create-excel/', VentasProductosAppBulkCreateFromExcelView.as_view(),
         name='ventas-productos-app-bulk-create-excel'),
    path('ventas-productos-app/download-template/', VentasProductosAppDownloadTemplateView.as_view(),
         name='ventas-productos-app-download-template'),
    path('ventas-productos-app/download-all/', VentasProductosAppDownloadAllView.as_view(),
         name='ventas-productos-app-download-all'),

    # NegativosJustificacion (CRUD completo)
    path('negativos-justificacion/', NegativosJustificacionListCreateView.as_view(),
         name='negativos-justificacion-list-create'),
    path('negativos-justificacion/search/', NegativosJustificacionSearchView.as_view(),
         name='negativos-justificacion-search'),
    path('negativos-justificacion/<int:pk>/',
         NegativosJustificacionRetrieveUpdateDestroyView.as_view(), name='negativos-justificacion-detail'),
    path('negativos-justificacion/bulk-create-excel/', NegativosJustificacionBulkCreateFromExcelView.as_view(),
         name='negativos-justificacion-bulk-create-excel'),
    path('negativos-justificacion/download-template/', NegativosJustificacionDownloadTemplateView.as_view(),
         name='negativos-justificacion-download-template'),
    path('negativos-justificacion/download-all/', NegativosJustificacionDownloadAllView.as_view(),
         name='negativos-justificacion-download-all'),

    # POC (CRUD completo)
    path('pocs/', POCListCreateView.as_view(),
         name='poc-list-create'),
    path('pocs/<int:pk>/',
         POCRetrieveUpdateDestroyView.as_view(), name='poc-detail'),
    path('pocs/bulk-create-excel/', POCBulkCreateFromExcelView.as_view(),
         name='poc-bulk-create-excel'),
    path('pocs/download-template/', POCDownloadTemplateView.as_view(),
         name='poc-download-template'),

    # Reports API
    path('reports/datetime-variation/', DatetimeVariationReportView.as_view(),
         name='datetime-variation-report'),
    path('reports/send-email/', ReportEmailView.as_view(),
         name='report-send-email'),
    path('reports/fetch-data/', ReportFetchView.as_view(),
         name='report-fetch-data'),

    # Webhook (receiver and stats)
    path('webhook/cancelled/', WebhookReceiverCancelledView.as_view(),
         name='webhook-cancelled'),
    path('webhook/cancelled/<int:pk>/update/', WebhookCancelledUpdateView.as_view(),
         name='webhook-cancelled-update'),
    path('webhook/cancelled/download/', WebhookCancelledDownloadView.as_view(),
         name='webhook-cancelled-download'),

]
