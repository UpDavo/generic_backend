from django.core.management.base import BaseCommand
from authentication.models import Role, Permission, HttpMethod


class Command(BaseCommand):
    help = 'Crea roles con sus respectivos permisos'

    def handle(self, *args, **options):
        # Definir los permisos
        permissions_data = [
            {"name": "Enviar Push", "path": "/push/send"},
            {"name": "Crear Push", "path": "/push"},
            {"name": "Ver Logs", "path": "/push/logs"},
            {"name": "Dashboard", "path": "/"},
            {"name": "Usuarios", "path": "/users"},
        ]

        # Crear o obtener los permisos
        permissions = {}
        for perm_data in permissions_data:
            permission, created = Permission.objects.get_or_create(
                name=perm_data["name"],
                path=perm_data["path"]
            )
            permissions[perm_data["name"]] = permission
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Permiso creado: {permission.name}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Permiso existente: {permission.name}'))

        # Definir los roles
        roles_data = [
            {
                "name": "Admin",
                "description": "Administrador",
                "permissions": [
                    "Enviar Push",
                    "Crear Push",
                    "Ver Logs",
                    "Dashboard",
                    "Usuarios"
                ],
                "is_admin": True
            },
            {
                "name": "Store",
                "description": "Rol de Push",
                "permissions": [
                    "Enviar Push"
                ],
                "is_admin": False
            },
            {
                "name": "Data",
                "description": "Rol de Datos",
                "permissions": [
                    "Enviar Push",
                    "Crear Push",
                    "Ver Logs",
                    "Dashboard"
                ],
                "is_admin": False
            },
            {
                "name": "Customer Service",
                "description": "Soporte al Cliente",
                "permissions": [
                    "Enviar Push",
                    "Ver Logs"
                ],
                "is_admin": False
            }
        ]

        # Crear los roles
        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_data["name"],
                defaults={
                    "description": role_data["description"],
                    "is_admin": role_data["is_admin"]
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Rol creado: {role.name}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Rol existente: {role.name}'))

            # Asignar permisos al rol
            role.permissions.clear()
            for perm_name in role_data["permissions"]:
                role.permissions.add(permissions[perm_name])
            role.save()
            self.stdout.write(self.style.SUCCESS(
                f'Permisos asignados al rol {role.name}'))
