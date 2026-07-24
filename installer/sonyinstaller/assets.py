"""Localiza el APK parcheado que hay que instalar en la camara.

Orden de busqueda:

1. El APK empaquetado dentro del ejecutable (PyInstaller lo extrae a `_MEIPASS`).
2. El APK del repositorio, cuando se ejecuta desde el codigo fuente.
3. Descarga desde la ultima Release de GitHub, como respaldo.

Asi el .exe funciona sin conexion, pero tambien puede actualizarse solo si algun
dia distribuimos un instalador sin APK incrustado.
"""

import json
import os
import ssl
import sys
import tempfile
import urllib.request

import certifi

APK_NAME = "SonyLiveMonitor-a6000-avcontent.apk"
RELEASE_API = "https://api.github.com/repos/otonielpv/SonyLiveMonitor/releases/latest"

# El APK de la camara se publica con un nombre largo para que nadie lo confunda
# con el APK del movil.
RELEASE_ASSET_HINTS = ("avcontent",)

# Smart Remote Control de fabrica (com.sony.imaging.app.srctrl v4.30), extraido
# de una a6000 sin parchear. Sirve para deshacer la instalacion.
#
# El paquete del parcheado es 'mod.sony.imaging.app.srctrl', distinto del
# original, asi que ambos pueden convivir en la camara: restaurar no obliga a
# desinstalar nada antes.
ORIGINAL_APK_NAME = "SmartRemote-a6000-original-v4.30.apk"


class AssetError(Exception):
    pass


def _bundle_dir():
    """Carpeta de datos: `_MEIPASS` si esta congelado, si no el repo."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS")
    # installer/sonyinstaller/assets.py -> raiz del repositorio
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_local_apk(name=APK_NAME):
    """Devuelve la ruta de un APK incluido, o None si no esta."""
    candidates = [
        os.path.join(_bundle_dir(), "camera-patches", name),
        os.path.join(_bundle_dir(), name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def find_original_apk():
    """Ruta del Smart Remote de fabrica incluido en el instalador."""
    return find_local_apk(ORIGINAL_APK_NAME)


def resolve_original_apk():
    """Como `find_original_apk`, pero falla con un mensaje util."""
    path = find_original_apk()
    if not path:
        raise AssetError(
            "This installer does not ship the original app, so it cannot "
            "restore it.\n\n"
            "Download the latest installer from the Releases page."
        )
    return path


def _ssl_context():
    return ssl.create_default_context(cafile=certifi.where())


def download_apk(log=None, dest_dir=None):
    """Descarga el APK de la camara desde la ultima Release."""
    log = log or (lambda _msg: None)
    log("Checking the latest published version...")

    request = urllib.request.Request(
        RELEASE_API, headers={"Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=30, context=_ssl_context()
        ) as response:
            release = json.load(response)
    except Exception as exc:
        raise AssetError(
            "Could not reach the releases list. Check your internet "
            "connection."
        ) from exc

    url = None
    for asset in release.get("assets", []):
        name = asset.get("name", "").lower()
        if name.endswith(".apk") and any(h in name for h in RELEASE_ASSET_HINTS):
            url = asset.get("browser_download_url")
            break

    if not url:
        raise AssetError(
            "The latest release does not include the camera APK. Download it "
            "manually from the Releases page."
        )

    dest_dir = dest_dir or tempfile.mkdtemp(prefix="sonylivemonitor-")
    dest = os.path.join(dest_dir, APK_NAME)
    log("Downloading %s..." % os.path.basename(url))
    try:
        with urllib.request.urlopen(
            url, timeout=120, context=_ssl_context()
        ) as response, open(dest, "wb") as out:
            out.write(response.read())
    except Exception as exc:
        raise AssetError("Failed to download the camera APK.") from exc

    log("APK downloaded.")
    return dest


def read_apk_version(apk_path):
    """versionName del APK, o None si no se puede leer.

    Ojo: el APK parcheado hereda el versionName de Sony (4.30) y no cambia
    entre releases del proyecto, asi que sirve para informar pero NO para
    decidir si hay una actualizacion disponible.
    """
    try:
        from pmca.apk import ApkParser
    except ImportError:
        # PMCA-RE aun no esta en sys.path (solo se anade al abrir la camara).
        try:
            from .camera import load_pmca
            load_pmca()
            from pmca.apk import ApkParser
        except Exception:
            return None
    try:
        with open(apk_path, "rb") as handle:
            return ApkParser(handle).getVersionName()
    except Exception:
        return None


def resolve_apk(log=None):
    """Devuelve la ruta del APK a instalar, descargandolo si hace falta."""
    log = log or (lambda _msg: None)
    local = find_local_apk()
    if local:
        log("Using the APK bundled with the installer.")
        return local
    return download_apk(log)
