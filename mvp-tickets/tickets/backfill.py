"""Utilities for populating ticket subcategories retroactively."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Iterable

from django.db import transaction
from django.db.models import QuerySet

from catalog.models import Subcategory

from .models import Ticket

logger = logging.getLogger(__name__)


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


@dataclass(slots=True)
class SubcategoryBackfillReport:
    total: int
    completed: int
    pending: int
    deterministic_matches: int = 0
    heuristic_matches: int = 0
    touched_ids: list[int] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        if self.total <= 0:
            return 0.0
        return round((self.completed / self.total) * 100, 2)


def _build_label_index(subcategories: Iterable[Subcategory]) -> dict[str, Subcategory]:
    index: dict[str, Subcategory] = {}
    for subcategory in subcategories:
        key = _normalize(subcategory.name)
        if key:
            index[key] = subcategory
    return index


def _match_by_labels(ticket: Ticket, label_index: dict[str, Subcategory]) -> Subcategory | None:
    labels = ticket.labels.all().values_list("name", flat=True)
    for label in labels:
        normalized = _normalize(label)
        candidate = label_index.get(normalized)
        if candidate and candidate.category_id == ticket.category_id:
            return candidate
    return None


def _match_by_text(ticket: Ticket, subcategories: Iterable[Subcategory]) -> Subcategory | None:
    searchable = _normalize(f"{ticket.title} {ticket.description}")
    if not searchable:
        return None

    for subcategory in subcategories:
        if subcategory.category_id != ticket.category_id:
            continue
        needle = _normalize(subcategory.name)
        if not needle or len(needle) < 3:
            continue
        if needle in searchable:
            return subcategory
    return None


def run_subcategory_backfill(*, queryset: QuerySet[Ticket] | None = None, dry_run: bool = False) -> SubcategoryBackfillReport:
    """Apply a three phase backfill to populate ticket subcategories."""

    queryset = queryset or Ticket.objects.all()
    total = queryset.count()
    completed_initial = queryset.exclude(subcategory__isnull=True).count()

    pending = list(queryset.filter(subcategory__isnull=True))
    if not pending:
        return SubcategoryBackfillReport(
            total=total,
            completed=completed_initial,
            pending=0,
        )

    subcategories = list(Subcategory.objects.filter(is_active=True).select_related("category"))
    label_index = _build_label_index(subcategories)

    deterministic = 0
    heuristic = 0
    touched: list[int] = []

    with transaction.atomic():
        for ticket in pending:
            chosen: Subcategory | None = _match_by_labels(ticket, label_index)
            reason = "labels" if chosen else ""

            if not chosen:
                chosen = _match_by_text(ticket, subcategories)
                reason = "text" if chosen else ""

            if not chosen:
                continue

            if reason == "labels":
                deterministic += 1
            elif reason == "text":
                heuristic += 1

            if not dry_run:
                Ticket.objects.filter(pk=ticket.pk).update(subcategory=chosen)
            touched.append(ticket.pk)

        if dry_run:
            transaction.set_rollback(True)

    completed = queryset.exclude(subcategory__isnull=True).count()
    pending_after = total - completed

    report = SubcategoryBackfillReport(
        total=total,
        completed=completed,
        pending=pending_after,
        deterministic_matches=deterministic,
        heuristic_matches=heuristic,
        touched_ids=touched,
    )

    logger.info(
        "Subcategory backfill executed",
        extra={
            "total": report.total,
            "completed": report.completed,
            "pending": report.pending,
            "deterministic": deterministic,
            "heuristic": heuristic,
            "dry_run": dry_run,
        },
    )
    return report
