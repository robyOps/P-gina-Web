from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import APIException
from .models_reservas import Reservation, Policy, Resource


class PolicyError(APIException):
    status_code = 400
    default_detail = 'Violación de política de reserva.'


class ConflictError(APIException):
    status_code = 409
    default_detail = 'Existe un conflicto/solapamiento con otra reserva.'


def enforce_policies(user, resource: Resource, start, end):
    if end <= start:
        raise PolicyError("La fecha/hora de término debe ser posterior al inicio.")

    duration = end - start
    hours = duration.total_seconds() / 3600

    policy = Policy.objects.first()
    if policy:
        if hours > policy.max_hours:
            raise PolicyError(f"La reserva excede el máximo de {policy.max_hours} horas.")
        if start < timezone.now() + timedelta(hours=policy.min_notice_hours):
            raise PolicyError(
                f"Se requiere un aviso mínimo de {policy.min_notice_hours} horas."
            )
        if not policy.allow_weekends and start.weekday() >= 5:
            raise PolicyError("No se permiten reservas en fin de semana.")

        if policy.buffer_minutes:
            buffer = timedelta(minutes=policy.buffer_minutes)
            conflict = Reservation.objects.filter(
                resource=resource,
                status__in=[Reservation.Status.REQUESTED, Reservation.Status.APPROVED],
            ).filter(
                Q(starts_at__lt=end + buffer) & Q(ends_at__gt=start - buffer)
            ).exists()
            if conflict:
                raise ConflictError("Existe una reserva cercana que viola el buffer mínimo.")


def assert_no_overlap(resource: Resource, start, end):
    # Solapamiento si: NOT (E <= starts_at_existente OR S >= ends_at_existente)
    conflicts = Reservation.objects.filter(
        resource=resource,
        status__in=[Reservation.Status.REQUESTED, Reservation.Status.APPROVED],
    ).filter(
        ~Q(ends_at__lte=start) & ~Q(starts_at__gte=end)
    ).exists()
    if conflicts:
        raise ConflictError("Existe una reserva solapada para este recurso.")
