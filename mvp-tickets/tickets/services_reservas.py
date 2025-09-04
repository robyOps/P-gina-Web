from django.db import transaction
from .models_reservas import Reservation, Resource
from .models import EventLog
from .validators_reservas import enforce_policies, assert_no_overlap


@transaction.atomic
def create_reservation(*, user, resource: Resource, starts_at, ends_at, ticket=None) -> Reservation:
    enforce_policies(user, resource, starts_at, ends_at)
    assert_no_overlap(resource, starts_at, ends_at)
    res = Reservation.objects.create(
        user=user,
        resource=resource,
        starts_at=starts_at,
        ends_at=ends_at,
        ticket=ticket,
    )
    EventLog.objects.create(
        actor=user,
        model="reservation",
        obj_id=res.id,
        action="CREATE",
        message="Reserva creada.",
        resource_id=resource.id,
    )
    return res


@transaction.atomic
def approve_reservation(reservation: Reservation, approver) -> Reservation:
    if reservation.status != Reservation.Status.REQUESTED:
        return reservation
    reservation.status = Reservation.Status.APPROVED
    reservation.save(update_fields=["status", "updated_at"])
    EventLog.objects.create(
        actor=approver,
        model="reservation",
        obj_id=reservation.id,
        action="APPROVE",
        message="Reserva aprobada.",
        resource_id=reservation.resource_id,
    )
    return reservation


@transaction.atomic
def cancel_reservation(reservation: Reservation, actor) -> Reservation:
    if reservation.status == Reservation.Status.CANCELLED:
        return reservation
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    EventLog.objects.create(
        actor=actor,
        model="reservation",
        obj_id=reservation.id,
        action="CANCEL",
        message="Reserva cancelada.",
        resource_id=reservation.resource_id,
    )
    return reservation
