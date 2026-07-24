"""Capa sobre PMCA-RE: deteccion de camara e instalacion de APK.

PMCA-RE esta pensado como aplicacion de linea de comandos: informa del progreso
con `print()` y lanza excepciones sueltas. Aqui lo envolvemos para exponer una
API pequena y sincrona que la GUI pueda llamar desde un hilo de trabajo:

    with CameraSession(log) as session:
        info = session.detect()
        session.install_apk(path)

Todo lo que PMCA imprima se redirige al callback `log`.
"""

import contextlib
import io
import os
import sys
import threading
import time


class CameraError(Exception):
    """Fallo esperable y explicable al usuario (no un bug del instalador)."""


class NoCameraFound(CameraError):
    pass


class TooManyCameras(CameraError):
    pass


class UnsupportedMode(CameraError):
    """La camara esta conectada pero en un modo USB que no sirve."""


class MissingUsbBackend(CameraError):
    """Falta la libreria libusb con la que se habla por USB."""


def _missing_backend_message():
    """Instrucciones para instalar libusb, distintas en cada sistema."""
    if sys.platform == "win32":
        extra = (
            "Connect the camera in 'Mass Storage' mode, which does not need\n"
            "this library. If the problem persists, install the libusb driver\n"
            "with Zadig: https://zadig.akeo.ie"
        )
    elif sys.platform == "darwin":
        extra = "Install it with Homebrew:\n    brew install libusb"
    else:
        extra = (
            "On Debian/Ubuntu:\n"
            "    sudo apt install libusb-1.0-0\n\n"
            "You may also need permission to access USB devices without root\n"
            "(a udev rule), or you can run the installer with sudo."
        )
    return "No USB driver available (libusb not found).\n\n" + extra


# PMCA-RE no es un paquete de pip: es un checkout de git que espera ejecutarse
# desde su propia raiz (hace `import config` y resuelve rutas relativas a ella).
# Por eso hay que anadirlo a sys.path a mano antes de importarlo.
#
# El import es perezoso para que la ventana pueda abrirse y mostrar un error
# legible si falta la dependencia, en vez de morir al arrancar.
_import_lock = threading.Lock()
_pmca = None

# Sitios donde puede estar PMCA-RE, en orden de preferencia.
_PMCA_ENV_VAR = "PMCA_ROOT"
_PMCA_DIR_NAMES = ("pmca-re", "Sony-PMCA-RE", "vendor/Sony-PMCA-RE")


def _candidate_roots():
    """Rutas donde buscar el checkout de PMCA-RE."""
    env_root = os.environ.get(_PMCA_ENV_VAR)
    if env_root:
        yield env_root

    if getattr(sys, "frozen", False):
        # PyInstaller extrae los datos aqui; PMCA queda en la raiz del bundle.
        yield getattr(sys, "_MEIPASS")

    # Ejecutando desde el repositorio: installer/sonyinstaller/camera.py
    installer_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(installer_dir)
    for base in (installer_dir, repo_root):
        for name in _PMCA_DIR_NAMES:
            yield os.path.join(base, name)


def load_pmca():
    """Importa PMCA-RE una sola vez. Devuelve el modulo de comandos usb."""
    global _pmca
    with _import_lock:
        if _pmca is not None:
            return _pmca

        # Si ya es importable (bundle congelado), no toques sys.path.
        try:
            from pmca.commands import usb as pmca_usb
        except ImportError:
            root = next(
                (r for r in _candidate_roots()
                 if r and os.path.isdir(os.path.join(r, "pmca"))),
                None,
            )
            if root is None:
                raise CameraError(
                    "PMCA-RE is missing. It is the component that talks to "
                    "the camera.\n\n"
                    "If you are running from source, clone it into "
                    "'installer/':\n"
                    "    git clone https://github.com/ma1co/Sony-PMCA-RE.git "
                    "installer/pmca-re\n"
                    "    pip install -r installer/requirements.txt\n\n"
                    "Or point to it with the %s variable." % _PMCA_ENV_VAR
                )
            if root not in sys.path:
                sys.path.insert(0, root)
            try:
                from pmca.commands import usb as pmca_usb
            except ImportError as exc:  # pragma: no cover - depende del entorno
                raise CameraError(
                    "PMCA-RE was found in '%s' but could not be loaded. "
                    "Its dependencies are missing:\n"
                    "    pip install -r installer/requirements.txt\n\n"
                    "Details: %s" % (root, exc)
                ) from exc

        _pmca = pmca_usb
        return _pmca


class _LogWriter(io.TextIOBase):
    """Convierte los `print()` de PMCA-RE en llamadas a un callback por linea.

    El callback puede a su vez imprimir (en modo consola es el propio `print`).
    Como aqui stdout esta redirigido, eso se realimentaria hasta desbordar la
    pila, asi que mientras se ejecuta el callback se restaura el stdout real.
    """

    def __init__(self, log):
        self._log = log
        self._buffer = ""
        self._emitting = False

    def _emit(self, line):
        if self._emitting:
            # Reentrada: el callback ha vuelto a escribir en stdout. Se ignora
            # para no realimentar el bucle.
            return
        self._emitting = True
        try:
            with contextlib.redirect_stdout(sys.__stdout__), \
                    contextlib.redirect_stderr(sys.__stderr__):
                self._log(line)
        finally:
            self._emitting = False

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self._emit(line)
        return len(text)

    def flush(self):
        if self._buffer.strip():
            self._emit(self._buffer.strip())
        self._buffer = ""


@contextlib.contextmanager
def _captured(log):
    """Redirige stdout/stderr al log mientras dure el bloque."""
    writer = _LogWriter(log)
    with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
        try:
            yield
        finally:
            writer.flush()


# Nombre con el que la camara reporta la app parcheada. La original de Sony se
# llama 'Smart Remote Control' / 'Mando a dist. inteligente' segun el idioma.
PATCHED_APP_NAME = "SonyLiveMonitor"


class CameraInfo:
    def __init__(self, model, product_code=None, serial=None, firmware=None,
                 apps=None):
        self.model = model
        self.product_code = product_code
        self.serial = serial
        self.firmware = firmware
        # Lista de (nombre, version) que la camara declara tener instaladas.
        # Solo llega en modo instalador; vacia en mass storage.
        self.apps = apps or []

    @property
    def is_a6000(self):
        return (self.model or "").upper().replace("-", "").startswith("ILCE6000")

    @property
    def has_patched_app(self):
        """True si la camara ya declara tener instalada la app parcheada."""
        return any(PATCHED_APP_NAME.lower() in (name or "").lower()
                   for name, _version in self.apps)

    def __str__(self):
        return self.model or "unknown camera"


class CameraSession:
    """Mantiene abierto el driver USB durante varias operaciones.

    Abrir el driver es caro y en Windows puede tardar, asi que la GUI abre una
    sesion y la reutiliza para detectar e instalar.
    """

    def __init__(self, log=None, driver_name=None):
        self._log = log or (lambda _msg: None)
        self._driver_name = driver_name
        self._driver_ctx = None
        self._driver = None

    def __enter__(self):
        pmca = load_pmca()
        with _captured(self._log):
            self._driver_ctx = pmca.importDriver(self._driver_name)
            self._driver = self._driver_ctx.__enter__()
        return self

    def __exit__(self, *exc):
        if self._driver_ctx is not None:
            with _captured(self._log):
                self._driver_ctx.__exit__(*exc)
        self._driver_ctx = None
        self._driver = None
        return False

    def _list_devices(self, quiet=False):
        """Enumera camaras Sony tolerando que algun driver falle.

        `UsbDriverList.listDevices` recorre todos los drivers en un unico
        generador, asi que si uno lanza (tipicamente libusb, cuando la DLL no
        esta instalada) se pierde lo que hubieran encontrado los demas. En
        Windows los drivers nativos bastan, asi que aqui se enumera driver a
        driver y solo se da error si fallan todos.
        """
        pmca = load_pmca()
        devices = []
        failures = []

        for driver in list(self._driver._drivers):
            single = pmca.UsbDriverList()
            single._drivers = [driver]
            try:
                with _captured(self._log):
                    devices.extend(pmca.listDevices(single, quiet))
            except Exception as exc:
                failures.append((getattr(driver, "name", "?"), exc))
                self._log("Driver %s unavailable (%s)"
                          % (getattr(driver, "name", "?"), type(exc).__name__))

        # Solo es un problema real si ningun driver ha podido enumerar.
        if not devices and failures and len(failures) == len(self._driver._drivers):
            if any(type(e).__name__ == "NoBackendError" for _, e in failures):
                raise MissingUsbBackend(_missing_backend_message())
            raise failures[0][1]

        return devices

    def _get_device(self):
        """Devuelve el unico dispositivo Sony conectado, o lanza CameraError."""
        devices = self._list_devices()

        if not devices:
            raise NoCameraFound(
                "No camera detected.\n\n"
                "To connect your Sony camera:\n\n"
                "1. Turn the camera ON, with a charged battery and an SD\n"
                "   card inserted.\n"
                "2. On the camera, set MENU > Setup > USB Connection to\n"
                "   'Mass Storage'.\n"
                "3. Connect it with a USB data cable - charge-only cables\n"
                "   will not work.\n"
                "4. Close any software that may take over the camera:\n"
                "   Imaging Edge, PlayMemories, Photos, Dropbox...\n\n"
                "Then press 'Search again'."
            )
        if len(devices) > 1:
            raise TooManyCameras(
                "More than one Sony camera is connected.\n\n"
                "Disconnect the others and leave only the camera you want to "
                "patch, then press 'Search again'."
            )
        return devices[0]

    def detect(self):
        """Identifica la camara conectada. No la modifica."""
        pmca = load_pmca()
        device = self._get_device()

        # En modo instalador de apps la unica forma de leer el modelo es
        # arrancar una sesion vacia con el servidor local de PMCA.
        if isinstance(device, pmca.SonyAppInstallDevice):
            with _captured(self._log):
                info = pmca.installApp(device)
            device_info = info["deviceinfo"]
            return CameraInfo(
                model=device_info["name"],
                product_code=device_info.get("productcode"),
                serial=device_info.get("deviceid"),
                firmware=device_info.get("fwversion"),
                apps=[(a.get("name"), a.get("version"))
                      for a in info.get("applications") or []],
            )

        if isinstance(device, pmca.SonyExtCmdDevice):
            with _captured(self._log):
                cam = pmca.SonyExtCmdCamera(device)
                info = cam.getCameraInfo()
            return CameraInfo(
                model=info.modelName,
                product_code=info.modelCode,
                serial=info.serial,
            )

        raise UnsupportedMode(
            "The camera is connected, but in a USB mode that does not allow "
            "installing apps.\n\n"
            "On the camera set MENU > Setup > USB Connection to 'Mass "
            "Storage'. Then turn it off, unplug it, plug it back in and turn "
            "it on."
        )

    def install_apk(self, apk_path, progress=None):
        """Instala un APK local en la camara.

        `progress` recibe (mensaje, porcentaje) si se proporciona.
        """
        pmca = load_pmca()
        device = self._get_device()

        if isinstance(device, pmca.SonyExtCmdDevice):
            device = self._switch_to_app_installer(device)

        if not isinstance(device, pmca.SonyAppInstallDevice):
            raise UnsupportedMode(
                "The camera is not in a mode that allows installing. Set it "
                "to 'Mass Storage' and reconnect it."
            )

        self._run_install(device, apk_path, progress)

    def _switch_to_app_installer(self, device):
        """Pide a la camara que reinicie en modo instalador y espera a que vuelva."""
        pmca = load_pmca()
        self._log("Switching the camera to app install mode...")
        try:
            with _captured(self._log):
                pmca.SonyExtCmdCamera(device).switchToAppInstaller()
        except pmca.InvalidCommandException as exc:
            raise CameraError(
                "This camera does not support apps. Check the PMCA-RE "
                "compatibility list for supported models."
            ) from exc

        self._log("Waiting for the camera to reconnect...")
        for _ in range(20):
            time.sleep(0.5)
            try:
                devices = self._list_devices(quiet=True)
            except Exception:
                # Durante el cambio de modo el dispositivo desaparece del bus y
                # el driver puede fallar; es esperado, seguimos esperando.
                continue
            if len(devices) == 1 and isinstance(devices[0], pmca.SonyAppInstallDevice):
                self._log("Camera ready in install mode.")
                return devices[0]

        raise CameraError(
            "The camera did not reconnect in time.\n\n"
            "Unplug it, plug it back in and press Install again."
        )

    def _run_install(self, device, apk_path, progress):
        """Ejecuta installApp reenviando el progreso a la GUI."""
        pmca = load_pmca()

        if progress is not None:
            original = pmca.printStatus

            def forward(status):
                progress(status.message, status.percent)

            pmca.printStatus = forward
        try:
            with open(apk_path, "rb") as apk_file, _captured(self._log):
                pmca.installApp(device, apkFile=apk_file)
        finally:
            if progress is not None:
                pmca.printStatus = original
