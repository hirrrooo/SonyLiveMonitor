"""Build an experimental LAN-only Smart Remote APK from the bundled a6000 APK.

This is a narrow, reviewable smali patch to the known Sony app startup path.
The APK is not hardware-validated. Keep the signed output out of Git.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "camera-patches/SonyLiveMonitor-a6000-avcontent.apk"
OUTPUT = ROOT / ".build/lan-apk/SonyLiveMonitor-a6000-LAN-test-unsigned.apk"
APKTOOL = Path(os.environ.get("APKTOOL_JAR", "/tmp/sony-lan-apk/apktool_3.0.3.jar"))
SOURCE_SHA256 = "6bac7525942b71bc5bfa5eff1c66b8f0cb95df8f242d5eaf0b475fca7e48025f"
OLD_PACKAGE = "mod.sony.imaging.app.srctrl"
NEW_PACKAGE = "lan.sony.imaging.app.srctrl"

LAN_ENDPOINT_SMALI = r""".class public final Lcom/sony/imaging/app/srctrl/util/LanEndpoint;
.super Ljava/lang/Object;

# The camera's station address is advertised only after association succeeds.
.method public static liveviewUrl()Ljava/lang/String;
    .locals 4

    const-string v0, "http://127.0.0.1:8081/liveview/liveviewstream"

    invoke-static {}, Lcom/sony/imaging/app/srctrl/util/SRCtrlEnvironment;->getInstance()Lcom/sony/imaging/app/srctrl/util/SRCtrlEnvironment;
    move-result-object v1
    if-eqz v1, :done

    invoke-virtual {v1}, Lcom/sony/imaging/app/srctrl/util/SRCtrlEnvironment;->getContext()Landroid/content/Context;
    move-result-object v1
    if-eqz v1, :done

    const-string v2, "wifi"
    invoke-virtual {v1, v2}, Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;
    move-result-object v1
    check-cast v1, Landroid/net/wifi/WifiManager;
    if-eqz v1, :done

    invoke-virtual {v1}, Landroid/net/wifi/WifiManager;->getConnectionInfo()Landroid/net/wifi/WifiInfo;
    move-result-object v1
    if-eqz v1, :done

    invoke-virtual {v1}, Landroid/net/wifi/WifiInfo;->getIpAddress()I
    move-result v1
    if-eqz v1, :done

    new-instance v2, Ljava/lang/StringBuilder;
    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V
    const-string v3, "http://"
    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-static {v1}, Landroid/text/format/Formatter;->formatIpAddress(I)Ljava/lang/String;
    move-result-object v3
    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    const-string v3, ":8081/liveview/liveviewstream"
    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;
    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;
    move-result-object v0

    :done
    return-object v0
.end method
"""


def replace_once(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one patch anchor, found {count}")
    return source.replace(before, after, 1)


def patch_root_state(path: Path) -> None:
    source = path.read_text()
    start = source.index(".method public onResume()V")
    end = source.index(".end method", start)
    method = source[start:end]

    wifi_start = method.index("    .line 163\n    iget-object v1, p0, Lcom/sony/imaging/app/srctrl/SRCtrlRootState;->wifiManager:")
    wifi_end = method.index("    .line 174\n    :goto_1\n", wifi_start)
    # Preserve the current station association. A direct jump also keeps the
    # original Wi-Fi Direct branch unreachable without altering its code.
    method = (method[:wifi_start] + "    # LAN prototype: preserve station Wi-Fi\n    goto :goto_1\n\n"
              + method[wifi_end:])

    camera_info = (
        "    invoke-virtual {v0, v1}, Lcom/sony/imaging/app/srctrl/network/dd/"
        "DigitalImagingDeviceInfo;->createDigitalImagingDeviceInfoFile(Ljava/lang/String;)Z\n\n"
        "    goto/16 :goto_0"
    )
    camera_info_lan = camera_info.replace(
        "    goto/16 :goto_0",
        "    # LAN prototype: bind the existing Sony API after app state setup\n"
        "    sget-object v1, Lcom/sony/imaging/app/srctrl/SRCtrlRootState;->wsController:"
        "Lcom/sony/imaging/app/srctrl/webapi/util/WsController;\n"
        "    invoke-virtual {v1}, Lcom/sony/imaging/app/srctrl/webapi/util/WsController;->start()Z\n"
        "    move-result v1\n\n"
        "    goto/16 :goto_0",
    )
    method = replace_once(method, camera_info, camera_info_lan, "web server startup")
    source = source[:start] + method + source[end:]

    start = source.index(".method private invokeFinishProcess()V")
    end = source.index(".end method", start)
    method = source[start:end]
    method = replace_once(
        method,
        "    invoke-virtual {v4, v8}, Landroid/net/wifi/WifiManager;->setWifiEnabled(Z)Z",
        "    # LAN prototype: leave station Wi-Fi enabled when exiting",
        "Wi-Fi cleanup",
    )
    path.write_text(source[:start] + method + source[end:])


def patch_web_server_port(path: Path) -> None:
    source = path.read_text()
    anchor = '    const-string v3, "port"\n\n    const/16 v4, 0x1f90'
    path.write_text(replace_once(source, anchor, anchor.replace("0x1f90", "0x1f91"), "port 8081"))


def patch_liveview_urls(path: Path) -> None:
    source = path.read_text()
    pattern = re.compile(r'    const-string (v\d+), "http://192\.168\.122\.1:8080/liveview/liveviewstream"')

    def replacement(match: re.Match[str]) -> str:
        return (
            "    invoke-static {}, Lcom/sony/imaging/app/srctrl/util/LanEndpoint;->liveviewUrl()Ljava/lang/String;\n"
            f"    move-result-object {match.group(1)}"
        )

    source, count = pattern.subn(replacement, source)
    if count != 2:
        raise RuntimeError(f"live-view URLs: expected two returns, found {count}")
    path.write_text(source)


def repack_with_new_package(source_apk: Path, dest_apk: Path) -> None:
    old = OLD_PACKAGE.encode("utf-16le")
    new = NEW_PACKAGE.encode("utf-16le")
    if len(old) != len(new):
        raise RuntimeError("package names must have equal UTF-16 lengths")
    with ZipFile(source_apk) as source, ZipFile(dest_apk, "w") as output:
        for entry in source.infolist():
            data = source.read(entry.filename)
            if entry.filename == "AndroidManifest.xml":
                if data.count(old) != 1:
                    raise RuntimeError("expected one package string in binary manifest")
                data = data.replace(old, new, 1)
            elif entry.filename == "resources.arsc":
                # Four English/Spanish app-label strings use this exact 15-byte
                # name. Keep string-pool lengths unchanged so the test variant
                # is distinguishable in the camera's Applications menu.
                label_old = b"SonyLiveMonitor"
                label_new = b"SonyLAN Monitor"
                if len(label_old) != len(label_new) or data.count(label_old) != 4:
                    raise RuntimeError("unexpected app-label entries in resource table")
                data = data.replace(label_old, label_new)
            if entry.filename.startswith("META-INF/"):
                continue  # never carry an invalidated original signature
            output.writestr(entry, data)


def main() -> None:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("unexpected camera APK; inspect before patching")
    if not APKTOOL.is_file():
        raise RuntimeError(f"Apktool 3.0.3 jar required at {APKTOOL}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sony-lan-build-") as temp:
        workspace = Path(temp)
        decoded = workspace / "decoded"
        rebuilt = workspace / "rebuilt.apk"
        subprocess.run(["java", "-jar", str(APKTOOL), "d", "-r", "-q", "-o", str(decoded), str(SOURCE)], check=True)
        smali = decoded / "smali/com/sony/imaging/app/srctrl"
        patch_root_state(smali / "SRCtrlRootState.smali")
        patch_web_server_port(smali / "webapi/util/WsController.smali")
        patch_liveview_urls(smali / "webapi/v1_0/SRCtrlServlet.smali")
        (smali / "util/LanEndpoint.smali").write_text(LAN_ENDPOINT_SMALI)
        subprocess.run(["java", "-jar", str(APKTOOL), "b", "-q", str(decoded), "-o", str(rebuilt)], check=True)
        repack_with_new_package(rebuilt, OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
