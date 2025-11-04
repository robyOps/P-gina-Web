"""
===============================================================================
Propósito:
    Definir etiquetas y agrupaciones de permisos para construir interfaces de
    administración más comprensibles.
API pública:
    ``PERMISSION_LABELS``, ``PERMISSION_GROUPS`` y helpers ``group_permissions``
    usados en formularios y vistas.
Flujo de datos:
    Codename de permiso → etiqueta amigable/agrupación → renderizado en UI o
    inicialización de roles.
Dependencias:
    ``accounts.roles`` para obtener roles predefinidos y módulos ``django.contrib.auth``.
Decisiones:
    Se almacenan etiquetas en español y se agrupan permisos para mantener
    coherencia en la experiencia de usuario.
TODOs:
    TODO:PREGUNTA Revisar si se requieren permisos adicionales para reportes
    avanzados o integraciones externas.
===============================================================================
"""

from dataclasses import dataclass
from typing import Iterable

from accounts.roles import ROLE_ADMIN, ROLE_TECH


PERMISSION_LABELS = {
    # --- Tickets (ciclo de vida) ---
    "add_ticket": "Puede crear ticket",
    "change_ticket": "Puede cambiar ticket",
    "delete_ticket": "Puede eliminar ticket",
    "view_ticket": "Puede ver ticket",
    "assign_ticket": "Puede asignar ticket",
    "transition_ticket": "Puede cambiar estado de ticket",
    "view_all_tickets": "Puede ver todos los tickets",
    "set_ticket_category": "Puede elegir categoría al crear ticket",
    "set_ticket_priority": "Puede elegir prioridad al crear ticket",
    "set_ticket_subcategory": "Puede elegir subcategoría al crear ticket",
    "set_ticket_area": "Puede elegir área al crear ticket",
    "set_ticket_assignee": "Puede asignar técnico al crear ticket",
    # --- Colaboración sobre tickets ---
    "comment_internal": "Puede comentar internamente",
    "add_ticketcomment": "Puede agregar comentario",
    "change_ticketcomment": "Puede cambiar comentario",
    "delete_ticketcomment": "Puede eliminar comentario",
    "view_ticketcomment": "Puede ver comentario",
    "add_ticketattachment": "Puede agregar adjunto",
    "change_ticketattachment": "Puede cambiar adjunto",
    "delete_ticketattachment": "Puede eliminar adjunto",
    "view_ticketattachment": "Puede ver adjunto",
    # --- Catálogo y clasificaciones ---
    "add_category": "Puede agregar categoría",
    "change_category": "Puede cambiar categoría",
    "delete_category": "Puede eliminar categoría",
    "view_category": "Puede ver categoría",
    "add_priority": "Puede agregar prioridad",
    "change_priority": "Puede cambiar prioridad",
    "delete_priority": "Puede eliminar prioridad",
    "view_priority": "Puede ver prioridad",
    "add_area": "Puede agregar área",
    "change_area": "Puede cambiar área",
    "delete_area": "Puede eliminar área",
    "view_area": "Puede ver área",
    # --- Automatizaciones y base de conocimientos ---
    "add_autoassignrule": "Puede crear regla de auto-asignación",
    "change_autoassignrule": "Puede cambiar regla de auto-asignación",
    "delete_autoassignrule": "Puede eliminar regla de auto-asignación",
    "view_autoassignrule": "Puede ver reglas de auto-asignación",
    "add_faq": "Puede crear pregunta frecuente",
    "change_faq": "Puede cambiar pregunta frecuente",
    "delete_faq": "Puede eliminar pregunta frecuente",
    "view_faq": "Puede ver preguntas frecuentes",
    "view_reports": "Puede ver reportes",
    "manage_reports": "Puede administrar reportes",
    # --- Usuarios y roles (auth) ---
    "add_user": "Puede agregar usuario",
    "change_user": "Puede cambiar usuario",
    "delete_user": "Puede eliminar usuario",
    "view_user": "Puede ver usuario",
    "add_group": "Puede agregar rol",
    "change_group": "Puede cambiar rol",
    "delete_group": "Puede eliminar rol",
    "view_group": "Puede ver rol",
    "add_permission": "Puede agregar permiso",
    "change_permission": "Puede cambiar permiso",
    "delete_permission": "Puede eliminar permiso",
    "view_permission": "Puede ver permiso",
    # --- Permisos del sistema y administración ---
    "add_logentry": "Puede agregar registro de admin",
    "change_logentry": "Puede cambiar registro de admin",
    "delete_logentry": "Puede eliminar registro de admin",
    "view_logentry": "Puede ver registro de admin",
    "add_eventlog": "Puede agregar registro global",
    "change_eventlog": "Puede cambiar registro global",
    "delete_eventlog": "Puede eliminar registro global",
    "view_eventlog": "Puede ver registro global",
    "add_contenttype": "Puede agregar tipo de contenido",
    "change_contenttype": "Puede cambiar tipo de contenido",
    "delete_contenttype": "Puede eliminar tipo de contenido",
    "view_contenttype": "Puede ver tipo de contenido",
    "add_session": "Puede agregar sesión",
    "change_session": "Puede cambiar sesión",
    "delete_session": "Puede eliminar sesión",
    "view_session": "Puede ver sesión",
}


@dataclass(frozen=True)
class PermissionGroup:
    """Representa un conjunto de permisos relacionados para la UI."""

    key: str
    label: str
    description: str
    codenames: tuple[str, ...]


PERMISSION_GROUPS: tuple[PermissionGroup, ...] = (
    PermissionGroup(
        key="tickets_core",
        label="Operación de tickets",
        description="Crear, actualizar y gestionar el ciclo de vida de los tickets.",
        codenames=(
            "view_ticket",
            "add_ticket",
            "change_ticket",
            "delete_ticket",
            "assign_ticket",
            "transition_ticket",
            "view_all_tickets",
            "set_ticket_category",
            "set_ticket_priority",
            "set_ticket_subcategory",
            "set_ticket_area",
            "set_ticket_assignee",
        ),
    ),
    PermissionGroup(
        key="tickets_collab",
        label="Colaboración y conversación",
        description="Comentar, adjuntar archivos y trabajar internamente en los tickets.",
        codenames=(
            "comment_internal",
            "add_ticketcomment",
            "change_ticketcomment",
            "delete_ticketcomment",
            "view_ticketcomment",
            "add_ticketattachment",
            "change_ticketattachment",
            "delete_ticketattachment",
            "view_ticketattachment",
        ),
    ),
    PermissionGroup(
        key="catalogs",
        label="Catálogos y clasificación",
        description="Mantener categorías, prioridades y áreas disponibles para los tickets.",
        codenames=(
            "view_category",
            "add_category",
            "change_category",
            "delete_category",
            "view_priority",
            "add_priority",
            "change_priority",
            "delete_priority",
            "view_area",
            "add_area",
            "change_area",
            "delete_area",
        ),
    ),
    PermissionGroup(
        key="knowledge",
        label="Automatización y base de conocimiento",
        description="Gestionar reglas de auto-asignación y preguntas frecuentes.",
        codenames=(
            "view_autoassignrule",
            "add_autoassignrule",
            "change_autoassignrule",
            "delete_autoassignrule",
            "view_faq",
            "add_faq",
            "change_faq",
            "delete_faq",
        ),
    ),
    PermissionGroup(
        key="analytics",
        label="Reportes y métricas",
        description="Consultar paneles y ejecutar herramientas analíticas.",
        codenames=(
            "view_reports",
            "manage_reports",
        ),
    ),
    PermissionGroup(
        key="accounts",
        label="Usuarios y roles",
        description="Administrar cuentas, grupos y permisos de la plataforma.",
        codenames=(
            "view_user",
            "add_user",
            "change_user",
            "delete_user",
            "view_group",
            "add_group",
            "change_group",
            "delete_group",
            "view_permission",
            "add_permission",
            "change_permission",
            "delete_permission",
        ),
    ),
    PermissionGroup(
        key="system",
        label="Registros del sistema",
        description="Acceso a logs, sesiones y configuraciones técnicas.",
        codenames=(
            "view_logentry",
            "add_logentry",
            "change_logentry",
            "delete_logentry",
            "view_eventlog",
            "add_eventlog",
            "change_eventlog",
            "delete_eventlog",
            "view_contenttype",
            "add_contenttype",
            "change_contenttype",
            "delete_contenttype",
            "view_session",
            "add_session",
            "change_session",
            "delete_session",
        ),
    ),
)


def group_permissions(queryset: Iterable) -> list[dict]:
    """Convierte un queryset de Permission a bloques agrupados para la UI."""

    by_code = {perm.codename: perm for perm in queryset}
    grouped: dict[str, dict] = {}

    # Construimos grupos conocidos primero para mantener el orden predefinido
    for group in PERMISSION_GROUPS:
        items = []
        for code in group.codenames:
            perm = by_code.get(code)
            if not perm:
                continue
            items.append(
                {
                    "id": str(perm.id),
                    "codename": perm.codename,
                    "label": PERMISSION_LABELS.get(perm.codename, perm.name),
                }
            )
        if items:
            grouped[group.key] = {
                "key": group.key,
                "label": group.label,
                "description": group.description,
                "items": items,
            }

    # Permisos restantes que no quedaron asociados a un grupo conocido
    remaining = []
    for perm in queryset:
        if any(perm.codename in grp.codenames for grp in PERMISSION_GROUPS):
            continue
        remaining.append(
            {
                "id": str(perm.id),
                "codename": perm.codename,
                "label": PERMISSION_LABELS.get(perm.codename, perm.name),
            }
        )

    if remaining:
        grouped["other"] = {
            "key": "other",
            "label": "Otros permisos",
            "description": "Códigos adicionales disponibles en el sistema.",
            "items": remaining,
        }

    # Devuelve la lista en el orden definido por PERMISSION_GROUPS más el bloque "Otros"
    ordered_keys = [grp.key for grp in PERMISSION_GROUPS]
    if "other" in grouped:
        ordered_keys.append("other")
    return [grouped[key] for key in ordered_keys if key in grouped]


PERMISSION_TEMPLATES = {
    ROLE_ADMIN: {
        "label": "Administrador",
        "description": "Acceso completo a la configuración, catálogos y tickets.",
        "codenames": list(PERMISSION_LABELS.keys()),
    },
    ROLE_TECH: {
        "label": "Técnico",
        "description": "Enfoque operativo: trabajar tickets, comentar y gestionar adjuntos.",
        "codenames": [
            "view_ticket",
            "change_ticket",
            "transition_ticket",
            "view_all_tickets",
            "comment_internal",
            "add_ticketcomment",
            "change_ticketcomment",
            "view_ticketcomment",
            "add_ticketattachment",
            "view_ticketattachment",
            "view_faq",
            "change_faq",
            "view_reports",
        ],
    },
}
