# mvp-tickets/core/test_runner.py
from __future__ import annotations
import unittest
import datetime
from pathlib import Path
from django.conf import settings
from django.test.runner import DiscoverRunner
from unittest.runner import TextTestResult

LABELS = {
    "rendimiento": "Prueba de rendimiento",
    "integral": "Prueba integral",
    "unitaria": "Prueba unitaria",
}

def _label_for(test) -> str:
    fn = getattr(test, test._testMethodName, None)
    tags = getattr(fn, "__django_test_tags__", set()) if fn else set()
    for key in ("rendimiento", "integral", "unitaria"):
        if key in tags:
            return LABELS[key]
    return LABELS["unitaria"]

def _explain(test) -> str:
    # Usa el docstring del test; si no hay, el nombre del método
    desc = test.shortDescription()
    return desc if desc else test._testMethodName

class HumanResult(TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        self.stream.write(f"- [{_label_for(test)}] {_explain(test)} → Éxito\n")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.write(f"- [{_label_for(test)}] {_explain(test)} → Fallo\n")

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.write(f"- [{_label_for(test)}] {_explain(test)} → Error\n")

class HumanRunner(DiscoverRunner):
    def run_suite(self, suite, **kwargs):
        out = Path(getattr(settings, "BASE_DIR", ".")) / "test_run.txt"
        with out.open("w", encoding="utf-8") as stream:  # ← SOBREESCRIBE CADA VEZ
            now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
            stream.write(f"Ejecución: {now}\n")
            runner = unittest.TextTestRunner(
                stream=stream, verbosity=2, resultclass=HumanResult, descriptions=True
            )
            result = runner.run(suite)
            successes = result.testsRun - len(result.failures) - len(result.errors) - len(getattr(result, "skipped", [])) \
                        - len(getattr(result, "expectedFailures", [])) + len(getattr(result, "unexpectedSuccesses", []))
            stream.write(
                f"Total de pruebas: {result.testsRun}\n"
                f"Resumen: {successes} éxitos, "
                f"{len(result.failures)} fallos, {len(result.errors)} errores, "
                f"{len(getattr(result, 'skipped', []))} omitidas, "
                f"{len(getattr(result, 'expectedFailures', []))} fallos esperados, "
                f"{len(getattr(result, 'unexpectedSuccesses', []))} éxitos inesperados\n"
            )
            return result
