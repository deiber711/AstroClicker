# AstroClicker

AstroClicker es una aplicación de autoclicker para Windows con interfaz gráfica, escrita en Python. Permite configurar la velocidad de clic, atajos de teclado personalizables, variación aleatoria (jitter) entre clics, un modo de prueba de CPS (clics por segundo) y persistencia de configuración entre sesiones.

Este proyecto nació como un sub-componente de **AstroTools / AstroMacros** y fue extraído para funcionar como una aplicación independiente.

## Características

- **Activación/desactivación con hotkey global** (por defecto `F6`), configurable con combinaciones de teclas (incluye modificadores como `Ctrl`, `Shift`, `Alt`).
- **Tecla de emergencia** (por defecto `F8`) para detener el autoclicker de inmediato.
- **Configuración de velocidad**: clics por ciclo e intervalo entre ciclos, ajustables desde la interfaz.
- **Jitter aleatorio**: variación de tiempo entre clics para simular un patrón menos uniforme.
- **Botón del mouse configurable**: izquierdo o derecho.
- **Icono en la bandeja del sistema** (system tray), con opción de minimizar a la bandeja al cerrar la ventana.
- **Pestaña de Test de CPS**: simula clics para medir el rendimiento real (clics procesados, tiempo transcurrido, CPS real, eficiencia).
- **Guardado automático de configuración** en `config_autoclicker.json`.
- **Logs opcionales** en consola.
- Optimización interna: usa un temporizador de alta precisión de Windows (`timeBeginPeriod`) y ajusta la prioridad del proceso para mayor estabilidad en la cadencia de clics.

## Requisitos

- Windows (usa APIs de `ctypes.windll`, por lo que no es multiplataforma).
- Python 3.9 o superior.

### Dependencias de Python

```bash
pip install ttkbootstrap pynput pillow pystray customtkinter
```

| Paquete | Uso |
|---|---|
| `ttkbootstrap` | Interfaz gráfica (obligatorio) |
| `pynput` | Escucha global de teclado para los hotkeys (obligatorio) |
| `pillow` (`PIL`) | Generación del ícono de la bandeja del sistema (opcional, con degradación segura si falta) |
| `pystray` | Icono en la bandeja del sistema (opcional) |
| `customtkinter` | Soporte adicional de UI (opcional, se importa de forma defensiva) |

> Las dependencias opcionales están envueltas en bloques `try/except` en el código: si no están instaladas, la app sigue funcionando pero sin esa característica (por ejemplo, sin ícono de bandeja).

## Uso

Ejecutar directamente con Python:

```bash
python astroclicker.py
```

Al iniciar:

1. Se carga automáticamente la configuración guardada (`config_autoclicker.json`), si existe.
2. Se abre la interfaz con tres pestañas:
   - **AstroClicker**: panel principal de control (estado, velocidad, hotkeys, botones de inicio/paro).
   - **Test de CPS**: simulación y medición de clics por segundo.
   - **Ajustes**: configuración general, guardado y logs.
3. Presiona la tecla configurada (por defecto `F6`) para activar/desactivar el autoclicker.
4. Presiona la tecla de emergencia (por defecto `F8`) para detenerlo inmediatamente.

## Compilar a ejecutable (.exe)

El proyecto incluye un script de batch para compilar con PyInstaller:

```bash
convert_to_exe.bat
```

Este script:

1. Limpia las carpetas `build/` y `dist/` de compilaciones anteriores.
2. Compila el proyecto usando el archivo de especificación `AstroClicker.spec` con PyInstaller.
3. Genera el ejecutable final en `dist\AstroClicker.exe`.

### Requisito previo

```bash
pip install pyinstaller
```

Y asegúrate de que `AstroClicker.spec` esté presente en el mismo directorio que el `.bat` (no incluido en este repositorio; debe generarse o mantenerse aparte).

## Estructura de archivos

```
.
├── astroclicker.py         # Código fuente principal
├── convert_to_exe.bat      # Script de compilación a .exe (PyInstaller)
├── AstroClicker.spec       # Especificación de PyInstaller (requerido para compilar)
└── config_autoclicker.json # Configuración generada automáticamente en tiempo de ejecución
```

## Configuración persistente

La app guarda su configuración en `config_autoclicker.json`, ubicado junto al ejecutable o script. Incluye:

- `clicks_por_ciclo`
- `intervalo_ms`
- `tecla_toggle`
- `tecla_emergencia`
- `boton_mouse`
- `aplicado_auto`
- `mostrar_logs`
- `guardar_automaticamente_cambios`
- `minimizar_a_bandeja_al_cerrar`
- `jitter_aleatorio_activo`
- `variacion_max_ms`

Si el archivo no existe, la app usa valores por defecto seguros y lo crea a partir de la primera ejecución con cambios.

## Notas

- Compatible únicamente con Windows por su dependencia de APIs de bajo nivel (`ctypes.windll`) para simular clics y ajustar la prioridad/temporización del proceso.
- Este proyecto fue extraído de **AstroMacros** (parte de **AstroTools**) para funcionar de forma independiente.

## Descargo de responsabilidad

Este software está pensado para uso personal y pruebas. El uso de autoclickers puede estar prohibido en algunos juegos, plataformas o servicios en línea — revisa los términos de servicio correspondientes antes de usarlo.
