# PyInstaller spec del instalador de SonyLiveMonitor.
#
#   pyinstaller installer/installer.spec
#
# Requiere PMCA-RE clonado en installer/pmca-re (ver installer/README.md).

import os
import sys

installer_dir = os.path.abspath(os.path.dirname(SPEC))
repo_root = os.path.dirname(installer_dir)
pmca_root = os.environ.get("PMCA_ROOT") or os.path.join(installer_dir, "pmca-re")

if not os.path.isdir(os.path.join(pmca_root, "pmca")):
    raise SystemExit(
        "No se encuentra PMCA-RE en %s.\n"
        "Clonalo con:\n"
        "  git clone https://github.com/ma1co/Sony-PMCA-RE.git installer/pmca-re"
        % pmca_root
    )

patches_dir = os.path.join(repo_root, "camera-patches")

# Los dos APK viajan dentro del ejecutable: el parcheado que se instala y el
# original de Sony, para poder deshacer la instalacion sin internet.
apks = [
    "SonyLiveMonitor-a6000-avcontent.apk",
    "SmartRemote-a6000-original-v4.30.apk",
]

datas = [
    # PMCA valida el certificado de su servidor local con estos ficheros.
    (os.path.join(pmca_root, "certs"), "certs"),
]

for name in apks:
    path = os.path.join(patches_dir, name)
    if not os.path.isfile(path):
        raise SystemExit("No se encuentra el APK %s" % path)
    datas.append((path, "camera-patches"))

# `config.py` esta en la raiz de PMCA y se importa como modulo suelto.
hidden = [
    "config",
    "pmca.usb.driver.generic.libusb",
    "pmca.usb.driver.generic.qemu",
]
if sys.platform == "win32":
    hidden += [
        "pmca.usb.driver.windows.msc",
        "pmca.usb.driver.windows.wpd",
        "pmca.usb.driver.windows.driverless",
    ]
elif sys.platform == "darwin":
    hidden += ["pmca.usb.driver.osx"]

excludes = ["numpy", "matplotlib", "PIL", "pytest", "lzma", "bz2", "tarfile"]
if sys.platform != "win32":
    excludes.append("pmca.usb.driver.windows")
if sys.platform != "darwin":
    excludes.append("pmca.usb.driver.osx")

a = Analysis(
    [os.path.join(installer_dir, "installer.py")],
    pathex=[installer_dir, pmca_root],
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    # Sin esto el handshake TLS con la camara falla solo en el ejecutable
    # empaquetado. Ver runtime_hook_tlslite.py.
    runtime_hooks=[os.path.join(installer_dir, "runtime_hook_tlslite.py")],
)

# certifi trae un bundle grande; solo hace falta el cacert.
a.datas = [d for d in a.datas
           if not (d[0].startswith("certifi") and not d[0].endswith("cacert.pem"))]

pyz = PYZ(a.pure)

name = "SonyLiveMonitor-Installer"

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name=name,
    console=False,      # aplicacion de ventana, sin consola detras
    upx=False,
    icon=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=name + ".app",
        bundle_identifier="com.otonielpv.sonylivemonitor.installer",
        info_plist={
            "NSHighResolutionCapable": True,
            # Sin esto macOS no deja abrir dispositivos USB.
            "NSCameraUsageDescription": "Acceso USB a la camara Sony.",
        },
    )
