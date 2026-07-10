from PIL import Image, ImageDraw


def crear_icono_rayo(esta_activo: bool, tam: int = 64) -> Image.Image:
    imagen = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(imagen)

    color_rayo = (68, 214, 122, 255) if esta_activo else (225, 84, 96, 255)
    color_borde = (255, 255, 255, 230)
    color_brillo = (255, 255, 255, 72)

    dibujo.ellipse(
        (4, 4, tam - 4, tam - 4),
        fill=(30, 36, 45, 240),
        outline=(255, 255, 255, 110),
        width=2,
    )
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


def guardar_ico(nombre_salida: str, esta_activo: bool) -> None:
    icono = crear_icono_rayo(esta_activo=esta_activo, tam=64)
    icono.save(
        nombre_salida,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    guardar_ico("astrotools_paused.ico", esta_activo=False)
    guardar_ico("astrotools_active.ico", esta_activo=True)
    print("Iconos generados: astrotools_paused.ico y astrotools_active.ico")
