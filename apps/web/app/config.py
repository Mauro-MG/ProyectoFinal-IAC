import os

from abasto_dominio.configuracion import ConfiguracionBase


class Config(ConfiguracionBase):
    # El web manda las notificaciones a ms-notificaciones y, si no responde, las guarda directo
    NOTIFICACIONES_VIA_SERVICIO = os.environ.get('NOTIFICACIONES_VIA_SERVICIO', 'true').lower() == 'true'
    # El análisis se pide a ms-analisis; si no responde, el web lo calcula con la misma biblioteca
    ANALISIS_VIA_SERVICIO = os.environ.get('ANALISIS_VIA_SERVICIO', 'true').lower() == 'true'
    # Dirección con la que el navegador llega a los servicios (enlaces a Swagger en Estado de los servicios)
    MS_DOCS_HOST = os.environ.get('MS_DOCS_HOST', 'http://localhost')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
