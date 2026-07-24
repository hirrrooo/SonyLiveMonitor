#!/usr/bin/env python3
"""Punto de entrada del instalador de SonyLiveMonitor.

Sin argumentos abre la ventana grafica. Con `--console` (o si Tkinter no esta
disponible, cosa habitual en algunas distros Linux) usa el modo de texto.
"""

import argparse
import os
import sys

# Permite ejecutar el script directamente desde el repositorio.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sonyinstaller import __version__


def run_console(auto_yes=False, restore=False):
    """Modo texto: mismo flujo, sin ventana."""
    from sonyinstaller import assets, camera

    def log(message):
        print("  %s" % message)

    print("Sony Live Monitor - Installer v%s" % __version__)
    print("=" * 46)

    try:
        print("\n[1/3] Looking for the camera...")
        with camera.CameraSession(log) as session:
            info = session.detect()
        print("\n  Camera detected: %s" % info.model)
        if info.firmware:
            print("  Firmware: %s" % info.firmware)
        if not info.is_a6000:
            print("  WARNING: only tested on the ILCE-6000. Continue at your "
                  "own risk.")

        if not auto_yes:
            if restore:
                print("\n  Sony's original 'Smart Remote Control' (v4.30) "
                      "will be installed.")
            else:
                print("\n  'Smart Remote Control' will be replaced with the "
                      "patched version.")
            print("  Do not disconnect the camera during the process.")
            if input("\n  Continue? [y/N] ").strip().lower() not in ("y", "s"):
                print("  Cancelled.")
                return 1

        print("\n[2/3] Preparing the APK...")
        apk_path = (assets.resolve_original_apk() if restore
                    else assets.resolve_apk(log))

        print("\n[3/3] Installing...")

        def progress(message, percent):
            print("  %s %d%%" % (message, percent))

        with camera.CameraSession(log) as session:
            session.install_apk(apk_path, progress)

        if restore:
            print("\nDone. Restart the camera: 'Smart Remote Control' is "
                  "back in Applications.")
        else:
            print("\nDone. Restart the camera and open Applications > "
                  "SonyLiveMonitor.")
        return 0

    except (camera.CameraError, assets.AssetError) as exc:
        print("\nERROR: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 1


def run_selftest():
    """Comprueba que el ejecutable lleva dentro todo lo necesario.

    Lo usa la CI: si el APK o PMCA-RE no se empaquetaran, el fallo aparecia en
    el ordenador del usuario en lugar de en el build.
    """
    from sonyinstaller import assets, camera

    ok = True

    print("Frozen:         %s" % bool(getattr(sys, "frozen", False)))

    apk = assets.find_local_apk()
    if apk and os.path.isfile(apk) and os.path.getsize(apk) > 0:
        print("Patched APK:    OK (%d KB)" % (os.path.getsize(apk) // 1024))
    else:
        print("Patched APK:    MISSING")
        ok = False

    original = assets.find_original_apk()
    if original and os.path.isfile(original) and os.path.getsize(original) > 0:
        print("Original APK:   OK (%d KB)" % (os.path.getsize(original) // 1024))
    else:
        print("Original APK:   MISSING (restore will not work)")
        ok = False

    try:
        module = camera.load_pmca()
        required = ["importDriver", "listDevices", "installApp", "printStatus",
                    "SonyAppInstallDevice", "SonyExtCmdDevice",
                    "SonyExtCmdCamera", "InvalidCommandException"]
        missing = [n for n in required if not hasattr(module, n)]
        if missing:
            print("PMCA-RE:        MISSING SYMBOLS: %s" % ", ".join(missing))
            ok = False
        else:
            print("PMCA-RE:        OK")
    except Exception as exc:
        print("PMCA-RE:        ERROR: %s" % exc)
        ok = False

    try:
        import certifi
        print("certifi:        OK (%s)" % os.path.basename(certifi.where()))
    except Exception as exc:
        print("certifi:        ERROR: %s" % exc)
        ok = False

    # La instalacion habla TLS con la camara. En un ejecutable empaquetado esta
    # ruta fallaba (ver runtime_hook_tlslite.py), y solo se notaba con la camara
    # conectada. Comprobarlo aqui hace que el fallo salte en el build.
    try:
        from tlslite.utils import cipherfactory
        cipher = cipherfactory.createAES(b"k" * 16, b"i" * 16)
        cipher.encrypt(b"A" * 16)
        print("TLS/AES:        OK (%s)" % type(cipher).__name__)
    except Exception as exc:
        print("TLS/AES:        ERROR: %s: %s" % (type(exc).__name__, exc))
        ok = False

    print("\n%s" % ("SELFTEST OK" if ok else "SELFTEST FAILED"))
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(
        description="Install the patched Smart Remote on a Sony camera."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--console", action="store_true",
                        help="use text mode instead of the window")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="do not ask for confirmation (with --console)")
    parser.add_argument("--selftest", action="store_true",
                        help="check the bundled contents and exit")
    parser.add_argument("--restore", action="store_true",
                        help="reinstall Sony's original Smart Remote")
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()

    if args.console or args.restore:
        return run_console(args.yes, restore=args.restore)

    try:
        from sonyinstaller.gui import main as gui_main
    except ImportError:
        print("Tkinter is not available; falling back to console mode.\n"
              "On Debian/Ubuntu install it with: sudo apt install python3-tk\n",
              file=sys.stderr)
        return run_console(args.yes)

    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
