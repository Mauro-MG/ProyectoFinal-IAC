"""Ejecutable de consola del instalador: diagnóstico de conexión (equivale a --diagnostico)."""
import sys

from abastored_escritorio.__main__ import diagnostico

sys.exit(diagnostico())
