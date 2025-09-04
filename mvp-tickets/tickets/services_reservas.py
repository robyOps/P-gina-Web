from django.db import transaction
from .models_reservas import Reservation, Resource
from .validators_reservas import enforce_policies, assert_no_overlap


@transaction.atomic
def create_reservation(*, user, resource: Resource, starts_at, ends_at) -> Reservation:
    enforce_policies(user, resource, starts_at, ends_at)
    assert_no_overlap(resource, starts_at, ends_at)
    return Reservation.objects.create(
        user=user,
        resource=resource,
        starts_at=starts_at,
        ends_at=ends_at,
    )


@transaction.atomic
def approve_reservation(reservation: Reservation, approver) -> Reservation:
    if reservation.status != Reservation.Status.REQUESTED:
        return reservation
    reservation.status = Reservation.Status.APPROVED
    reservation.save(update_fields=["status", "updated_at"])
    return reservation


@transaction.atomic
def cancel_reservation(reservation: Reservation, actor) -> Reservation:
    if reservation.status == Reservation.Status.CANCELLED:
        return reservation
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    return reservation
