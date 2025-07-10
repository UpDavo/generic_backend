
PUSH = 1
CANVAS = 2
TRAFFIC = 3
EXECUTION = 4

APP_NAMES = {
    PUSH: "Push",
    CANVAS: "Canvas",
    TRAFFIC: "Traffic",
    EXECUTION: "Execution",
}

APPS = {
    "PUSH": PUSH,
    "CANVAS": CANVAS,
    "TRAFFIC": TRAFFIC,
    "EXECUTION": EXECUTION,
}


STORE_TIMES = []

# Configuración de ventana de tiempo para registros
START_WINDOW = 57
END_WINDOW = 12

# Horarios de operación por día de la semana
# Formato: {día: {'start_hour': hora_inicio, 'end_hour': hora_fin, 'crosses_midnight': boolean}}
# crosses_midnight indica si el horario continúa al día siguiente
OPERATING_HOURS = {
    # Lunes: 12:00-23:00
    1: {'start_hour': 12, 'end_hour': 23, 'crosses_midnight': False},
    # Martes: 09:00-23:00
    2: {'start_hour': 9, 'end_hour': 23, 'crosses_midnight': False},
    # Miércoles: 09:00-24:00 (hasta 00:00 del día siguiente)
    3: {'start_hour': 9, 'end_hour': 0, 'crosses_midnight': True},
    # Jueves: 09:00-01:00 (del día siguiente)
    4: {'start_hour': 9, 'end_hour': 1, 'crosses_midnight': True},
    # Viernes: 08:00-02:00 (del día siguiente)
    5: {'start_hour': 8, 'end_hour': 2, 'crosses_midnight': True},
    # Sábado: 08:00-02:00 (del día siguiente)
    6: {'start_hour': 8, 'end_hour': 2, 'crosses_midnight': True},
    # Domingo: 08:00-22:00
    7: {'start_hour': 8, 'end_hour': 22, 'crosses_midnight': False},
}

# Nombres de días para mensajes
DAY_NAMES = {
    1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves',
    5: 'Viernes', 6: 'Sábado', 7: 'Domingo'
}

# Horarios formateados para mostrar
DAY_SCHEDULES = {
    1: '12:00-23:00',
    2: '09:00-23:00',
    3: '09:00-24:00',
    4: '09:00-01:00',
    5: '08:00-02:00',
    6: '08:00-02:00',
    7: '08:00-22:00'
}
