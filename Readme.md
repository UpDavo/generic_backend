# Django Generic Backend

Este es un **proyecto Django genérico** diseñado para servir como base para cualquier proyecto con prospecto de crecimiento. Incluye una configuración robusta para **autenticación (auth), APIs RESTful**, y una estructura modular escalable.

---

## Características principales

- ✅ **Autenticación con JWT** (JSON Web Tokens) usando `djangorestframework-simplejwt`.
- ✅ **Estructura modular y escalable** con separación de lógica en servicios, modelos y utilidades.
- ✅ **Integración con MySQL** como base de datos.
- ✅ **CORS habilitado** para permitir la conexión con aplicaciones frontend (React, Next.js, etc.).
- ✅ **Configuración segura** mediante variables de entorno.
- ✅ **Manejo de sesiones y permisos personalizados.**
- ✅ **Documentación con DRF Browsable API.**

---

## Requisitos previos

Antes de instalar, asegúrate de tener instalados los siguientes requisitos:

- [Python 3.8+](https://www.python.org/downloads/)
- [MySQL](https://dev.mysql.com/downloads/)
- [pip](https://pip.pypa.io/en/stable/)
- [Virtualenv (opcional)](https://virtualenv.pypa.io/en/latest/)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/tu-repositorio.git
cd tu-repositorio
```

### 2. Crear un entorno virtual

```bash
python -m venv env
source env/bin/activate  # Para Linux/MacOS
env\Scripts\activate     # Para Windows
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto y agrega la configuración:

```plaintext
SECRET_KEY=tu-clave-secreta
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=mi_base_de_datos
DB_USER=mi_usuario
DB_PASSWORD=mi_contraseña
DB_HOST=localhost
DB_PORT=3306
```

### 5. Aplicar migraciones de base de datos

```bash
python manage.py makemigrations\python manage.py migrate
```

### 6. Crear un superusuario

```bash
python manage.py createsuperuser
```

### 7. Ejecutar el servidor

```bash
python manage.py runserver
```

La API estará disponible en `http://127.0.0.1:8000/`

---

## Uso

- Accede al panel de administración en `http://127.0.0.1:8000/admin`.
- Consulta la API usando herramientas como Postman o cURL.
- Frontend compatible con React, Next.js u otro framework moderno.

---

## Estructura del proyecto

```plaintext
myproject/
│-- manage.py
│-- myproject/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│-- auth/
│   ├── models/
│   ├── services/
│   ├── views/
│   ├── urls.py
│-- core/
│-- requirements.txt
│-- .env
│-- README.md
```

---

## API Endpoints

| Método | Endpoint        | Descripción                |
| ------ | --------------- | -------------------------- |
| POST   | /auth/login/    | Iniciar sesión de usuario  |
| POST   | /auth/register/ | Registrar un nuevo usuario |
| POST   | /auth/logout/   | Cerrar sesión de usuario   |

---

## Tecnologías utilizadas

- **Django** - Framework principal
- **Django REST Framework** - Construcción de APIs RESTful
- **MySQL** - Base de datos
- **SimpleJWT** - Autenticación basada en tokens JWT
- **CORS Headers** - Permitir conexiones del frontend

---

## Contribuciones

Si deseas contribuir, por favor sigue los siguientes pasos:

1. Haz un fork del repositorio.
2. Crea una rama con tu nueva funcionalidad.
3. Realiza un pull request explicando los cambios.

---

## Licencia

Este proyecto está licenciado bajo la MIT License - consulta el archivo [LICENSE](LICENSE) para más detalles.

---

## Autor

Desarrollado por **[updavo](https://github.com/updavo)**