"""
Dominio de AbastoRed: modelos, reglas de negocio y sesiones.

Lo usan el sistema web (apps/web) y cada microservicio (apps/microservicios/*).
Así una regla como "no se envía un pedido debajo del mínimo" existe en un solo
lugar, y el web y el servicio de pedidos la aplican igual.

Uso desde una aplicación Flask:

    from abasto_dominio import extensiones
    from abasto_dominio.configuracion import ConfiguracionBase
    app.config.from_object(ConfiguracionBase)
    extensiones.init_app(app)
"""
