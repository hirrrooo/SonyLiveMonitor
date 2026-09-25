"""Sign the LAN prototype for old a6000 Android using a dedicated local test key.

Requires the sony-pmca-android-builder:local Docker image (JDK 8 and Android
Build Tools 28.0.3). The keystore and password remain under ignored .build/.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".build/lan-apk"
KEY = OUTPUT / "lan-test.jks"
PASSWORD = OUTPUT / "lan-test-password.txt"
ENV_FILE = OUTPUT / "sign.env"
UNSIGNED = OUTPUT / "SonyLiveMonitor-a6000-LAN-test-unsigned.apk"
SIGNED = OUTPUT / "SonyLiveMonitor-a6000-LAN-test.apk"


def main() -> None:
    if not UNSIGNED.is_file():
        raise RuntimeError(f"build the unsigned APK first: {UNSIGNED}")
    if not KEY.is_file():
        password = secrets.token_urlsafe(20)
        PASSWORD.write_text(password + "\n")
        PASSWORD.chmod(0o600)
        subprocess.run(
            ["keytool", "-genkeypair", "-keystore", str(KEY), "-storetype", "JKS",
             "-storepass", password, "-keypass", password, "-alias", "sony-lan-test",
             "-keyalg", "RSA", "-keysize", "2048", "-sigalg", "SHA1withRSA",
             "-validity", "3650", "-dname", "CN=Sony Live Monitor LAN Prototype,O=Local Test"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    else:
        password = PASSWORD.read_text().strip()
    ENV_FILE.write_text("LAN_TEST_PASSWORD=" + password + "\n")
    ENV_FILE.chmod(0o600)

    script = r'''set -eu
sdk="$ANDROID_SDK_ROOT/build-tools/28.0.3"
jarsigner -keystore /work/lan-test.jks \
  -storepass "$LAN_TEST_PASSWORD" -keypass "$LAN_TEST_PASSWORD" \
  -sigalg SHA1withRSA -digestalg SHA1 \
  -signedjar /work/SonyLiveMonitor-a6000-LAN-test-signed-jdk8.apk \
  /work/SonyLiveMonitor-a6000-LAN-test-unsigned.apk sony-lan-test >/work/jdk8-sign.log 2>&1
"$sdk/zipalign" -f 4 /work/SonyLiveMonitor-a6000-LAN-test-signed-jdk8.apk \
  /work/SonyLiveMonitor-a6000-LAN-test.apk
"$sdk/zipalign" -c 4 /work/SonyLiveMonitor-a6000-LAN-test.apk
"$sdk/apksigner" verify --min-sdk-version 10 --verbose \
  /work/SonyLiveMonitor-a6000-LAN-test.apk
'''
    subprocess.run(
        ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
         "--env-file", str(ENV_FILE), "-v", f"{OUTPUT}:/work",
         "sony-pmca-android-builder:local", "sh", "-c", script],
        check=True,
    )
    print(SIGNED)


if __name__ == "__main__":
    main()
