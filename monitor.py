"""Monitor en vivo de baja latencia para Sony a6000.

Uso:
    python monitor.py                  # descubre la camara por SSDP
    python monitor.py --endpoint URL   # endpoint conocido (mas rapido)
    python monitor.py --size L         # pide mayor tamano de liveview
    python monitor.py --scale 2        # escala la ventana (por defecto 2x)
    python monitor.py --webcam         # publica el liveview como webcam
    python monitor.py --webcam --no-preview  # webcam sin ventana

Teclas: q o ESC para salir.
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np

from liveview_stream import LiveviewStream
from sony_camera import CameraError, SonyCamera

WINDOW = "Sony a6000 - Monitor"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint", help="URL del endpoint (ej. http://192.168.122.1:8080/sony/camera)")
    p.add_argument("--size", help="Tamano de liveview a pedir (ej. L o M); si falla usa el default")
    p.add_argument("--scale", type=float, default=2.0, help="Factor de escala de la ventana")
    p.add_argument("--no-hud", action="store_true", help="Ocultar overlay de FPS/latencia")
    p.add_argument("--webcam", action="store_true", help="Publicar el liveview en una camara virtual")
    p.add_argument("--no-preview", action="store_true", help="Ocultar la ventana en modo --webcam")
    return p.parse_args()


def draw_hud(img: np.ndarray, fps: float, age_ms: float, dropped: int) -> None:
    text = f"{fps:5.1f} fps | frame age {age_ms:4.0f} ms | dropped {dropped}"
    cv2.putText(img, text, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 128), 1, cv2.LINE_AA)


def run_webcam(stream: LiveviewStream, *, preview: bool, scale: float) -> None:
    """Publish the newest decoded frame at a steady output rate."""
    import pyvirtualcam

    first = None
    while first is None:
        frame = stream.latest_frame(timeout=10)
        first = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)

    height, width = first.shape[:2]
    print(f"Liveview resolution: {width}x{height}", flush=True)
    window_start = time.monotonic()
    window_received = 1
    last_frame_at = window_start
    image = first
    black = np.zeros_like(first)

    # OpenCV already decodes into BGR. pyvirtualcam accepts this format directly.
    with pyvirtualcam.Camera(width=width, height=height, fps=25,
                             fmt=pyvirtualcam.PixelFormat.BGR) as webcam:
        print(f"Virtual camera: {webcam.device} ({webcam.backend})", flush=True)
        if preview:
            cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        while True:
            frame = stream.poll_frame()
            now = time.monotonic()
            if frame is not None:
                decoded = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
                if decoded is not None:
                    if decoded.shape[:2] != (height, width):
                        decoded = cv2.resize(decoded, (width, height))
                    image = decoded
                    window_received += 1
                    last_frame_at = now

            stalled = now - last_frame_at
            if stalled > 30:
                raise TimeoutError("30s sin frames del liveview")
            webcam.send(image if stalled < 2 else black)
            if preview:
                shown = image
                if scale != 1.0:
                    shown = cv2.resize(shown, None, fx=scale, fy=scale)
                if stalled >= 2:
                    shown = np.zeros_like(shown)
                cv2.imshow(WINDOW, shown)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break

            if now - window_start >= 1:
                fps = window_received / (now - window_start)
                print(f"received {fps:.1f} fps | webcam {webcam.current_fps:.1f} fps | "
                      f"dropped {stream.frames_dropped} | {width}x{height} | "
                      f"frame age {stalled * 1000:.0f} ms", flush=True)
                window_start = now
                window_received = 0
            webcam.sleep_until_next_frame()


def main() -> int:
    args = parse_args()
    if args.no_preview and not args.webcam:
        print("--no-preview requires --webcam", file=sys.stderr)
        return 2

    print("Conectando con la camara..." if args.endpoint else "Buscando camara por SSDP...", flush=True)
    camera = SonyCamera(args.endpoint)
    print(f"Endpoint: {camera.endpoint}", flush=True)

    try:
        url = camera.start_liveview(prefer_size=args.size)
    except CameraError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "Comprueba que la camara esta en 'Ctrl. con smartphone' y que el PC "
            "esta conectado al WiFi de la camara.",
            file=sys.stderr,
        )
        return 1
    print(f"Liveview: {url}", flush=True)

    stream = LiveviewStream(url)

    shown = 0
    fps = 0.0
    fps_t0 = time.monotonic()
    fps_n0 = 0
    last_frame_at = time.monotonic()
    last_img: np.ndarray | None = None
    try:
        stream.start()
        if args.webcam:
            run_webcam(stream, preview=not args.no_preview, scale=args.scale)
            return 0
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        while True:
            # No bloquear NUNCA esperando frames: la ventana debe seguir
            # respondiendo aunque el stream se pause (WiFi/puente con hipos).
            frame = stream.poll_frame()
            now = time.monotonic()

            if frame is not None:
                img = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:  # JPEG corrupto ocasional: se ignora
                    if args.scale != 1.0:
                        img = cv2.resize(
                            img, None, fx=args.scale, fy=args.scale,
                            interpolation=cv2.INTER_LINEAR,
                        )
                    shown += 1
                    last_frame_at = now
                    if now - fps_t0 >= 1.0:
                        fps = (shown - fps_n0) / (now - fps_t0)
                        fps_t0, fps_n0 = now, shown
                    if not args.no_hud:
                        age_ms = (now - frame.received_at) * 1000
                        draw_hud(img, fps, age_ms, stream.frames_dropped)
                    last_img = img
                    cv2.imshow(WINDOW, img)
            else:
                stalled = now - last_frame_at
                if stalled > 30:
                    raise TimeoutError("30s sin frames del liveview")
                if stalled > 1.5 and last_img is not None and not args.no_hud:
                    frozen = last_img.copy()
                    cv2.putText(
                        frozen, f"SIN SENAL {stalled:.0f}s", (8, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA,
                    )
                    cv2.imshow(WINDOW, frozen)

            # Bombear eventos SIEMPRE: 1 ms si hay señal fluida, 15 ms en pausa
            key = cv2.waitKey(1 if frame is not None else 15) & 0xFF
            if key in (ord("q"), 27):
                break
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        return 0
    except (TimeoutError, ConnectionError, OSError, RuntimeError, ImportError) as e:
        print(f"Stream interrumpido: {e}", file=sys.stderr)
        return 1
    finally:
        stream.stop()
        camera.stop_liveview()
        if not args.webcam or not args.no_preview:
            cv2.destroyAllWindows()
        summary = f"Frames leidos: {stream.frames_read}, descartados: {stream.frames_dropped}"
        if not args.webcam:
            summary += f", mostrados: {shown}"
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
