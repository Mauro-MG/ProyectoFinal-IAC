# Instalador de la aplicación de escritorio: prueba en un entorno limpio

**Fecha:** 24 de noviembre de 2026.

## Archivo probado

| Dato | Valor |
| :--- | :--- |
| Instalador | `AbastoRed-1.1.0-win64.msi` (46.4 MB) |
| SHA-256 | `5a7ef0240233c7d272c6686e47cfe5a16463241426b3d415c850033d29bf90c4` |
| Construcción | `python instalador/construir_instalador.py --gateway https://localhost --certificado ../../infra/certs/abastored.crt` |
| Herramientas | cx_Freeze 7.2.3 y Python 3.12.9 |

El `.msi` no se sube al repositorio porque es un binario de 46 MB. Se genera con el comando anterior
o se adjunta como *release*.

## Qué se comprobó

1. **Instalación administrativa:** `msiexec /a <msi> /qn TARGETDIR=<carpeta>`.
   - Extrae el contenido sin registrar nada en Windows.
   - Terminó con código 0.
   - La carpeta contiene:
     - `AbastoRed.exe` (gráfico);
     - `AbastoRed-diagnostico.exe` (de consola);
     - `abastored.ini`;
     - `certificados/gateway.crt`, que es solo el certificado público;
     - `lib/`, con Python, PySide6, lxml y requests empaquetados.

2. **Diagnóstico con un entorno mínimo.** Se corrió `AbastoRed-diagnostico.exe` con todas las
   variables de entorno borradas, menos `SystemRoot`. Además:
   - `PATH` solo con `C:\Windows\system32`, sin Python;
   - `APPDATA` y `USERPROFILE` apuntando a una carpeta vacía;
   - sin acceso al repositorio.

   Salida real:

   ```
   AbastoRed escritorio · ejecutable: True
   Gateway: https://localhost
   Certificado: ...\msi_limpio\certificados\gateway.crt
   Carpeta local: ...\perfil_limpio\AbastoRed
     ms-seguridad: contrato XSD válido con 23 elementos raíz
     ms-comercios: contrato XSD válido con 12 elementos raíz
     ms-analisis: contrato XSD válido con 12 elementos raíz
     Estado público (XML validado): 24 de 24 servicios en línea
   Diagnóstico correcto
   ```

   El resultado fue código 0. La configuración y el certificado salieron del instalador, y la
   conexión TLS al gateway se verificó con ese certificado.

3. **Arranque de la aplicación gráfica** en el mismo entorno, con `QT_QPA_PLATFORM=offscreen`.
   - A los 8 s seguía corriendo, esperando en la ventana de inicio de sesión.
   - Creó su bitácora local en el perfil vacío (`AbastoRed\bitacora.sqlite3`).

## Pendiente

Falta la **prueba manual en otra computadora** con Windows recién instalado. Es una instalación
normal: doble clic, acceso directo en el menú Inicio, iniciar sesión, recorrer los módulos y
desinstalar. Se hace con el instalador construido para la dirección del servidor desplegado (ver
`apps/infra/README.md`).
