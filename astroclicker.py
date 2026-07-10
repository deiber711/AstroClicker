import atexit
import ctypes
import importlib
import json
import os
import random
import re
import sys
import threading
import time
import tkinter
from tkinter import messagebox
import ttkbootstrap as ttk
from pynput import keyboard as kb
from dataclasses import dataclass, asdict

try:
    ctk = importlib.import_module("customtkinter")
except Exception:
    ctk = None

try:
    pystray = importlib.import_module("pystray")
except Exception:
    pystray = None

try:
    pil_image = importlib.import_module("PIL.Image")
    pil_draw = importlib.import_module("PIL.ImageDraw")
except Exception:
    pil_image = None
    pil_draw = None

try:
    pil_imagetk = importlib.import_module("PIL.ImageTk")
except Exception:
    pil_imagetk = None


# --- NÚCLEO DEL AUTOCLICKER ---

HOTKEY_TOGGLE_POR_DEFECTO = "f6"
HOTKEY_EMERGENCIA_POR_DEFECTO = "f8"

clicks_por_ciclo = 6
intervalo        = 0.015
activo           = False
corriendo        = True
tecla_toggle     = HOTKEY_TOGGLE_POR_DEFECTO
tecla_emergencia = HOTKEY_EMERGENCIA_POR_DEFECTO
esperando_tecla  = False
esperando_emergencia = False
boton_mouse      = 'izquierdo'
aplicado_auto    = False
mostrar_advertencia_seguridad = True
mostrar_logs     = True
guardar_automaticamente_cambios = True
minimizar_a_bandeja_al_cerrar = False
evento_activo    = threading.Event()
timer_precision_activa = False
icono_bandeja = None
bloqueo_icono_bandeja = threading.Lock()
jitter_aleatorio_activo = False
variacion_max_ms = 4
conflicto_hotkeys_cargadas = False
MODIFICADORES_HOTKEY = {"shift", "ctrl", "alt", "cmd", "windows"}


@dataclass
class Config:
    clicks_por_ciclo: int = 6
    intervalo: float = 0.015
    tecla_toggle: str = HOTKEY_TOGGLE_POR_DEFECTO
    tecla_emergencia: str = HOTKEY_EMERGENCIA_POR_DEFECTO
    boton_mouse: str = 'izquierdo'
    aplicado_auto: bool = False
    mostrar_advertencia_seguridad: bool = True
    mostrar_logs: bool = True
    guardar_automaticamente_cambios: bool = True
    minimizar_a_bandeja_al_cerrar: bool = False
    jitter_aleatorio_activo: bool = False
    variacion_max_ms: int = 4


# Instancia global de configuración.
cfg = Config()

def _sync_config_to_globals():
    global clicks_por_ciclo, intervalo, tecla_toggle, tecla_emergencia
    global boton_mouse, aplicado_auto
    global mostrar_advertencia_seguridad, mostrar_logs, guardar_automaticamente_cambios
    global minimizar_a_bandeja_al_cerrar
    global jitter_aleatorio_activo, variacion_max_ms

    clicks_por_ciclo = cfg.clicks_por_ciclo
    intervalo = cfg.intervalo
    tecla_toggle = cfg.tecla_toggle
    tecla_emergencia = cfg.tecla_emergencia
    boton_mouse = cfg.boton_mouse
    aplicado_auto = cfg.aplicado_auto
    mostrar_advertencia_seguridad = cfg.mostrar_advertencia_seguridad
    mostrar_logs = cfg.mostrar_logs
    guardar_automaticamente_cambios = cfg.guardar_automaticamente_cambios
    minimizar_a_bandeja_al_cerrar = cfg.minimizar_a_bandeja_al_cerrar
    jitter_aleatorio_activo = cfg.jitter_aleatorio_activo
    variacion_max_ms = cfg.variacion_max_ms


def _sync_globals_to_config():
    cfg.clicks_por_ciclo = int(clicks_por_ciclo)
    cfg.intervalo = float(intervalo)
    cfg.boton_mouse = str(boton_mouse)
    cfg.aplicado_auto = bool(aplicado_auto)
    cfg.mostrar_advertencia_seguridad = bool(mostrar_advertencia_seguridad)
    cfg.mostrar_logs = bool(mostrar_logs)
    cfg.guardar_automaticamente_cambios = bool(guardar_automaticamente_cambios)
    cfg.minimizar_a_bandeja_al_cerrar = bool(minimizar_a_bandeja_al_cerrar)
    cfg.jitter_aleatorio_activo = bool(jitter_aleatorio_activo)
    cfg.variacion_max_ms = int(variacion_max_ms)


def texto_hotkey_legible(hotkey_cadena):
    especiales = {
        "space": "ESPACIO",
        "esc": "ESC",
        "enter": "ENTER",
        "tab": "TAB",
        "backspace": "BKSP",
        "shift": "SHIFT",
        "ctrl": "CTRL",
        "alt": "ALT",
        "cmd": "CMD",
        "windows": "WIN",
    }
    tokens = combo_desde_cadena_hotkey(hotkey_cadena)
    if not tokens:
        return "-"
    return " + ".join(especiales.get(token, token.upper()) for token in tokens)


def corregir_hotkey_legacy(cadena):
    if not isinstance(cadena, str):
        return ""

    cruda = cadena.strip().lower()
    if not cruda:
        return ""

    partes = [p for p in cruda.split("+") if p.strip()]
    if "f" in partes and all((p == "f" or p.isdigit()) for p in partes):
        digitos = "".join(p for p in partes if p.isdigit())
        if digitos == "01":
            digitos = "10"
        if digitos.isdigit():
            valor = int(digitos)
            if 1 <= valor <= 24:
                return f"f{valor}"

    return cruda


def normalizar_token_hotkey(token):
    token = (token or "").strip().lower()
    alias = {
        "shift_l": "shift",
        "shift_r": "shift",
        "ctrl_l": "ctrl",
        "ctrl_r": "ctrl",
        "alt_l": "alt",
        "alt_r": "alt",
        "alt_gr": "alt",
        "cmd_l": "cmd",
        "cmd_r": "cmd",
        "super_l": "windows",
        "super_r": "windows",
    }
    return alias.get(token, token)


def ordenar_tokens_hotkey(tokens):
    unicos = []
    vistos = set()
    for token in tokens:
        norm = normalizar_token_hotkey(token)
        if not norm or norm in vistos:
            continue
        vistos.add(norm)
        unicos.append(norm)

    return tuple(sorted(unicos, key=lambda t: (0 if t in MODIFICADORES_HOTKEY else 1, t)))


def combo_desde_cadena_hotkey(cadena):
    if not isinstance(cadena, str):
        return tuple()
    partes = [p for p in cadena.split("+") if p.strip()]
    return ordenar_tokens_hotkey(partes)


def cadena_desde_combo_hotkey(tokens):
    return "+".join(ordenar_tokens_hotkey(tokens))

def log_mensaje(mensaje):
    try:
        mostrar = cfg.mostrar_logs
    except Exception:
        mostrar = True
    if mostrar:
        print(mensaje)

def obtener_directorio_base_app():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(__file__)


def obtener_ruta_recurso(nombre_archivo):
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, nombre_archivo)
    return os.path.join(obtener_directorio_base_app(), nombre_archivo)


RUTA_CONFIG = os.path.join(obtener_directorio_base_app(), "config_autoclicker.json")


def cargar_configuracion():
    global clicks_por_ciclo, intervalo, tecla_toggle, tecla_emergencia
    global boton_mouse, aplicado_auto
    global mostrar_advertencia_seguridad, mostrar_logs, guardar_automaticamente_cambios
    global minimizar_a_bandeja_al_cerrar
    global jitter_aleatorio_activo, variacion_max_ms
    global conflicto_hotkeys_cargadas

    conflicto_hotkeys_cargadas = False

    if not os.path.exists(RUTA_CONFIG):
        return

    try:
        with open(RUTA_CONFIG, "r", encoding="utf-8") as archivo:
            data = json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return

    clicks = data.get("clicks_por_ciclo", cfg.clicks_por_ciclo)
    if isinstance(clicks, int):
        cfg.clicks_por_ciclo = min(max(clicks, 1), 20)

    intervalo_ms = data.get("intervalo_ms", int(cfg.intervalo * 1000))
    if isinstance(intervalo_ms, int):
        intervalo_ms = min(max(intervalo_ms, 1), 100)
        cfg.intervalo = intervalo_ms / 1000

    tecla = data.get("tecla_toggle", cfg.tecla_toggle)
    if isinstance(tecla, str) and tecla.strip():
        tecla_normalizada = corregir_hotkey_legacy(tecla)
        cfg.tecla_toggle = cadena_desde_combo_hotkey(combo_desde_cadena_hotkey(tecla_normalizada))

    tecla_escape = data.get("tecla_emergencia", cfg.tecla_emergencia)
    if isinstance(tecla_escape, str) and tecla_escape.strip():
        cfg.tecla_emergencia = cadena_desde_combo_hotkey(combo_desde_cadena_hotkey(corregir_hotkey_legacy(tecla_escape)))

    # Evita un estado inválido si un config viejo trae teclas duplicadas.
    if cfg.tecla_toggle == cfg.tecla_emergencia:
        conflicto_hotkeys_cargadas = True
        cfg.tecla_emergencia = HOTKEY_EMERGENCIA_POR_DEFECTO

    boton = data.get("boton_mouse", cfg.boton_mouse)
    if boton in ("izquierdo", "derecho"):
        cfg.boton_mouse = boton

    auto = data.get("aplicado_auto", cfg.aplicado_auto)
    if isinstance(auto, bool):
        cfg.aplicado_auto = auto

    logs = data.get("mostrar_logs", cfg.mostrar_logs)
    if isinstance(logs, bool):
        cfg.mostrar_logs = logs

    guardado_auto = data.get("guardar_automaticamente_cambios", cfg.guardar_automaticamente_cambios)
    if isinstance(guardado_auto, bool):
        cfg.guardar_automaticamente_cambios = guardado_auto

    minimizar_a_bandeja = data.get("minimizar_a_bandeja_al_cerrar", cfg.minimizar_a_bandeja_al_cerrar)
    if isinstance(minimizar_a_bandeja, bool):
        cfg.minimizar_a_bandeja_al_cerrar = minimizar_a_bandeja

    jitter_activado = data.get("jitter_aleatorio_activo", cfg.jitter_aleatorio_activo)
    if isinstance(jitter_activado, bool):
        cfg.jitter_aleatorio_activo = jitter_activado

    variacion = data.get("variacion_max_ms", cfg.variacion_max_ms)
    if isinstance(variacion, int):
        cfg.variacion_max_ms = min(max(variacion, 0), 12)

    try:
        _sync_config_to_globals()
    except Exception:
        pass


def guardar_configuracion(forzado=False):
    if not forzado and not cfg.guardar_automaticamente_cambios:
        return
    try:
        _sync_globals_to_config()
    except Exception:
        pass

    data = {
        "clicks_por_ciclo": int(cfg.clicks_por_ciclo),
        "intervalo_ms": int(cfg.intervalo * 1000),
        "tecla_toggle": cfg.tecla_toggle,
        "tecla_emergencia": cfg.tecla_emergencia,
        "boton_mouse": cfg.boton_mouse,
        "aplicado_auto": cfg.aplicado_auto,
        "mostrar_logs": cfg.mostrar_logs,
        "guardar_automaticamente_cambios": cfg.guardar_automaticamente_cambios,
        "minimizar_a_bandeja_al_cerrar": cfg.minimizar_a_bandeja_al_cerrar,
        "jitter_aleatorio_activo": cfg.jitter_aleatorio_activo,
        "variacion_max_ms": int(cfg.variacion_max_ms),
    }

    try:
        with open(RUTA_CONFIG, "w", encoding="utf-8") as archivo:
            json.dump(data, archivo, ensure_ascii=False, indent=2)
    except OSError:
        pass


_establecer_estado_callback = None


def registrar_establecer_estado(callback):
    global _establecer_estado_callback
    _establecer_estado_callback = callback


def establecer_estado(nuevo_estado, animar=False):
    if callable(_establecer_estado_callback):
        return _establecer_estado_callback(nuevo_estado, animar=animar)


# Optimizaciones de referencias (búsqueda más rápida en el bucle caliente)
_mouse_event = ctypes.windll.user32.mouse_event
_perf_counter = time.perf_counter
_sleep = time.sleep

def click_rapido():
    if cfg.boton_mouse == "derecho":
        down, up = 0x0008, 0x0010
    else:
        down, up = 0x0002, 0x0004

    _mouse_event(down, 0, 0, 0, 0)
    _mouse_event(up, 0, 0, 0, 0)


def liberar_timer_precision():
    global timer_precision_activa
    if not timer_precision_activa:
        return
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass
    timer_precision_activa = False

def bucle_clicker():
    proximo_tick = _perf_counter()
    while corriendo:
        if not evento_activo.wait(timeout=0.1):
            continue

        if activo:
            clicks_actuales = cfg.clicks_por_ciclo
            intervalo_actual = max(cfg.intervalo, 0.001)
            if cfg.jitter_aleatorio_activo:
                base_por_click = max(0.001, intervalo_actual / max(clicks_actuales, 1))
                for _ in range(clicks_actuales):
                    click_rapido()
                    variacion_actual = random.uniform(-cfg.variacion_max_ms, cfg.variacion_max_ms) / 1000
                    espera_click = max(0.001, base_por_click + variacion_actual)
                    _sleep(espera_click)
                proximo_tick = _perf_counter()
            else:
                for i in range(clicks_actuales):
                    click_rapido()
                    if i < clicks_actuales - 1:
                        _sleep(0)

                proximo_tick += intervalo_actual
                espera = proximo_tick - _perf_counter()
                if espera > 0:
                    _sleep(espera)
                else:
                    proximo_tick = _perf_counter()
        else:
            evento_activo.clear()
            proximo_tick = _perf_counter()


def bandeja_disponible():
    return pystray is not None and pil_image is not None and pil_draw is not None


def icono_ventana_disponible():
    return pil_image is not None and pil_imagetk is not None


def crear_icono_bandeja(esta_activo):
    tam = 64
    imagen = pil_image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    dibujo = pil_draw.Draw(imagen)

    color_rayo = (68, 214, 122, 255) if esta_activo else (225, 84, 96, 255)
    color_borde = (255, 255, 255, 230)
    color_brillo = (255, 255, 255, 72)

    dibujo.ellipse((4, 4, tam - 4, tam - 4), fill=(30, 36, 45, 240), outline=(255, 255, 255, 110), width=2)
    dibujo.ellipse((10, 10, tam - 10, tam - 10), fill=(20, 24, 31, 210))
    dibujo.polygon(
        [
            (tam * 0.56, tam * 0.12),
            (tam * 0.30, tam * 0.54),
            (tam * 0.48, tam * 0.54),
            (tam * 0.42, tam * 0.88),
            (tam * 0.72, tam * 0.40),
            (tam * 0.54, tam * 0.40),
        ],
        fill=color_rayo,
        outline=color_borde,
    )
    dibujo.ellipse((8, 8, tam // 2, tam // 2), fill=color_brillo)

    return imagen


def crear_icono_ventana_tk(esta_activo, tam=64):
    if not icono_ventana_disponible():
        return None

    ruta_ico = obtener_ruta_icono_estado(esta_activo)

    imagen_base = None
    if ruta_ico and os.path.exists(ruta_ico):
        try:
            imagen_base = pil_image.open(ruta_ico).convert("RGBA")
        except Exception:
            imagen_base = None

    if imagen_base is None:
        imagen_base = crear_icono_bandeja(esta_activo)

    if hasattr(pil_image, "Resampling"):
        remuestreo = pil_image.Resampling.LANCZOS
    else:
        remuestreo = pil_image.LANCZOS

    return pil_imagetk.PhotoImage(imagen_base.resize((tam, tam), remuestreo))


def obtener_ruta_icono_estado(esta_activo):
    if esta_activo:
        candidatos = ["astroclicker_active.ico", "astrotools_active.ico"]
    else:
        candidatos = ["astroclicker_paused.ico", "astrotools_paused.ico"]

    for nombre in candidatos:
        ruta = obtener_ruta_recurso(nombre)
        if os.path.exists(ruta):
            return ruta
    return None


# --- INTERFAZ CON TTKBOOTSTRAP ---

def hotkey_a_vk_y_modificadores(hotkey_str):
    tokens = combo_desde_cadena_hotkey(hotkey_str)
    if not tokens:
        return None, []
        
    modificadores = []
    tecla_base = None
    
    mapa_mods = {
        "ctrl": 0x11,
        "alt": 0x12,
        "shift": 0x10,
        "windows": 0x5B,
        "cmd": 0x5B
    }
    
    mapa_especiales = {
        "space": 0x20,
        "esc": 0x1B,
        "enter": 0x0D,
        "tab": 0x09,
        "backspace": 0x08
    }
    
    for token in tokens:
        if token in mapa_mods:
            modificadores.append(mapa_mods[token])
        else:
            if token in mapa_especiales:
                tecla_base = mapa_especiales[token]
            elif len(token) == 1:
                tecla_base = ord(token.upper())
            elif re.match(r"^f([1-9]|1[0-9]|2[0-4])$", token):
                num = int(token[1:])
                tecla_base = 0x70 + (num - 1)
                
    return tecla_base, modificadores

def es_hotkey_presionado(vk_base, mod_list):
    if not vk_base:
        return False
        
    if not (ctypes.windll.user32.GetAsyncKeyState(vk_base) & 0x8000):
        return False
        
    for mod in mod_list:
        if not (ctypes.windll.user32.GetAsyncKeyState(mod) & 0x8000):
            return False
            
    todos_mods = {0x11, 0x12, 0x10, 0x5B}
    mods_no_requeridos = todos_mods - set(mod_list)
    for mod in mods_no_requeridos:
        if ctypes.windll.user32.GetAsyncKeyState(mod) & 0x8000:
            return False
            
    return True

def bucle_polling_teclas(root, on_emergencia_close_callback):
    toggle_was_pressed = False
    emergencia_was_pressed = False

    while corriendo:
        vk_toggle, mods_toggle = hotkey_a_vk_y_modificadores(cfg.tecla_toggle)
        vk_emergencia, mods_emergencia = hotkey_a_vk_y_modificadores(cfg.tecla_emergencia)

        if vk_emergencia:
            emergencia_is_pressed = es_hotkey_presionado(vk_emergencia, mods_emergencia)
            if emergencia_is_pressed and not emergencia_was_pressed:
                root.after(0, on_emergencia_close_callback)
            emergencia_was_pressed = emergencia_is_pressed

        if vk_toggle and not esperando_tecla and not esperando_emergencia:
            toggle_is_pressed = es_hotkey_presionado(vk_toggle, mods_toggle)
            if toggle_is_pressed and not toggle_was_pressed:
                root.after(0, lambda: establecer_estado(not activo, animar=True))
            toggle_was_pressed = toggle_is_pressed

        time.sleep(0.015)

def crear_interfaz():
    global activo, clicks_por_ciclo, intervalo
    global tecla_toggle, tecla_emergencia
    global esperando_tecla, esperando_emergencia, boton_mouse, aplicado_auto
    global mostrar_advertencia_seguridad, mostrar_logs, guardar_automaticamente_cambios
    global minimizar_a_bandeja_al_cerrar
    global jitter_aleatorio_activo, variacion_max_ms
    global conflicto_hotkeys_cargadas
    teclas_presionadas = set()
    disparo_toggle_activo = False
    disparo_emergencia_activo = False

    def texto_tecla(tecla):
        especiales = {
            "space": "ESPACIO",
            "esc": "ESC",
            "enter": "ENTER",
            "tab": "TAB",
            "backspace": "BKSP",
            "shift": "SHIFT",
            "shift_r": "SHIFT",
            "shift_l": "SHIFT",
            "ctrl": "CTRL",
            "ctrl_r": "CTRL",
            "ctrl_l": "CTRL",
            "alt": "ALT",
            "alt_r": "ALT",
            "alt_l": "ALT",
            "cmd": "CMD",
            "windows": "WIN",
        }
        return especiales.get(tecla, tecla.upper())

    def texto_hotkey(hotkey_cadena):
        tokens = combo_desde_cadena_hotkey(hotkey_cadena)
        if not tokens:
            return "-"
        return " + ".join(texto_tecla(token) for token in tokens)

    def crear_labelframe(parent, text, bootstyle=None):
        if not bootstyle:
            return ttk.Labelframe(parent, text=text)
        try:
            return ttk.Labelframe(parent, text=text, bootstyle=bootstyle)
        except Exception:
            return ttk.Labelframe(parent, text=text)

    texto_logs = None
    def registrar_log(texto):
        nonlocal texto_logs
        if not mostrar_logs or texto_logs is None:
            return
        hora = time.strftime("%H:%M:%S")
        texto_logs.configure(state="normal")
        texto_logs.insert("end", f"[{hora}] {texto}\n")
        texto_logs.see("end")
        texto_logs.configure(state="disabled")

    ventana = ttk.Window(themename="darkly")
    ventana.title("AstroClicker")
    ventana.geometry("680x780")
    ventana.minsize(660, 740)
    ventana.resizable(True, True)

    var_mostrar_logs = tkinter.BooleanVar(value=cfg.mostrar_logs)
    var_guardado_auto = tkinter.BooleanVar(value=cfg.guardar_automaticamente_cambios)
    var_minimizar_bandeja = tkinter.BooleanVar(value=cfg.minimizar_a_bandeja_al_cerrar)

    icono_ventana_tk = None

    def actualizar_icono_ventana():
        nonlocal icono_ventana_tk
        if not icono_ventana_disponible():
            return
        try:
            icono_ventana_tk = crear_icono_ventana_tk(activo)
            if icono_ventana_tk is not None:
                ventana.iconphoto(True, icono_ventana_tk)
            if os.name == "nt":
                ruta_ico = obtener_ruta_icono_estado(activo)
                if ruta_ico and os.path.exists(ruta_ico):
                    ventana.iconbitmap(ruta_ico)
        except Exception:
            pass

    actualizar_icono_ventana()

    if conflicto_hotkeys_cargadas:
        def avisar_conflicto_hotkeys_inicio():
            global conflicto_hotkeys_cargadas
            messagebox.showwarning(
                "Hotkeys en conflicto",
                "No es posible usar la misma hotkey para Iniciar/Pausar y Emergencia.\n"
                "\n"
                "Se corrigió automáticamente la tecla de emergencia para evitar conflictos.",
                parent=ventana,
            )
            conflicto_hotkeys_cargadas = False
            guardar_configuracion(forzado=True)

        ventana.after(250, avisar_conflicto_hotkeys_inicio)

    # Estilos de botones personalizados
    estilo = ttk.Style()
    estilo.configure("MoradoAccion.TButton",
                     font=("Segoe UI", 12, "bold"),
                     foreground="#FFFFFF",
                     background="#6A5AE0",
                     borderwidth=0)
    estilo.map("MoradoAccion.TButton",
               background=[("disabled", "#4B5160"), ("pressed", "#5143B8"), ("active", "#5A4BC8")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("RojoSuaveAccion.TButton",
                     font=("Segoe UI", 12, "bold"),
                     foreground="#FFFFFF",
                     background="#C95D6A",
                     borderwidth=0)
    estilo.map("RojoSuaveAccion.TButton",
               background=[("pressed", "#9F4A55"), ("active", "#B14F5C")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("VerdeAccion.TButton",
                     font=("Segoe UI", 12, "bold"),
                     foreground="#FFFFFF",
                     background="#2F8E57",
                     borderwidth=0)
    estilo.map("VerdeAccion.TButton",
               background=[("disabled", "#4B5160"), ("pressed", "#266E46"), ("active", "#2B7F4F")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("BotonEstadoGrandeVerde.TButton",
                     font=("Segoe UI", 14, "bold"),
                     foreground="#FFFFFF",
                     background="#2F8E57",
                     borderwidth=0,
                     padding=(14, 8))
    estilo.map("BotonEstadoGrandeVerde.TButton",
               background=[("pressed", "#266E46"), ("active", "#2B7F4F")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("BotonEstadoGrandeVerdeHover.TButton",
                     font=("Segoe UI", 14, "bold"),
                     foreground="#FFFFFF",
                     background="#39A967",
                     borderwidth=0,
                     padding=(14, 8))

    estilo.configure("BotonEstadoGrandeVerdePress.TButton",
                     font=("Segoe UI", 14, "bold"),
                     foreground="#FFFFFF",
                     background="#266E46",
                     borderwidth=0,
                     padding=(14, 7))

    estilo.configure("BotonEstadoGrandeRojo.TButton",
                     font=("Segoe UI", 14, "bold"),
                     foreground="#FFFFFF",
                     background="#B14F5C",
                     borderwidth=0,
                     padding=(14, 8))
    estilo.map("BotonEstadoGrandeRojo.TButton",
               background=[("pressed", "#923E49"), ("active", "#A44753")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("BotonEstadoGrandeRojoHover.TButton",
                     font=("Segoe UI", 14, "bold"),
                     foreground="#FFFFFF",
                     background="#C45C69",
                     borderwidth=0,
                     padding=(14, 8))

    estilo.configure("BotonEstadoGrandeRojoPress.TButton",
                     font=("Segoe UI", 14, "bold"),
                     foreground="#FFFFFF",
                     background="#923E49",
                     borderwidth=0,
                     padding=(14, 7))

    estilo.configure("PresetSuave.TButton",
                     font=("Segoe UI", 9, "bold"),
                     foreground="#FFFFFF",
                     background="#60A5FA",
                     borderwidth=0)
    estilo.map("PresetSuave.TButton",
               background=[("pressed", "#3F7FCC"), ("active", "#4A90E2")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("PresetOptima.TButton",
                     font=("Segoe UI", 9, "bold"),
                     foreground="#FFFFFF",
                     background="#7C6EE8",
                     borderwidth=0)
    estilo.map("PresetOptima.TButton",
               background=[("pressed", "#5E52BC"), ("active", "#6A5AE0")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("PresetMaximo.TButton",
                     font=("Segoe UI", 9, "bold"),
                     foreground="#FFFFFF",
                     background="#F59E0B",
                     borderwidth=0)
    estilo.map("PresetMaximo.TButton",
               background=[("pressed", "#C67D08"), ("active", "#FB923C")],
               foreground=[("disabled", "#D7D7D7"), ("!disabled", "#FFFFFF")])

    estilo.configure("CpsSuave.TLabel",
                     font=("Segoe UI", 10, "bold"),
                     foreground="#60A5FA")
    estilo.configure("CpsOptimo.TLabel",
                     font=("Segoe UI", 10, "bold"),
                     foreground="#7C6EE8")
    estilo.configure("CpsAgresivo.TLabel",
                     font=("Segoe UI", 10, "bold"),
                     foreground="#F59E0B")

    # --- Título ---
    canvas_titulo = tkinter.Canvas(ventana, bg="#534AB7", height=72,
                                    highlightthickness=0)
    canvas_titulo.pack(fill="x")
    rect_titulo = canvas_titulo.create_rectangle(
        0, 0, 380, 72, fill="#534AB7", outline="")
    txt_titulo = canvas_titulo.create_text(190, 28, text="⚡ AstroClicker ⚡",
                                           font=("Segoe UI", 16, "bold"),
                                           fill="#EEEDFE")
    txt_version = canvas_titulo.create_text(368, 14, text="Versión 2.1",
                                            font=("Segoe UI", 8, "bold"),
                                            fill="#D6D2FF", anchor="e")
    redimension_titulo_job = None
    ancho_titulo_pendiente = 380
    ancho_titulo_aplicado = None

    def aplicar_ajuste_titulo():
        nonlocal redimension_titulo_job, ancho_titulo_aplicado
        ancho = max(ancho_titulo_pendiente, 1)
        if ancho_titulo_aplicado == ancho:
            redimension_titulo_job = None
            return
        centro_x = ancho // 2
        canvas_titulo.coords(rect_titulo, 0, 0, ancho, 72)
        canvas_titulo.coords(txt_titulo, centro_x, 28)
        canvas_titulo.coords(txt_version, ancho - 12, 14)
        ancho_titulo_aplicado = ancho
        redimension_titulo_job = None

    def ajustar_canvas_titulo(event):
        nonlocal redimension_titulo_job, ancho_titulo_pendiente
        ancho_titulo_pendiente = event.width
        if redimension_titulo_job is not None:
            ventana.after_cancel(redimension_titulo_job)
        redimension_titulo_job = ventana.after(33, aplicar_ajuste_titulo)

    canvas_titulo.bind("<Configure>", ajustar_canvas_titulo)

    barra_inferior = ttk.Frame(ventana, padding=(10, 2, 10, 8))
    barra_inferior.pack(side="bottom", fill="x")

    contenido = ttk.Frame(ventana, padding=(10, 8, 10, 8))
    contenido.pack(fill="both", expand=True)

    notebook_principal = ttk.Notebook(contenido)
    notebook_principal.pack(fill="both", expand=True)

    tab_clicker = ttk.Frame(notebook_principal, padding=8)
    tab_test = ttk.Frame(notebook_principal, padding=8)
    notebook_principal.add(tab_clicker, text="AstroClicker")
    notebook_principal.add(tab_test, text="Test de CPS")

    # --- Pestaña Ajustes ---
    tab_ajustes = ttk.Frame(notebook_principal, padding=8)
    notebook_principal.add(tab_ajustes, text="Ajustes")

    # Título de la pestaña Ajustes
    label_titulo_ajustes = tkinter.Label(
        tab_ajustes,
        text="Ajustes Generales",
        font=("Segoe UI", 18, "bold"),
        bg="#1E293B",
        fg="#E1E8EF",
        pady=20
    )
    label_titulo_ajustes.pack(fill="x")

    frame_ajustes_config = crear_labelframe(tab_ajustes, text="Configuración y guardado")
    frame_ajustes_config.pack(fill="x", padx=8, pady=(0, 10))

    frame_ajustes_logs = crear_labelframe(tab_ajustes, text="Logs")
    frame_ajustes_logs.pack(fill="x", padx=8, pady=(0, 8))

    # Toggle para mostrar logs
    def actualizar_mostrar_logs(*args):
        cfg.mostrar_logs = var_mostrar_logs.get()
        guardar_configuracion()

    var_mostrar_logs.trace("w", actualizar_mostrar_logs)
    chk_mostrar_logs = ttk.Checkbutton(
        frame_ajustes_logs,
        text="Mostrar logs de eventos",
        variable=var_mostrar_logs,
        bootstyle="round-toggle",
    )
    chk_mostrar_logs.pack(anchor="w", padx=8, pady=(8, 8))

    chk_guardado_auto = ttk.Checkbutton(
        frame_ajustes_config,
        text="Guardar automáticamente los cambios",
        variable=var_guardado_auto,
        bootstyle="round-toggle",
    )
    chk_guardado_auto.pack(anchor="w", padx=8, pady=(8, 8))

    def guardar_configuracion_manual():
        guardar_configuracion(forzado=True)
        messagebox.showinfo(
            "Configuración guardada",
            "La configuración actual se guardó correctamente.",
            parent=ventana,
        )

    btn_guardar_config = ttk.Button(
        frame_ajustes_config,
        text="Guardar configuración",
        command=guardar_configuracion_manual,
        style="VerdeAccion.TButton",
        width=30,
    )
    btn_guardar_config.pack(anchor="w", padx=8, pady=(0, 2))

    def actualizar_estado_boton_guardar_config(*args):
        if var_guardado_auto.get():
            btn_guardar_config.configure(state="disabled")
        else:
            btn_guardar_config.configure(state="normal")

    def actualizar_guardado_auto(*args):
        cfg.guardar_automaticamente_cambios = var_guardado_auto.get()
        guardar_configuracion(forzado=True)
        actualizar_estado_boton_guardar_config()

    var_guardado_auto.trace("w", actualizar_guardado_auto)
    actualizar_estado_boton_guardar_config()

    def actualizar_minimizar_bandeja(*args):
        cfg.minimizar_a_bandeja_al_cerrar = var_minimizar_bandeja.get()
        guardar_configuracion()

    var_minimizar_bandeja.trace("w", actualizar_minimizar_bandeja)
    chk_minimizar_bandeja = ttk.Checkbutton(
        frame_ajustes_config,
        text="Minimizar a bandeja al cerrar",
        variable=var_minimizar_bandeja,
        bootstyle="round-toggle",
    )
    chk_minimizar_bandeja.pack(anchor="w", padx=8, pady=(0, 8))

    def restaurar_configuracion_guardada_por_defecto():

        confirmar = messagebox.askyesno(
            "Restaurar configuración",
            "Se reiniciará toda la configuración guardada a valores por defecto.\n\n¿Deseas continuar?",
            parent=ventana,
        )
        if not confirmar:
            return

        cfg.clicks_por_ciclo = 6
        cfg.intervalo = 0.015
        cfg.tecla_toggle = HOTKEY_TOGGLE_POR_DEFECTO
        cfg.tecla_emergencia = HOTKEY_EMERGENCIA_POR_DEFECTO
        _sync_config_to_globals()
        cfg.boton_mouse = "izquierdo"
        cfg.aplicado_auto = False
        cfg.mostrar_logs = True
        cfg.guardar_automaticamente_cambios = True
        cfg.minimizar_a_bandeja_al_cerrar = False
        cfg.jitter_aleatorio_activo = False
        cfg.variacion_max_ms = 4

        var_mostrar_logs.set(cfg.mostrar_logs)
        var_guardado_auto.set(cfg.guardar_automaticamente_cambios)
        var_minimizar_bandeja.set(cfg.minimizar_a_bandeja_al_cerrar)

        slider_clics.set(cfg.clicks_por_ciclo)
        slider_intervalo.set(int(cfg.intervalo * 1000))
        slider_variacion.set(cfg.variacion_max_ms)
        var_jitter_aleatorio.set(cfg.jitter_aleatorio_activo)
        combo_boton.set("Izquierdo" if cfg.boton_mouse == "izquierdo" else "Derecho")
        var_aplicado_auto.set(cfg.aplicado_auto)

        label_tecla.config(text=f"[ {texto_hotkey(cfg.tecla_toggle)} ]", fg="#8D85EE", bg="#242A38")
        label_emergencia.config(text=f"[ {texto_hotkey(cfg.tecla_emergencia)} ]", fg="#ECA2B0", bg="#2E2228")

        actualizar_etiquetas()
        actualizar_estado_jitter()
        actualizar_estado_boton_aplicar()
        aplicar_configuracion()
        guardar_configuracion(forzado=True)
        messagebox.showinfo("Configuración restaurada", "Se restauraron los valores por defecto.", parent=ventana)

    btn_restaurar_defaults = ttk.Button(
        frame_ajustes_config,
        text="Restaurar configuración",
        command=restaurar_configuracion_guardada_por_defecto,
        style="RojoSuaveAccion.TButton",
        width=30,
    )
    btn_restaurar_defaults.pack(anchor="w", padx=8, pady=(0, 8))

    chk_minimizar_bandeja.pack_forget()
    chk_minimizar_bandeja.pack(anchor="w", padx=8, pady=(2, 8))

    # Botón para limpiar logs
    def limpiar_logs():
        texto_logs.configure(state="normal")
        texto_logs.delete("1.0", "end")
        texto_logs.configure(state="disabled")

    btn_limpiar_logs = ttk.Button(
        frame_ajustes_logs,
        text="Limpiar logs",
        command=limpiar_logs,
        style="MoradoAccion.TButton",
        width=12,
    )
    btn_limpiar_logs.pack(anchor="w", padx=8, pady=(0, 10))

    texto_logs = tkinter.Text(
        frame_ajustes_logs,
        height=5,
        wrap="word",
        bg="#111827",
        fg="#D1D5DB",
        insertbackground="#FFFFFF",
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground="#303745",
    )
    texto_logs.pack(fill="x", pady=(8, 0))
    texto_logs.configure(state="disabled")

    # Tooltips para los ajustes
    tooltips_ajustes_pendientes = [
        (chk_mostrar_logs, "Muestra mensajes de depuración detallados de todas las operaciones.\n\nÚtil para resolver problemas, desactívalo si prefieres una interfaz limpia."),
        (chk_guardado_auto, "Si está activado, los cambios se guardan automáticamente en el archivo de configuración.\n\nSi lo desactivas, solo se guardarán al usar acciones forzadas como restaurar por defecto."),
        (btn_guardar_config, "Guarda manualmente la configuración actual cuando el guardado automático está desactivado."),
        (chk_minimizar_bandeja, "Cuando está activado, al cerrar la ventana se minimizará a la bandeja del sistema en lugar de salir."),
        (btn_limpiar_logs, "Vacia el registro."),
        (btn_restaurar_defaults, "Restaura toda la configuración guardada a los valores por defecto recomendados."),
    ]

    # --- Estado ---
    frame_estado = crear_labelframe(tab_clicker, text="Estado")
    frame_estado.pack(fill="x", pady=(0, 10))
    panel_estado = tkinter.Frame(frame_estado,
                                  bg="#1D2730",
                                  height=98,
                                  padx=10,
                                  pady=6,
                                  relief="flat",
                                  highlightthickness=0,
                                  bd=0)
    panel_estado.pack(fill="x", padx=6, pady=6)
    panel_estado.pack_propagate(False)

    estado_contenido = tkinter.Frame(panel_estado,
                                     bg="#1D2730",
                                     relief="flat",
                                     highlightthickness=0,
                                     bd=0)
    estado_contenido.pack(expand=True)

    label_estado = tkinter.Label(estado_contenido,
                                  text="PAUSADO",
                                  font=("Segoe UI", 18, "bold"),
                                  bg="#1D2730", fg="#9CA3AF")
    label_estado.pack(anchor="center", pady=(0, 6))

    btn_toggle_estado = ttk.Button(estado_contenido,
                                    text="▶ INICIAR",
                                    style="BotonEstadoGrandeVerde.TButton",
                                    width=20)
    btn_toggle_estado.pack(anchor="center", padx=18, ipady=7)
    boton_estado_hover = False
    boton_estado_pressed = False

    # --- Velocidad ---
    frame_rendimiento = crear_labelframe(tab_clicker, text="Velocidad")
    frame_rendimiento.pack(fill="x", pady=(0, 10))

    PRESETS = {
        "Suave / Seguro": {
            "clicks": 5,
            "intervalo_ms": 15,
            "tooltip": (
                "Uso recomendado: anti-cheat fuerte o PC poco potente.\n"
                "Bajo impacto en CPU y mínimo riesgo de lag/detección."
            ),
        },
        "Óptimo / Recomendado": {
            "clicks": 8,
            "intervalo_ms": 9,
            "tooltip": (
                "Uso recomendado: PC decente, la mayoría de juegos.\n"
                "Equilibrado, velocidad vs rendimiento."
            ),
        },
        "Agresivo / Máximo": {
            "clicks": 15,
            "intervalo_ms": 1,
            "tooltip": (
                "Uso recomendado: idle games o clickers extremos.\n"
                "Alta velocidad, pero puede causar lag en algunos juegos."
            ),
        },
    }
    preset_actual = tkinter.StringVar(value="Óptimo / Recomendado")

    def vincular_tooltip(widget, texto):
        def mostrar_tooltip(event):
            if getattr(widget, "_tooltip", None):
                return
            tooltip = tkinter.Toplevel(ventana)
            tooltip.wm_overrideredirect(True)
            tooltip.configure(bg="#151A22")
            x = event.x_root + 10
            y = event.y_root + 10
            tooltip.geometry(f"+{x}+{y}")
            tkinter.Label(
                tooltip,
                text=texto,
                font=("Segoe UI", 8),
                bg="#151A22",
                fg="#A5ADBC",
                justify="left",
                padx=8,
                pady=6,
            ).pack()
            widget._tooltip = tooltip

        def ocultar_tooltip(_event):
            tooltip = getattr(widget, "_tooltip", None)
            if tooltip:
                tooltip.destroy()
                widget._tooltip = None

        widget._tooltip = None
        widget.bind("<Enter>", mostrar_tooltip)
        widget.bind("<Leave>", ocultar_tooltip)

    def aplicar_preset(nombre_preset):
        config = PRESETS[nombre_preset]
        preset_actual.set(nombre_preset)

        slider_clics.set(config["clicks"])
        slider_intervalo.set(config["intervalo_ms"])
        actualizar_etiquetas()
        aplicar_si_auto()
        ventana.update_idletasks()

    frame_preset_rend = ttk.Frame(frame_rendimiento, padding=(6, 6, 6, 0))
    frame_preset_rend.pack(fill="x", pady=(0, 5))

    ttk.Label(frame_preset_rend,
              text="⚡  Presets",
              font=("Segoe UI", 9, "bold"),
              bootstyle="warning").pack(side="left")

    frame_botones_preset = ttk.Frame(frame_preset_rend)
    frame_botones_preset.pack(side="right")

    btn_preset_suave = ttk.Button(
        frame_botones_preset,
        text="Suave",
        width=8,
        style="PresetSuave.TButton",
        command=lambda: aplicar_preset("Suave / Seguro"),
    )
    btn_preset_suave.pack(side="left", padx=(0, 4))

    btn_preset_optima = ttk.Button(
        frame_botones_preset,
        text="Óptima",
        width=8,
        style="PresetOptima.TButton",
        command=lambda: aplicar_preset("Óptimo / Recomendado"),
    )
    btn_preset_optima.pack(side="left", padx=(0, 4))

    btn_preset_agresiva = ttk.Button(
        frame_botones_preset,
        text="Agresivo",
        width=8,
        style="PresetMaximo.TButton",
        command=lambda: aplicar_preset("Agresivo / Máximo"),
    )
    btn_preset_agresiva.pack(side="left")

    vincular_tooltip(btn_preset_suave, PRESETS["Suave / Seguro"]["tooltip"])
    vincular_tooltip(btn_preset_optima, PRESETS["Óptimo / Recomendado"]["tooltip"])
    vincular_tooltip(btn_preset_agresiva, PRESETS["Agresivo / Máximo"]["tooltip"])

    for widget, texto_tooltip in tooltips_ajustes_pendientes:
        vincular_tooltip(widget, texto_tooltip)

    frame_sliders = ttk.Frame(frame_rendimiento, padding=(6, 0, 6, 0))
    frame_sliders.pack(fill="x")
    frame_sliders.grid_columnconfigure(0, weight=1)
    frame_sliders.grid_columnconfigure(1, weight=1)

    card_clics = ttk.Frame(frame_sliders)
    card_intervalo = ttk.Frame(frame_sliders)

    ttk.Label(card_clics,
              text="Clics por ciclo",
              font=("Segoe UI", 9)).pack(anchor="w")

    frame_clics = tkinter.Frame(card_clics,
                                bg="#262B36",
                                relief="flat",
                                bd=0,
                                highlightthickness=0,
                                highlightbackground="#3B4252",
                                highlightcolor="#3B4252")
    frame_clics.pack(fill="x", pady=(2, 4), ipady=4, ipadx=4)
    frame_clics.grid_columnconfigure(0, weight=1)

    slider_knob_base = "#534AB7"
    slider_knob_activo = "#7C6EE8"

    def crear_slider(parent, minimo, maximo, pasos):
        if ctk is not None:
            return ctk.CTkSlider(
                parent,
                from_=minimo,
                to=maximo,
                number_of_steps=pasos,
                width=120,
                height=16,
                fg_color="#313847",
                progress_color="#6A5AE0",
                button_color=slider_knob_base,
                button_hover_color="#6A5AE0",
                border_width=0,
            )
        return ttk.Scale(parent, from_=minimo, to=maximo, orient="horizontal")

    slider_clics = crear_slider(frame_clics, 1, 20, 19)
    slider_clics.set(clicks_por_ciclo)
    slider_clics.grid(row=0, column=0, sticky="ew", padx=(8, 4))

    label_clics_val = ttk.Label(frame_clics,
                                text=str(clicks_por_ciclo),
                                font=("Segoe UI", 11, "bold"),
                                width=4,
                                anchor="e")
    label_clics_val.grid(row=0, column=1, padx=(4, 8))

    titulo_intervalo = ttk.Frame(card_intervalo)
    titulo_intervalo.pack(fill="x")

    ttk.Label(titulo_intervalo,
              text="Intervalo (ms)",
              font=("Segoe UI", 9)).pack(side="left", anchor="w")

    frame_intervalo = tkinter.Frame(card_intervalo,
                                    bg="#262B36",
                                    relief="flat",
                                    bd=0,
                                    highlightthickness=0,
                                    highlightbackground="#3B4252",
                                    highlightcolor="#3B4252")
    frame_intervalo.pack(fill="x", pady=(2, 4), ipady=4, ipadx=4)
    frame_intervalo.grid_columnconfigure(0, weight=1)

    slider_intervalo = crear_slider(frame_intervalo, 1, 100, 99)
    slider_intervalo.set(int(intervalo * 1000))
    slider_intervalo.grid(row=0, column=0, sticky="ew", padx=(8, 4))

    label_intervalo_val = ttk.Label(frame_intervalo,
                                    text=f"{int(intervalo * 1000)}ms",
                                    font=("Segoe UI", 11, "bold"),
                                    width=7,
                                    anchor="e")
    label_intervalo_val.grid(row=0, column=1, padx=(4, 8))

    frame_jitter = ttk.Frame(frame_rendimiento, padding=(6, 0, 6, 0))
    frame_jitter.pack(fill="x", pady=(6, 0))

    var_jitter_aleatorio = tkinter.BooleanVar(value=jitter_aleatorio_activo)
    var_variacion_max_ms = tkinter.IntVar(value=variacion_max_ms)
    var_jitter_info = tkinter.StringVar(value="")

    chk_jitter = ttk.Checkbutton(
        frame_jitter,
        text="Añadir jitter aleatorio (anti-detección)",
        variable=var_jitter_aleatorio,
        bootstyle="round-toggle",
    )
    chk_jitter.pack(anchor="w")

    ttk.Label(
        frame_jitter,
        text="Variación máxima (ms)",
        font=("Segoe UI", 9),
    ).pack(anchor="w", pady=(6, 0))

    frame_variacion = tkinter.Frame(
        frame_jitter,
        bg="#262B36",
        relief="flat",
        bd=0,
        highlightthickness=0,
        highlightbackground="#3B4252",
        highlightcolor="#3B4252",
    )
    frame_variacion.pack(fill="x", pady=(2, 2), ipady=4, ipadx=4)
    frame_variacion.grid_columnconfigure(0, weight=1)

    slider_variacion = crear_slider(frame_variacion, 0, 12, 12)
    slider_variacion.set(variacion_max_ms)
    slider_variacion.grid(row=0, column=0, sticky="ew", padx=(8, 4))

    label_variacion_val = ttk.Label(
        frame_variacion,
        text=f"{variacion_max_ms}ms",
        font=("Segoe UI", 11, "bold"),
        width=7,
        anchor="e",
    )
    label_variacion_val.grid(row=0, column=1, padx=(4, 8))

    label_jitter_info = ttk.Label(
        frame_jitter,
        textvariable=var_jitter_info,
        font=("Segoe UI", 8),
        bootstyle="secondary",
        wraplength=620,
        justify="left",
    )
    label_jitter_info.pack(anchor="w", pady=(4, 0), padx=2)

    def actualizar_estado_jitter(*args):
        global jitter_aleatorio_activo, variacion_max_ms
        jitter_aleatorio_activo = bool(var_jitter_aleatorio.get())
        variacion_max_ms = int(round(float(slider_variacion.get())))
        variacion_max_ms = max(0, min(12, variacion_max_ms))
        try:
            slider_variacion.set(variacion_max_ms)
        except Exception:
            pass

        estado_widget = "disabled" if jitter_aleatorio_activo else "normal"
        for widget in (slider_clics, slider_intervalo):
            try:
                widget.configure(state=estado_widget)
            except Exception:
                pass

        if ctk is not None:
            color_boton_base = "#4E5566" if jitter_aleatorio_activo else slider_knob_base
            for widget in (slider_clics, slider_intervalo):
                try:
                    widget.configure(button_color=color_boton_base)
                except Exception:
                    pass
            try:
                slider_variacion.configure(button_color=slider_knob_base)
            except Exception:
                pass

        label_clics_val.configure(foreground="#A5ADBC" if jitter_aleatorio_activo else "#FFFFFF")
        label_intervalo_val.configure(foreground="#A5ADBC" if jitter_aleatorio_activo else "#FFFFFF")
        label_variacion_val.configure(text=f"{variacion_max_ms}ms")
        var_jitter_info.set(
            "El jitter aleatorio está activo. La velocidad base se ajusta automáticamente."
            if jitter_aleatorio_activo
            else ""
        )
        guardar_configuracion()

    def actualizar_variacion(*args):
        global variacion_max_ms
        variacion_max_ms = int(round(float(slider_variacion.get())))
        variacion_max_ms = max(0, min(12, variacion_max_ms))
        try:
            slider_variacion.set(variacion_max_ms)
        except Exception:
            pass
        label_variacion_val.config(text=f"{variacion_max_ms}ms")
        guardar_configuracion()

    chk_jitter.configure(command=actualizar_estado_jitter)
    slider_variacion.configure(command=lambda _: actualizar_variacion())
    vincular_tooltip(
        chk_jitter,
        "Añade una pequeña variación aleatoria en el tiempo entre clicks.\n"
        "Esto hace que los clicks sean menos predecibles y ayuda a evitar detección por sistemas anti-cheat.\n"
        "Recomendado: 3-6 ms para la mayoría de juegos. (No es efectivo para todos los juegos.)",
    )
    actualizar_estado_jitter()

    frame_info_cps = ttk.Frame(frame_rendimiento, padding=(6, 0, 6, 0))
    frame_info_cps.pack(fill="x", pady=(2, 4))

    label_cps = ttk.Label(frame_info_cps,
                          text="≈ 0 CPS estimados",
                          font=("Segoe UI", 10, "bold"),
                          bootstyle="warning")
    label_cps.grid(row=0, column=0, sticky="w", padx=(0, 6))

    label_info_cps = ttk.Label(frame_info_cps,
                               text="ⓘ Aviso",
                               font=("Segoe UI", 9, "bold"),
                               bootstyle="light")
    label_info_cps.grid(row=0, column=1, sticky="w")
    vincular_tooltip(
        label_info_cps,
        "Velocidades muy altas pueden generar lag.\n"
        "Reduce la velocidad si notas baja de FPS\n"
        "al tener activo el autoclicker.",
    )

    var_aplicado_auto = tkinter.BooleanVar(value=aplicado_auto)
    chk_aplicado_auto = ttk.Checkbutton(
        frame_rendimiento,
        text="Aplicar cambios de velocidad automáticamente",
        variable=var_aplicado_auto,
        bootstyle="round-toggle")
    chk_aplicado_auto.pack(anchor="w", pady=(0, 2), padx=6)

    def obtener_estilo_cps(cps_estimado):
        if cps_estimado <= 600:
            return "CpsSuave.TLabel"
        if cps_estimado <= 13000:
            return "CpsOptimo.TLabel"
        return "CpsAgresivo.TLabel"

    def valor_entero_slider(widget, minimo, maximo):
        valor = int(round(float(widget.get())))
        valor = max(minimo, min(maximo, valor))
        if abs(float(widget.get()) - valor) > 0.001:
            widget.set(valor)
        return valor

    def actualizar_etiquetas(*args):
        clicks_actuales = valor_entero_slider(slider_clics, 1, 20)
        intervalo_ms = valor_entero_slider(slider_intervalo, 1, 100)
        cps_estimado = int(clicks_actuales / (intervalo_ms / 1000))
        estilo_cps = obtener_estilo_cps(cps_estimado)

        label_clics_val.config(text=str(clicks_actuales))
        label_intervalo_val.config(text=f"{intervalo_ms}ms")
        label_cps.config(text=f"≈ {cps_estimado} CPS estimados")
        label_cps.configure(style=estilo_cps)

    def on_slider_press(event):
        if event.widget == slider_clics:
            if ctk is not None:
                slider_clics.configure(button_color=slider_knob_activo)
            frame_clics.config(highlightbackground="#7C6EE8", highlightcolor="#7C6EE8")
        elif event.widget == slider_intervalo:
            if ctk is not None:
                slider_intervalo.configure(button_color=slider_knob_activo)
            frame_intervalo.config(highlightbackground="#7C6EE8", highlightcolor="#7C6EE8")

    def on_slider_release(event):
        if event.widget == slider_clics:
            if ctk is not None:
                slider_clics.configure(button_color=slider_knob_base)
            frame_clics.config(highlightbackground="#3B4252", highlightcolor="#3B4252")
        elif event.widget == slider_intervalo:
            if ctk is not None:
                slider_intervalo.configure(button_color=slider_knob_base)
            frame_intervalo.config(highlightbackground="#3B4252", highlightcolor="#3B4252")

    slider_variacion.bind("<ButtonPress-1>", on_slider_press)
    slider_variacion.bind("<ButtonRelease-1>", on_slider_release)

    card_clics.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 2))
    card_intervalo.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=(0, 2))

    slider_clics.bind("<ButtonPress-1>", on_slider_press)
    slider_clics.bind("<ButtonRelease-1>", on_slider_release)
    slider_intervalo.bind("<ButtonPress-1>", on_slider_press)
    slider_intervalo.bind("<ButtonRelease-1>", on_slider_release)
    actualizar_etiquetas()

    # --- Controles ---
    frame_controles = crear_labelframe(tab_clicker, text="Controles")
    frame_controles.pack(fill="x", pady=(0, 4))
    frame_controles.grid_columnconfigure(0, weight=1)
    frame_controles.grid_columnconfigure(1, weight=1)

    ttk.Label(frame_controles,
              text="Tecla de iniciar/pausar",
              font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=5)

    frame_titulo_emergencia = ttk.Frame(frame_controles)
    frame_titulo_emergencia.grid(row=0, column=1, sticky="w", padx=(8, 0))

    ttk.Label(frame_titulo_emergencia,
              text="Tecla de emergencia",
              font=("Segoe UI", 9)).pack(side="left")

    label_info_emergencia = ttk.Label(frame_titulo_emergencia,
                                      text=" ⓘ",
                                      font=("Segoe UI", 9, "bold"),
                                      bootstyle="None",
                                      cursor="hand2")
    label_info_emergencia.pack(side="left", padx=(4, 0))
    vincular_tooltip(
        label_info_emergencia,
        "Usa esta tecla para cerrar el programa de forma inmediata\n"
        "si surge un problema con la tecla de activar o pausar\n"
        "y no puedes detener el autoclicker normalmente.\n" \
        "Esto cierra todo el programa incluso si el autoclicker no esta activo, por lo que es útil como medida de seguridad adicional.",
    )

    frame_tecla = ttk.Frame(frame_controles)
    frame_tecla.grid(row=1, column=0, sticky="ew", pady=(3, 6))

    label_tecla = tkinter.Label(frame_tecla,
                                text=f"[ {texto_hotkey(cfg.tecla_toggle)} ]",
                                font=("Segoe UI", 12, "bold"),
                                bg="#242A38", fg="#8D85EE",
                                relief="flat", bd=0,
                                padx=10, pady=5,
                                cursor="hand2")
    label_tecla.pack(side="left")

    frame_emergencia = ttk.Frame(frame_controles)
    frame_emergencia.grid(row=1, column=1, sticky="ew", pady=(3, 6), padx=(8, 0))

    label_emergencia = tkinter.Label(frame_emergencia,
                                     text=f"[ {texto_hotkey(cfg.tecla_emergencia)} ]",
                                     font=("Segoe UI", 12, "bold"),
                                     bg="#2E2228", fg="#ECA2B0",
                                     relief="flat", bd=0,
                                     padx=10, pady=5,
                                     cursor="hand2")
    label_emergencia.pack(side="left")

    ttk.Label(frame_controles,
              text="Botón de clic",
              font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", padx=5)

    combo_boton = ttk.Combobox(frame_controles,
                               state="readonly",
                               values=["Izquierdo", "Derecho"],
                               width=14)
    combo_boton.grid(row=3, column=0, sticky="w", pady=(2, 0), padx=5)
    combo_boton.set("Derecho" if cfg.boton_mouse == "derecho" else "Izquierdo")

    ttk.Label(frame_controles,
              text="Haz clic en cada tecla para cambiarla",
              font=("Segoe UI", 8),
              bootstyle="secondary").grid(row=4, column=0, columnspan=2,
                                           sticky="w", pady=(3, 0), padx=5)

    # --- Botones Aplicar / Restaurar ---
    frame_botones = ttk.Frame(tab_clicker)
    frame_botones.pack(fill="x", pady=(8, 0))

    ttk.Label(barra_inferior,
              text="By: Lomwit",
              font=("Segoe UI", 8),
              bootstyle="secondary").pack(anchor="w", pady=(0, 2))

    def refrescar_estilo_boton_estado():
        if activo:
            if boton_estado_pressed:
                estilo_boton = "BotonEstadoGrandeRojoPress.TButton"
            elif boton_estado_hover:
                estilo_boton = "BotonEstadoGrandeRojoHover.TButton"
            else:
                estilo_boton = "BotonEstadoGrandeRojo.TButton"
        else:
            if boton_estado_pressed:
                estilo_boton = "BotonEstadoGrandeVerdePress.TButton"
            elif boton_estado_hover:
                estilo_boton = "BotonEstadoGrandeVerdeHover.TButton"
            else:
                estilo_boton = "BotonEstadoGrandeVerde.TButton"
        btn_toggle_estado.config(style=estilo_boton)

    def animar_activacion_boton(paso=0):
        secuencia = [
            "BotonEstadoGrandeRojoHover.TButton",
            "BotonEstadoGrandeRojo.TButton",
            "BotonEstadoGrandeRojoHover.TButton",
            "BotonEstadoGrandeRojo.TButton",
        ]
        if not activo or boton_estado_pressed:
            refrescar_estilo_boton_estado()
            return
        if paso >= len(secuencia):
            refrescar_estilo_boton_estado()
            return
        if not boton_estado_hover:
            btn_toggle_estado.config(style=secuencia[paso])
        ventana.after(70, lambda: animar_activacion_boton(paso + 1))

    def on_boton_estado_enter(event):
        nonlocal boton_estado_hover
        boton_estado_hover = True
        refrescar_estilo_boton_estado()

    def on_boton_estado_leave(event):
        nonlocal boton_estado_hover, boton_estado_pressed
        boton_estado_hover = False
        boton_estado_pressed = False
        refrescar_estilo_boton_estado()

    def on_boton_estado_press(event):
        nonlocal boton_estado_pressed
        boton_estado_pressed = True
        refrescar_estilo_boton_estado()

    def on_boton_estado_release(event):
        nonlocal boton_estado_hover, boton_estado_pressed
        widget_bajo_cursor = ventana.winfo_containing(event.x_root, event.y_root)
        boton_estado_hover = widget_bajo_cursor == btn_toggle_estado
        boton_estado_pressed = False
        refrescar_estilo_boton_estado()

    def actualizar_estado_visual(animar=False):
        if activo:
            panel_estado.config(bg="#253129")
            estado_contenido.config(bg="#253129")
            label_estado.config(text="CORRIENDO", fg="#7AE39D", bg="#253129")
            btn_toggle_estado.config(text="⏸ PAUSAR")
        else:
            panel_estado.config(bg="#1D2730")
            estado_contenido.config(bg="#1D2730")
            label_estado.config(text="PAUSADO", fg="#9CA3AF", bg="#1D2730")
            btn_toggle_estado.config(text="▶ INICIAR")
        refrescar_estilo_boton_estado()
        actualizar_icono_ventana()
        actualizar_icono_bandeja()
        if animar and activo:
            animar_activacion_boton()

    def actualizar_icono_bandeja():
        global icono_bandeja
        if not bandeja_disponible():
            return
        with bloqueo_icono_bandeja:
            if icono_bandeja is None:
                return
            icono_bandeja.icon = crear_icono_bandeja(activo)
            icono_bandeja.title = "AstroClicker - CORRIENDO" if activo else "AstroClicker - PAUSADO"

    def _establecer_estado_ui(nuevo_estado, animar=False):
        global activo
        activo = bool(nuevo_estado)
        if activo:
            evento_activo.set()
        else:
            evento_activo.clear()
        actualizar_estado_visual(animar=animar)

    registrar_establecer_estado(_establecer_estado_ui)

    def alternar_estado_desde_boton():
        establecer_estado(not activo, animar=True)

    def mostrar_ventana_principal():
        if not ventana.winfo_exists():
            return
        ventana.deiconify()
        ventana.lift()
        ventana.focus_force()

    def mostrar_desde_bandeja(icono, item):
        ventana.after(0, mostrar_ventana_principal)

    def salir_desde_bandeja(icono, item):
        ventana.after(0, lambda: al_cerrar(forzar_salida=True))

    def avisar_bandeja_no_disponible(detalle):
        if not ventana.winfo_exists():
            return
        try:
            ventana.attributes("-topmost", True)
            messagebox.showwarning(
                "Bandeja no disponible",
                "No se pudo iniciar el icono de la bandeja del sistema.\n"
                "La app seguirá funcionando sin bandeja.\n\n"
                f"Detalle: {detalle}",
                parent=ventana,
            )
        finally:
            ventana.attributes("-topmost", False)

    def iniciar_icono_bandeja_worker():
        global icono_bandeja
        if not bandeja_disponible():
            return False, "Falta instalar pystray o Pillow en este entorno."

        try:
            menu = pystray.Menu(
                pystray.MenuItem("Abrir AstroClicker", mostrar_desde_bandeja),
                pystray.MenuItem("Cerrar AstroClicker", salir_desde_bandeja),
            )

            icono = pystray.Icon(
                "astroclicker_app",
                crear_icono_bandeja(activo),
                "AstroClicker - PAUSADO",
                menu,
            )
            with bloqueo_icono_bandeja:
                icono_bandeja = icono

            evento_inicio = threading.Event()
            error_hilo = []

            def setup_icono(icono_listo):
                evento_inicio.set()

            def ejecutar_icono():
                try:
                    icono.run(setup=setup_icono)
                except Exception as exc:
                    error_hilo.append(exc)
                    evento_inicio.set()

            inicio_detached = False
            try:
                icono.run_detached(setup=setup_icono)
                inicio_detached = True
            except Exception:
                inicio_detached = False

            if not inicio_detached:
                hilo_icono = threading.Thread(target=ejecutar_icono, daemon=True)
                hilo_icono.start()

            if not evento_inicio.wait(timeout=3.0):
                try:
                    icono.stop()
                except Exception:
                    pass
                with bloqueo_icono_bandeja:
                    icono_bandeja = None
                if inicio_detached:
                    return False, "Timeout al registrar el icono en Windows (modo detached, 3s)."
                else:
                    return False, "Timeout al registrar el icono en Windows (modo hilo, 3s)."

            if error_hilo:
                with bloqueo_icono_bandeja:
                    icono_bandeja = None
                raise RuntimeError(str(error_hilo[0]))

            try:
                icono.visible = True
            except Exception:
                pass

            visible_confirmado = False
            for _ in range(12):
                if bool(getattr(icono, "visible", False)):
                    visible_confirmado = True
                    break
                time.sleep(0.15)

            if not visible_confirmado:
                with bloqueo_icono_bandeja:
                    icono_bandeja = None
                return False, "pystray inició, pero Windows no confirmó el icono como visible."

            return True, ""
        except Exception as exc:
            with bloqueo_icono_bandeja:
                icono_bandeja = None
            return False, str(exc)

    def iniciar_icono_bandeja():
        if not bandeja_disponible():
            avisar_bandeja_no_disponible("Falta instalar pystray o Pillow en este entorno.")
            return

        def trabajo_inicio_bandeja():
            ok, detalle = iniciar_icono_bandeja_worker()
            if not ok:
                try:
                    ventana.after(0, lambda: avisar_bandeja_no_disponible(detalle))
                except Exception:
                    pass

        threading.Thread(target=trabajo_inicio_bandeja, daemon=True).start()

    def aplicar_configuracion(*args):
        global clicks_por_ciclo, intervalo, boton_mouse, aplicado_auto
        global jitter_aleatorio_activo, variacion_max_ms
        clicks_por_ciclo = valor_entero_slider(slider_clics, 1, 20)
        intervalo        = valor_entero_slider(slider_intervalo, 1, 100) / 1000
        boton_mouse      = "derecho" if combo_boton.get() == "Derecho" else "izquierdo"
        aplicado_auto    = bool(var_aplicado_auto.get())
        jitter_aleatorio_activo = bool(var_jitter_aleatorio.get())
        variacion_max_ms = valor_entero_slider(slider_variacion, 0, 12)
        actualizar_estado_jitter()

    def aplicar_si_auto(*args):
        if var_aplicado_auto.get():
            aplicar_configuracion()

    def actualizar_estado_boton_aplicar(*args):
        if var_aplicado_auto.get():
            btn_aplicar.configure(state="disabled")
        else:
            btn_aplicar.configure(state="normal")

    def restaurar_configuracion():
        slider_clics.set(5)
        slider_intervalo.set(1)
        slider_variacion.set(4)
        var_jitter_aleatorio.set(False)
        combo_boton.set("Izquierdo")
        actualizar_etiquetas()
        actualizar_estado_jitter()
        aplicar_configuracion()

    btn_aplicar = ttk.Button(frame_botones,
                             text="Aplicar",
                             command=aplicar_configuracion,
                             style="MoradoAccion.TButton",
                             width=16)
    btn_aplicar.pack(side="left", expand=True, fill="x", padx=(0, 6), ipady=6)

    ttk.Button(frame_botones,
               text="Restaurar",
               command=restaurar_configuracion,
               style="RojoSuaveAccion.TButton",
               width=16).pack(side="left", expand=True, fill="x", ipady=6)

    btn_toggle_estado.config(command=alternar_estado_desde_boton)
    btn_toggle_estado.bind("<Enter>", on_boton_estado_enter)
    btn_toggle_estado.bind("<Leave>", on_boton_estado_leave)
    btn_toggle_estado.bind("<ButtonPress-1>", on_boton_estado_press)
    btn_toggle_estado.bind("<ButtonRelease-1>", on_boton_estado_release)
    actualizar_estado_visual()

    combo_boton.bind("<<ComboboxSelected>>", aplicar_si_auto)
    var_aplicado_auto.trace_add("write", aplicar_configuracion)
    var_aplicado_auto.trace_add("write", actualizar_estado_boton_aplicar)
    actualizar_estado_boton_aplicar()

    def actualizar_y_aplicar(*args):
        actualizar_etiquetas()
        aplicar_si_auto()
        try:
            actualizar_teorico_ref()
        except Exception:
            pass

    slider_clics.configure(command=lambda _: actualizar_y_aplicar())
    slider_intervalo.configure(command=lambda _: actualizar_y_aplicar())

    # --- PESTAÑA TEST DE CPS ---
    duracion_test_var = tkinter.IntVar(value=5)
    var_progreso_test = tkinter.DoubleVar(value=0.0)
    
    test_activo = False
    test_clicks_contados = [0]
    test_stop_event = threading.Event()
    test_finished_event = threading.Event()
    test_inicio_time = 0.0
    ultimo_clicks_flash = 0
    blanco_flasheando = False
    clics_manuales = []

    def bucle_test_clicker(duracion, clicks_por_ciclo_test, intervalo_test, jitter_activo, jitter_variacion_ms, counter_list, stop_event, finished_event):
        inicio = time.perf_counter()
        limite = inicio + duracion
        proximo_tick = time.perf_counter()
        
        while not stop_event.is_set():
            ahora = time.perf_counter()
            if ahora >= limite:
                break
                
            clicks_actuales = clicks_por_ciclo_test
            intervalo_actual = max(intervalo_test, 0.001)
            
            if jitter_activo:
                base_por_click = max(0.001, intervalo_actual / max(clicks_actuales, 1))
                for _ in range(clicks_actuales):
                    if stop_event.is_set() or time.perf_counter() >= limite:
                        break
                    counter_list[0] += 1
                    variacion_actual = random.uniform(-jitter_variacion_ms, jitter_variacion_ms) / 1000
                    espera_click = max(0.001, base_por_click + variacion_actual)
                    time.sleep(espera_click)
                proximo_tick = time.perf_counter()
            else:
                for i in range(clicks_actuales):
                    if stop_event.is_set() or time.perf_counter() >= limite:
                        break
                    counter_list[0] += 1
                    if i < clicks_actuales - 1:
                        time.sleep(0)
                
                proximo_tick += intervalo_actual
                espera = proximo_tick - time.perf_counter()
                if espera > 0:
                    time.sleep(espera)
                else:
                    proximo_tick = time.perf_counter()
                    
        finished_event.set()

    def flashear_blanco():
        nonlocal blanco_flasheando
        if blanco_flasheando:
            return
        blanco_flasheando = True
        label_blanco_test.config(bg="#22C55E", fg="#FFFFFF")
        def restaurar_blanco():
            nonlocal blanco_flasheando
            if test_activo:
                label_blanco_test.config(bg="#1E293B", fg="#9CA3AF")
            else:
                label_blanco_test.config(bg="#242A38", fg="#8D85EE")
            blanco_flasheando = False
        ventana.after(40, restaurar_blanco)

    def actualizar_gui_test():
        nonlocal test_activo, test_inicio_time, ultimo_clicks_flash
        if not test_activo:
            return
            
        elapsed = time.perf_counter() - test_inicio_time
        duracion = float(duracion_test_var.get())
        
        if test_finished_event.is_set() or elapsed >= duracion:
            finalizar_test(cancelado=False)
            return
            
        porcentaje = min(100.0, (elapsed / duracion) * 100.0)
        var_progreso_test.set(porcentaje)
        
        clicks_actuales = test_clicks_contados[0]
        cps_actual = clicks_actuales / max(elapsed, 0.01)
        
        lbl_test_clicks.config(text=f"Clics procesados: {clicks_actuales}")
        lbl_test_tiempo.config(text=f"Tiempo transcurrido: {elapsed:.2f}s")
        lbl_test_cps_real.config(text=f"CPS Real: {cps_actual:.1f} CPS")
        
        if clicks_actuales > ultimo_clicks_flash:
            flashear_blanco()
            ultimo_clicks_flash = clicks_actuales
            
        ventana.after(30, actualizar_gui_test)

    def iniciar_test_autoclicker():
        nonlocal test_activo, test_clicks_contados, test_inicio_time, ultimo_clicks_flash
        if test_activo:
            return
            
        clicks_ciclo = valor_entero_slider(slider_clics, 1, 20)
        intervalo_s = valor_entero_slider(slider_intervalo, 1, 100) / 1000
        jitter_act = bool(var_jitter_aleatorio.get())
        jitter_var_ms = valor_entero_slider(slider_variacion, 0, 12)
        
        test_activo = True
        test_clicks_contados[0] = 0
        ultimo_clicks_flash = 0
        test_stop_event.clear()
        test_finished_event.clear()
        
        btn_iniciar_test.configure(state="disabled")
        slider_duracion.configure(state="disabled")
        btn_cancelar_test.configure(state="normal")
        label_blanco_test.config(bg="#1E293B", fg="#9CA3AF", text="\n\nEjecutando test automático...\nClicks locales simulados.")
        
        lbl_test_clicks.config(text="Clics procesados: 0")
        lbl_test_tiempo.config(text="Tiempo transcurrido: 0.00s")
        lbl_test_cps_real.config(text="CPS Real: 0.0 CPS", style="CpsSuave.TLabel")
        lbl_test_eficiencia.config(text="Eficiencia: --%", foreground="#9CA3AF")
        lbl_test_explicacion.config(text="Ejecutando simulación en segundo plano...", bootstyle="info")
        
        test_inicio_time = time.perf_counter()
        duracion_s = float(duracion_test_var.get())
        
        hilo_test = threading.Thread(
            target=bucle_test_clicker,
            args=(duracion_s, clicks_ciclo, intervalo_s, jitter_act, jitter_var_ms, test_clicks_contados, test_stop_event, test_finished_event),
            daemon=True
        )
        hilo_test.start()
        ventana.after(30, actualizar_gui_test)

    def finalizar_test(cancelado=False):
        nonlocal test_activo
        if not test_activo:
            return
            
        test_activo = False
        test_stop_event.set()
        
        btn_iniciar_test.configure(state="normal")
        slider_duracion.configure(state="normal")
        btn_cancelar_test.configure(state="disabled")
        label_blanco_test.config(bg="#242A38", fg="#8D85EE", text="\nHaga clic aquí para medir CPS manual\no inicie el test automático")
        
        var_progreso_test.set(100.0 if not cancelado else 0.0)
        clicks_finales = test_clicks_contados[0]
        tiempo_final = time.perf_counter() - test_inicio_time
        
        if cancelado:
            lbl_test_clicks.config(text=f"Clics procesados: {clicks_finales} (Cancelado)")
            lbl_test_cps_real.config(text="CPS Real: 0.0 CPS", style="CpsSuave.TLabel")
            lbl_test_eficiencia.config(text="Eficiencia: 0.0%", foreground="#F59E0B")
            lbl_test_explicacion.config(text="Prueba cancelada por el usuario.", bootstyle="warning")
            return
            
        cps_real = clicks_finales / max(tiempo_final, 0.01)
        
        clicks_ciclo = valor_entero_slider(slider_clics, 1, 20)
        intervalo_ms = valor_entero_slider(slider_intervalo, 1, 100)
        cps_teorico = clicks_ciclo / (intervalo_ms / 1000)
        
        eficiencia = (cps_real / cps_teorico) * 100.0
        eficiencia_mostrar = min(100.0, eficiencia)
        
        lbl_test_clicks.config(text=f"Clics procesados: {clicks_finales}")
        lbl_test_tiempo.config(text=f"Tiempo transcurrido: {tiempo_final:.2f}s")
        lbl_test_cps_real.config(text=f"CPS Real: {cps_real:.1f} CPS")
        lbl_test_cps_real.configure(style=obtener_estilo_cps(int(cps_real)))
        
        if eficiencia >= 90.0:
            color_ef = "#22C55E"
            msg = "¡Excelente! El clicker se ejecuta a la velocidad esperada sin retrasos en tu sistema."
            boot_st = "success"
        elif eficiencia >= 70.0:
            color_ef = "#3B82F6"
            msg = "Rendimiento aceptable, pero Windows está introduciendo ligeros retrasos en el temporizador."
            boot_st = "info"
        else:
            color_ef = "#EF4444"
            msg = "Rendimiento degradado. Windows no puede mantener la velocidad debido a los límites de sleep de 15ms. Intenta activar Jitter o subir los Clics por Ciclo."
            boot_st = "danger"
            
        lbl_test_eficiencia.config(text=f"Eficiencia: {eficiencia_mostrar:.1f}%", foreground=color_ef)
        lbl_test_explicacion.config(text=msg, bootstyle=boot_st)

    def registrar_clic_manual(event):
        if test_activo:
            return
            
        ahora = time.perf_counter()
        clics_manuales.append(ahora)
        clics_manuales[:] = [t for t in clics_manuales if ahora - t <= 1.0]
        
        total_manuales = len(clics_manuales)
        flashear_blanco()
        
        lbl_test_clicks.config(text=f"Clics manuales en el último segundo: {total_manuales}")
        lbl_test_tiempo.config(text="Prueba: Manual activa")
        lbl_test_cps_real.config(text=f"CPS Manual: {total_manuales} CPS", style="CpsSuave.TLabel")
        
        lbl_test_eficiencia.config(text="")
        lbl_test_explicacion.config(text="Midiendo CPS físico. ¡Haz clic tan rápido como puedas!", bootstyle="secondary")

    # --- DISEÑO DE LA INTERFAZ DE TEST DE CPS ---
    label_titulo_test = tkinter.Label(
        tab_test,
        text="Test de CPS y Rendimiento",
        font=("Segoe UI", 18, "bold"),
        bg="#1E293B",
        fg="#E1E8EF",
        pady=12
    )
    label_titulo_test.pack(fill="x", pady=(0, 10))
    
    lbl_desc_test = ttk.Label(
        tab_test,
        text="Ejecuta una simulación del autoclicker en modo seguro (sin clics a nivel de sistema) o haz clic manualmente para registrar y analizar los CPS en tiempo real.",
        font=("Segoe UI", 9),
        wraplength=600,
        justify="left"
    )
    lbl_desc_test.pack(fill="x", padx=10, pady=(0, 10))
    
    frame_config_test = crear_labelframe(tab_test, text="Configuración del Test")
    frame_config_test.pack(fill="x", pady=(0, 10))
    
    frame_duracion_row = ttk.Frame(frame_config_test, padding=6)
    frame_duracion_row.pack(fill="x")
    
    ttk.Label(frame_duracion_row, text="Duración (segundos):", font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
    
    slider_duracion = crear_slider(frame_duracion_row, 1, 10, 9)
    slider_duracion.set(duracion_test_var.get())
    slider_duracion.pack(side="left", fill="x", expand=True, padx=(0, 8))
    
    lbl_duracion_val = ttk.Label(frame_duracion_row, text="5s", font=("Segoe UI", 11, "bold"), width=4)
    lbl_duracion_val.pack(side="right")
    
    def actualizar_lbl_duracion(*args):
        val = int(round(float(slider_duracion.get())))
        slider_duracion.set(val)
        duracion_test_var.set(val)
        lbl_duracion_val.config(text=f"{val}s")
        
    slider_duracion.configure(command=lambda _: actualizar_lbl_duracion())
    
    lbl_teorico_ref = ttk.Label(
        frame_config_test,
        text="Ajuste actual del clicker: 0 CPS estimados",
        font=("Segoe UI", 9, "bold"),
        bootstyle="warning"
    )
    lbl_teorico_ref.pack(anchor="w", padx=10, pady=(4, 8))
    
    def actualizar_teorico_ref():
        clicks_actuales = valor_entero_slider(slider_clics, 1, 20)
        intervalo_ms = valor_entero_slider(slider_intervalo, 1, 100)
        cps_estimado = int(clicks_actuales / (intervalo_ms / 1000))
        lbl_teorico_ref.config(
            text=f"Ajuste actual en AstroClicker: {clicks_actuales} clics/ciclo a {intervalo_ms}ms (≈ {cps_estimado} CPS teóricos)"
        )
        
    actualizar_teorico_ref()
    
    frame_blanco = crear_labelframe(tab_test, text="Área de Pruebas (Clics Locales)")
    frame_blanco.pack(fill="x", pady=(0, 10))
    
    label_blanco_test = tkinter.Label(
        frame_blanco,
        text="\n\nHaga clic aquí para medir CPS manual\no inicie el test automático",
        font=("Segoe UI", 12, "bold"),
        bg="#242A38", fg="#8D85EE",
        height=5,
        relief="flat", bd=0,
        cursor="hand2"
    )
    label_blanco_test.pack(fill="x", padx=8, pady=8)
    label_blanco_test.bind("<Button-1>", registrar_clic_manual)
    
    frame_controles_test = ttk.Frame(tab_test)
    frame_controles_test.pack(fill="x", pady=(0, 10))
    frame_controles_test.grid_columnconfigure(0, weight=1)
    frame_controles_test.grid_columnconfigure(1, weight=1)
    
    btn_iniciar_test = ttk.Button(
        frame_controles_test,
        text="Iniciar Test Automático",
        command=iniciar_test_autoclicker,
        style="VerdeAccion.TButton"
    )
    btn_iniciar_test.grid(row=0, column=0, sticky="ew", padx=(0, 4), ipady=4)
    
    btn_cancelar_test = ttk.Button(
        frame_controles_test,
        text="Cancelar",
        command=lambda: finalizar_test(cancelado=True),
        style="RojoSuaveAccion.TButton",
        state="disabled"
    )
    btn_cancelar_test.grid(row=0, column=1, sticky="ew", padx=(4, 0), ipady=4)
    
    prog_bar_test = ttk.Progressbar(
        tab_test,
        orient="horizontal",
        mode="determinate",
        variable=var_progreso_test,
        bootstyle="success-striped"
    )
    prog_bar_test.pack(fill="x", pady=(0, 10))
    
    frame_resultados_test = crear_labelframe(tab_test, text="Resultados de la Prueba")
    frame_resultados_test.pack(fill="both", expand=True, pady=(0, 5))
    
    lbl_test_clicks = ttk.Label(frame_resultados_test, text="Clics procesados: 0", font=("Segoe UI", 10))
    lbl_test_clicks.pack(anchor="w", padx=10, pady=(6, 3))
    
    lbl_test_tiempo = ttk.Label(frame_resultados_test, text="Tiempo transcurrido: 0.00s", font=("Segoe UI", 10))
    lbl_test_tiempo.pack(anchor="w", padx=10, pady=3)
    
    lbl_test_cps_real = ttk.Label(frame_resultados_test, text="CPS Real: 0.0 CPS", font=("Segoe UI", 11, "bold"), style="CpsSuave.TLabel")
    lbl_test_cps_real.pack(anchor="w", padx=10, pady=3)
    
    lbl_test_eficiencia = ttk.Label(frame_resultados_test, text="Eficiencia: --%", font=("Segoe UI", 11, "bold"))
    lbl_test_eficiencia.pack(anchor="w", padx=10, pady=3)
    
    lbl_test_explicacion = ttk.Label(
        frame_resultados_test,
        text="Presione 'Iniciar Test Automático' para comenzar la simulación.",
        font=("Segoe UI", 9),
        wraplength=600,
        justify="left",
        bootstyle="secondary"
    )
    lbl_test_explicacion.pack(fill="x", padx=10, pady=(6, 8))


    # --- LISTENER DE TECLADO ---

    def nombre_tecla(tecla):
        try:
            if tecla.char:
                return normalizar_token_hotkey(tecla.char.lower())
        except AttributeError:
            pass
        return normalizar_token_hotkey(str(tecla).replace("Key.", "").lower())

    def combo_actual_con(letra_actual):
        return ordenar_tokens_hotkey(set(teclas_presionadas) | {letra_actual})

    def al_presionar_tecla(tecla):
        nonlocal disparo_toggle_activo, disparo_emergencia_activo
        global esperando_tecla, esperando_emergencia
        letra = nombre_tecla(tecla)
        if not letra:
            return

        teclas_presionadas.add(letra)

        if esperando_tecla:
            combo_capturado = combo_actual_con(letra)
            if letra in MODIFICADORES_HOTKEY:
                ventana.after(0, lambda: label_tecla.config(
                    text=f"[ {' + '.join(texto_tecla(t) for t in combo_capturado)} + ... ]"
                ))
                return

            combo_str = cadena_desde_combo_hotkey(combo_capturado)
            if combo_str == cadena_desde_combo_hotkey(combo_desde_cadena_hotkey(cfg.tecla_emergencia)):
                esperando_tecla = False
                ventana.after(0, lambda: label_tecla.config(
                    text=f"[ {texto_hotkey(cfg.tecla_toggle)} ]",
                    fg="#8D85EE", bg="#242A38"))
                ventana.after(0, lambda: messagebox.showwarning(
                    "Tecla no válida",
                    "La tecla de activación no puede ser igual a la tecla de emergencia.",
                    parent=ventana,
                ))
                return

            cfg.tecla_toggle = combo_str
            esperando_tecla = False
            _sync_config_to_globals()
            ventana.after(0, lambda: label_tecla.config(
                text=f"[ {texto_hotkey(cfg.tecla_toggle)} ]",
                bg="#1a1a2e", fg="#7F77DD"))
            return

        if esperando_emergencia:
            combo_capturado = combo_actual_con(letra)
            if letra in MODIFICADORES_HOTKEY:
                ventana.after(0, lambda: label_emergencia.config(
                    text=f"[ {' + '.join(texto_tecla(t) for t in combo_capturado)} + ... ]"
                ))
                return

            combo_str = cadena_desde_combo_hotkey(combo_capturado)
            if combo_str == cadena_desde_combo_hotkey(combo_desde_cadena_hotkey(cfg.tecla_toggle)):
                esperando_emergencia = False
                ventana.after(0, lambda: label_emergencia.config(
                    text=f"[ {texto_hotkey(cfg.tecla_emergencia)} ]",
                    fg="#ECA2B0", bg="#2E2228"))
                ventana.after(0, lambda: messagebox.showwarning(
                    "Tecla no válida",
                    "La tecla de emergencia no puede ser igual a la tecla de activación.",
                    parent=ventana,
                ))
                return

            cfg.tecla_emergencia = combo_str
            esperando_emergencia = False
            _sync_config_to_globals()
            ventana.after(0, lambda: label_emergencia.config(
                text=f"[ {texto_hotkey(cfg.tecla_emergencia)} ]",
                bg="#2E2228", fg="#ECA2B0"))
            return

        pass

    def al_soltar_tecla(tecla):
        nonlocal disparo_toggle_activo, disparo_emergencia_activo
        letra = nombre_tecla(tecla)
        if letra:
            teclas_presionadas.discard(letra)
        disparo_toggle_activo = False
        disparo_emergencia_activo = False

    def escuchar_nueva_tecla(event):
        global esperando_tecla, esperando_emergencia
        esperando_tecla = True
        esperando_emergencia = False
        label_tecla.config(text="[ ... ]", fg="#D85A30", bg="#242A38")

    def escuchar_nueva_tecla_emergencia(event):
        global esperando_tecla, esperando_emergencia
        esperando_emergencia = True
        esperando_tecla = False
        label_emergencia.config(text="[ ... ]", fg="#D85A30", bg="#2E2228")

    label_tecla.bind("<Button-1>", escuchar_nueva_tecla)
    label_emergencia.bind("<Button-1>", escuchar_nueva_tecla_emergencia)

    listener = kb.Listener(on_press=al_presionar_tecla, on_release=al_soltar_tecla)

    def al_cerrar(forzar_salida=False):
        global corriendo, icono_bandeja
        if not ventana.winfo_exists():
            return

        if minimizar_a_bandeja_al_cerrar and not forzar_salida:
            if bandeja_disponible() and icono_bandeja is None:
                iniciar_icono_bandeja()
            if bandeja_disponible():
                ventana.withdraw()
                return

        liberar_timer_precision()
        aplicar_configuracion()
        guardar_configuracion()
        corriendo = False
        evento_activo.set()
        listener.stop()
        with bloqueo_icono_bandeja:
            icono_local = icono_bandeja
            icono_bandeja = None
        if icono_local is not None:
            try:
                icono_local.visible = False
            except Exception:
                pass
            try:
                icono_local.stop()
            except Exception:
                pass
        ventana.destroy()

    listener.daemon = True
    listener.start()

    tamano_base_tabs = [680, 780]
    minimo_base_tabs = [660, 740]

    # Hilo de sondeo de alta precisión para teclas (GetAsyncKeyState)
    threading.Thread(
        target=bucle_polling_teclas,
        args=(ventana, lambda: al_cerrar(forzar_salida=True)),
        daemon=True
    ).start()

    ventana.protocol("WM_DELETE_WINDOW", al_cerrar)
    ventana.after(450, iniciar_icono_bandeja)
    ventana.mainloop()

# --- ARRANQUE ---
atexit.register(liberar_timer_precision)

try:
    ctypes.windll.winmm.timeBeginPeriod(1)
    timer_precision_activa = True
except Exception:
    timer_precision_activa = False

try:
    # ABOVE_NORMAL_PRIORITY_CLASS
    ctypes.windll.kernel32.SetPriorityClass(-1, 0x00008000)
except Exception:
    pass

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lomwit.AstroClicker")
except Exception:
    pass

cargar_configuracion()

hilo = threading.Thread(target=bucle_clicker, daemon=True)
hilo.start()

crear_interfaz()