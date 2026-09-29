"""Punto de entrada para Gunicorn: gunicorn wsgi:app"""
from app import app  # noqa: F401
