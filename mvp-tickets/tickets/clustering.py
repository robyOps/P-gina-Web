"""Utilidades para agrupar tickets por similitud textual."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from django.db import transaction

try:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError as exc:  # pragma: no cover - dependencia opcional en runtime
    raise ImportError(
        "scikit-learn es requerido para agrupar tickets. Instálalo o añade la dependencia."
    ) from exc

from .models import Ticket

logger = logging.getLogger(__name__)

# Lista sencilla de stopwords en español + inglés para reducir ruido
STOPWORDS = {
    "de",
    "la",
    "que",
    "el",
    "en",
    "y",
    "a",
    "los",
    "del",
    "se",
    "las",
    "por",
    "un",
    "para",
    "con",
    "no",
    "una",
    "su",
    "al",
    "lo",
    "como",
    "más",
    "pero",
    "sus",
    "le",
    "ya",
    "o",
    "este",
    "sí",
    "porque",
    "esta",
    "entre",
    "cuando",
    "muy",
    "sin",
    "sobre",
    "también",
    "me",
    "hasta",
    "hay",
    "donde",
    "quien",
    "ser",
    "tiene",
    "todo",
    "han",
    "uno",
    "son",
    "dos",
    "era",
    "ya",
    "you",
    "the",
    "is",
    "to",
    "and",
    "of",
    "in",
    "for",
    "on",
    "with",
    "this",
    "that",
}


@dataclass(slots=True)
class ClusterSummary:
    """Resumen del proceso de clusterización."""

    total_tickets: int
    requested_clusters: int
    effective_clusters: int
    assignments: dict[int, int]


def _normalize_text(text: str | None) -> str:
    """Normaliza texto (lowercase + remueve caracteres no alfanuméricos básicos)."""

    if not text:
        return ""
    lowered = text.lower()
    # Preserva caracteres acentuados y ñ/ü
    cleaned = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", lowered)
    compact = re.sub(r"\s+", " ", cleaned).strip()
    return compact


def _vectorize(texts: Sequence[str]):
    vectorizer = TfidfVectorizer(stop_words=list(STOPWORDS), min_df=1)
    matrix = vectorizer.fit_transform(texts)
    return matrix


def train_ticket_clusters(*, num_clusters: int) -> ClusterSummary:
    """Calcula agrupaciones por similitud y persiste el cluster_id en cada ticket."""

    if num_clusters <= 0:
        raise ValueError("num_clusters debe ser mayor a cero")

    tickets: list[Ticket] = list(
        Ticket.objects.order_by("id").only("id", "title", "description", "cluster_id")
    )
    total = len(tickets)
    if total == 0:
        logger.info("No hay tickets para agrupar")
        return ClusterSummary(0, num_clusters, 0, {})

    normalized_texts = [
        _normalize_text(f"{t.title} {t.description}") for t in tickets
    ]

    non_empty = [text for text in normalized_texts if text]
    if not non_empty:
        logger.warning("Todos los tickets tienen texto vacío; asignando cluster único")
        with transaction.atomic():
            Ticket.objects.update(cluster_id=1)
        return ClusterSummary(total, num_clusters, 1, {1: total})

    effective_clusters = min(num_clusters, total)

    if effective_clusters == 1:
        with transaction.atomic():
            Ticket.objects.update(cluster_id=1)
        return ClusterSummary(total, num_clusters, 1, {1: total})

    try:
        matrix = _vectorize(normalized_texts)
    except ValueError:
        logger.warning("Vocabulario vacío al vectorizar; asignando cluster único")
        with transaction.atomic():
            Ticket.objects.update(cluster_id=1)
        return ClusterSummary(total, num_clusters, 1, {1: total})

    # scikit-learn requiere que n_samples >= n_clusters
    if total < effective_clusters:
        effective_clusters = total

    model = KMeans(n_clusters=effective_clusters, n_init=10, random_state=42)
    labels = model.fit_predict(matrix)

    label_counts = Counter(int(label) for label in labels)

    with transaction.atomic():
        for ticket, label in zip(tickets, labels, strict=False):
            ticket.cluster_id = int(label) + 1  # 1-based para lectura sencilla
        Ticket.objects.bulk_update(tickets, ["cluster_id"])

    assignments = {label + 1: count for label, count in label_counts.items()}
    logger.info(
        "Clusterización completada",
        extra={
            "total_tickets": total,
            "requested_clusters": num_clusters,
            "effective_clusters": effective_clusters,
            "assignments": assignments,
        },
    )

    return ClusterSummary(
        total_tickets=total,
        requested_clusters=num_clusters,
        effective_clusters=effective_clusters,
        assignments=assignments,
    )


__all__ = ["train_ticket_clusters", "ClusterSummary"]
