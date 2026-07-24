"""Copia de seguridad opcional del Smart Remote Control original, via ADB.

Es opcional a proposito. El camino normal del instalador no lo necesita: no
requiere ADB, ni OpenMemories: Tweak, ni tocar los menus de la camara.

Quien quiera la copia debe hacer un paso manual que no se puede automatizar
(activar ADB en el menu de la camara). A partir de ahi esto se encarga de todo:
descubre la IP, se conecta y descarga el APK original.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time

SMART_REMOTE_PACKAGE = "com.sony.imaging.app.srctrl"
ADB_PORT = 5555


class BackupError(Exception):
    pass


def _no_window():
    """Evita que en Windows parpadee una consola por cada llamada a adb."""
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": startupinfo}
    return {}


def find_adb():
    """Busca el ejecutable de adb en el PATH y en rutas habituales."""
    found = shutil.which("adb")
    if found:
        return found

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
        os.path.join(home, "Android", "Sdk", "platform-tools", "adb"),
        os.path.join(home, "Library", "Android", "sdk", "platform-tools", "adb"),
        "/usr/local/bin/adb",
        "/usr/bin/adb",
        "/opt/homebrew/bin/adb",
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _adb(adb_path, *args, timeout=30):
    result = subprocess.run(
        [adb_path, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        **_no_window(),
    )
    return result


def _local_subnets():
    """Prefijos /24 de las interfaces locales, para barrer buscando la camara."""
    prefixes = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            prefix = ip.rsplit(".", 1)[0]
            if prefix not in prefixes:
                prefixes.append(prefix)
    except socket.gaierror:
        pass
    # La red que crea la propia camara es casi siempre esta.
    for prefix in ("192.168.122", "192.168.1", "192.168.0"):
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


def _port_open(ip, port, timeout=0.25):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((ip, port)) == 0


def discover_camera_ip(log=None, hint=None):
    """Encuentra una IP con el puerto ADB abierto.

    Se prueba primero la pista del usuario; si no, se barre la subred local.
    """
    log = log or (lambda _msg: None)

    if hint:
        log("Trying %s..." % hint)
        if _port_open(hint, ADB_PORT, timeout=2.0):
            return hint
        raise BackupError(
            "No ADB response at %s. Check that 'Enable ADB' is still on in "
            "the camera and that this computer is on its Wi-Fi." % hint
        )

    for prefix in _local_subnets():
        log("Looking for the camera on %s.x ..." % prefix)
        for last in range(1, 255):
            ip = "%s.%d" % (prefix, last)
            if _port_open(ip, ADB_PORT):
                log("Camera found at %s" % ip)
                return ip

    raise BackupError(
        "The camera was not found on the network.\n\n"
        "Check that this computer is connected to the camera's Wi-Fi "
        "(DIRECT-xxxx:ILCE-6000) and that ADB is enabled in\n"
        "Applications > OpenMemories: Tweak > Developer > Enable ADB."
    )


def backup_original_apk(dest_path, log=None, ip_hint=None):
    """Descarga el Smart Remote original de la camara a `dest_path`."""
    log = log or (lambda _msg: None)

    adb_path = find_adb()
    if not adb_path:
        raise BackupError(
            "'adb' was not found.\n\n"
            "Install the Android Platform Tools and try again:\n"
            "https://developer.android.com/tools/releases/platform-tools"
        )

    ip = discover_camera_ip(log, ip_hint)

    log("Connecting over ADB...")
    _adb(adb_path, "disconnect")
    result = _adb(adb_path, "connect", "%s:%d" % (ip, ADB_PORT))
    if "connected" not in (result.stdout or "").lower():
        raise BackupError("ADB could not connect to %s:\n%s" % (ip, result.stdout))

    target = "%s:%d" % (ip, ADB_PORT)
    try:
        # Tras 'connect' el dispositivo tarda un instante en aparecer.
        for attempt in range(10):
            result = _adb(adb_path, "-s", target, "shell", "pm", "path", SMART_REMOTE_PACKAGE)
            if "package:" in (result.stdout or ""):
                break
            time.sleep(0.5)
        else:
            raise BackupError(
                "The camera does not have the original Smart Remote Control "
                "installed, or ADB is not responding yet. If you already "
                "installed the patch, this backup is no longer possible."
            )

        match = re.search(r"package:(\S+)", result.stdout)
        if not match:
            raise BackupError("Could not locate the APK on the camera.")
        remote_path = match.group(1)
        log("Original APK: %s" % remote_path)

        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        log("Downloading backup...")
        result = _adb(adb_path, "-s", target, "pull", remote_path, dest_path, timeout=180)
        if result.returncode != 0:
            raise BackupError("Failed to pull the APK:\n%s" % (result.stderr or result.stdout))

        if not os.path.isfile(dest_path) or os.path.getsize(dest_path) == 0:
            raise BackupError(
                "The backup file is empty. Do not continue until you have a "
                "valid copy."
            )

        size_kb = os.path.getsize(dest_path) // 1024
        log("Backup saved (%d KB): %s" % (size_kb, dest_path))
        return dest_path
    finally:
        _adb(adb_path, "disconnect")
