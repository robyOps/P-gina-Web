"""Test runner personalizado que registra cada ejecución en ``test_run.txt``.

El objetivo es enriquecer el ciclo de pruebas dejando una bitácora en español
con información detallada sobre cada caso, su categoría (unitaria, integral o
rendimiento) y el estado final. Esto permite correlacionar ejecuciones de
``python manage.py test`` con los resultados que se obtuvieron en ese momento.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.runner import TextTestResult

from django.conf import settings
from django.test.runner import DiscoverRunner


@dataclass
class RecordedTest:
    """Estructura intermedia para serializar resultados de pruebas."""

    identifier: str
    description: str
    category: str
    state_key: str
    state_label: str
    detail: str | None = None


class RecordingTestResult(TextTestResult):
    """Extiende ``TextTestResult`` para almacenar resultados individuales."""

    def __init__(self, stream, descriptions: bool, verbosity: int) -> None:  # noqa: D401
        super().__init__(stream, descriptions, verbosity)
        self.test_records: list[RecordedTest] = []

    # -- Hooks de resultado -------------------------------------------------
    def addSuccess(self, test: Any) -> None:  # noqa: N802 (API de unittest)
        super().addSuccess(test)
        self._register(test, "success", "Éxito")

    def addFailure(self, test: Any, err: Any) -> None:  # noqa: N802
        super().addFailure(test, err)
        self._register(test, "failure", "Fallo")

    def addError(self, test: Any, err: Any) -> None:  # noqa: N802
        super().addError(test, err)
        self._register(test, "error", "Error")

    def addSkip(self, test: Any, reason: str) -> None:  # noqa: N802
        super().addSkip(test, reason)
        self._register(test, "skipped", "Omitida", detail=reason)

    def addExpectedFailure(self, test: Any, err: Any) -> None:  # noqa: N802
        super().addExpectedFailure(test, err)
        self._register(test, "expected_failure", "Fallo esperado")

    def addUnexpectedSuccess(self, test: Any) -> None:  # noqa: N802
        super().addUnexpectedSuccess(test)
        self._register(test, "unexpected_success", "Éxito inesperado")

    def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:  # noqa: N802
        """Registra subtests exitosos o con errores."""

        super().addSubTest(test, subtest, err)
        params = getattr(subtest, "params", None)
        params_repr = params if params is not None else str(subtest)
        identifier = f"{test.id()} (subprueba: {params_repr})"
        description = self.getDescription(test)
        state_key = "success" if err is None else "failure"
        state_label = "Éxito" if err is None else "Fallo"
        self.test_records.append(
            RecordedTest(
                identifier=identifier,
                description=description,
                category=self._classify_test(identifier),
                state_key=state_key,
                state_label=state_label,
                detail="Subprueba",
            )
        )

    # -- Utilidades internas -------------------------------------------------
    def _register(
        self,
        test: Any,
        state_key: str,
        state_label: str,
        *,
        detail: str | None = None,
    ) -> None:
        identifier = getattr(test, "id", lambda: str(test))()
        description = self.getDescription(test)
        self.test_records.append(
            RecordedTest(
                identifier=identifier,
                description=description,
                category=self._classify_test(identifier),
                state_key=state_key,
                state_label=state_label,
                detail=detail,
            )
        )

    @staticmethod
    def _classify_test(identifier: str) -> str:
        lowered = identifier.lower()
        if "performance" in lowered or "rendimiento" in lowered:
            return "Prueba de rendimiento"
        if ".api" in lowered or "apitest" in lowered or "apitests" in lowered:
            return "Prueba integral"
        return "Prueba unitaria"


class TestRunRecordingRunner(DiscoverRunner):
    """Runner que persiste un log de la ejecución en ``test_run.txt``."""

    def run_suite(self, suite, **kwargs):  # noqa: D401
        result: RecordingTestResult = super().run_suite(suite, **kwargs)
        try:
            self._write_execution_log(result)
        except Exception:  # pragma: no cover - nunca debe abortar las pruebas
            # Si ocurre un error al escribir el log, lo reportamos en la salida
            # estándar pero no interrumpimos la ejecución de Django.
            print("No se pudo escribir test_run.txt")
        return result

    def get_test_runner_kwargs(self):  # noqa: D401
        kwargs = super().get_test_runner_kwargs()
        kwargs["resultclass"] = RecordingTestResult
        return kwargs

    # -- Persistencia -------------------------------------------------------
    def _write_execution_log(self, result: RecordingTestResult) -> None:
        base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
        log_path = base_dir.parent / "artifacts" / "test_run.txt"
        timestamp = datetime.now().astimezone()
        header = [
            f"Ejecución: {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"Total de pruebas: {len(result.test_records)}",
        ]

        counts = Counter(record.state_key for record in result.test_records)
        resumen = ", ".join(
            [
                f"{counts.get('success', 0)} éxitos",
                f"{counts.get('failure', 0)} fallos",
                f"{counts.get('error', 0)} errores",
                f"{counts.get('skipped', 0)} omitidas",
                f"{counts.get('expected_failure', 0)} fallos esperados",
                f"{counts.get('unexpected_success', 0)} éxitos inesperados",
            ]
        )
        header.append(f"Resumen: {resumen}")

        lines = header + ["Detalle de pruebas:"]
        for record in result.test_records:
            detail_suffix = f" ({record.detail})" if record.detail else ""
            lines.append(
                "- "
                f"[{record.category}] Se realiza test de {record.description} "
                f"→ {record.state_label}{detail_suffix}"
            )

        block = "\n".join(lines) + "\n\n"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handler:
            handler.write(block)


__all__ = ["TestRunRecordingRunner"]
