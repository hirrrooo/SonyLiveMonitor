# SonyLAN Monitor: signed a6000 test APK

This branch contains a **hardware-untested** infrastructure-Wi-Fi experiment based on the bundled SonyLiveMonitor a6000 Smart Remote APK. It is a separate package, `lan.sony.imaging.app.srctrl`, labeled **SonyLAN Monitor**. The existing Smart Remote and SonyLiveMonitor applications remain installed.

The patch is deliberately narrow: `SRCtrlRootState.onResume` preserves the current station association and starts the existing Sony HTTP API service without waiting for a Wi-Fi Direct group; cleanup leaves station Wi-Fi enabled; `WsController` listens on port **8081** to avoid Camera Web Companion's port 8080; both live-view start methods return a URL made from the camera's current Wi-Fi IPv4 address. There is no SSDP discovery in this prototype, so give the desktop client the API endpoint explicitly. The app does **not** configure or join a home SSID itself: join through the known working Camera Web Companion path before opening SonyLAN Monitor.

## Install and test on the camera

1. Keep the released original and patched APKs available for recovery. This experimental package installs alongside them; do not uninstall either. Use a charged battery and an SD card.
2. With the camera in **USB Connection → Mass Storage**, install the signed `SonyLiveMonitor-a6000-LAN-test.apk` through the same Sony-PMCA-RE `install -f` procedure used for your other PMCA camera apps. Do not use Android `adb install` or the upstream one-click installer; the latter installs its own bundled release APK.
3. Disconnect USB. Start **Camera Web Companion** and join the normal Wi-Fi network as before. Confirm its displayed `http://LAN_IP:8080/` page works from the PC. Note the LAN IP.
4. Leave Web Companion and open **SonyLAN Monitor** on the camera. Keep the PC on the normal LAN/Ethernet. The intended behavior is no DIRECT hotspot. The camera may initially show Smart Remote's preparation screen until the PC calls `startRecMode`.
5. On Windows PowerShell, substitute the actual camera LAN IP:

   ```powershell
   $cameraIp = '192.168.1.50'
   Test-NetConnection $cameraIp -Port 8081
   $body = @{ method='getVersions'; params=@(); id=1; version='1.0' } | ConvertTo-Json -Compress
   Invoke-RestMethod -Uri "http://$($cameraIp):8081/sony/camera" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 5
   ```

6. If `getVersions` returns Sony JSON, run the desktop webcam from the **separate** `feature/desktop-webcam` branch:

   ```powershell
   .\.venv\Scripts\python.exe monitor.py --webcam --size L --endpoint "http://$($cameraIp):8081/sony/camera"
   ```

The startup `Liveview:` line should contain `LAN_IP:8081/liveview/liveviewstream`. If it contains `127.0.0.1:8081`, the camera app had no station IPv4 address when it answered. If `getVersions` works but `startRecMode` or `startLiveview` fails, record the exact API error; the Sony shooting-state transition is the next camera-side component to inspect. If TCP 8081 fails, record whether the camera still has the LAN IP and whether the SonyLAN Monitor screen stays open. No ADB is required for this first test.

Stop or uninstall **SonyLAN Monitor** through the camera's Application Management menu to return to the existing apps. The patch does not alter firmware or the other camera packages.

## Build provenance and local verification

`build_unsigned.py` checks the SHA-256 of the bundled upstream v0.11 APK before applying explicit smali and equal-length binary manifest/resource string edits. It uses Apktool 3.0.3 with raw resource preservation because Sony's legacy nine-patch images do not rebuild with modern `aapt2`. Set `APKTOOL_JAR` to that jar's path if it is not at the script's default path, then run `python3 camera-lan-prototype/build_unsigned.py`.

`sign_test_apk.py` signs with a dedicated local test keystore using JDK 8, SHA-1/v1 JAR signing, then checks alignment and verifies the result with Android Build Tools 28.0.3 for API 10. It requires the local `sony-pmca-android-builder:local` Docker image used in the companion PMCA project. The keystore, password and APK stay under ignored `.build/lan-apk/`; keep that keystore if you want to install an update over the same test package.

Static checks passed: the APK ZIP is intact; JADX decodes its manifest as `lan.sony.imaging.app.srctrl` and its English/Spanish label as **SonyLAN Monitor**; decompiled live-view start methods call the new LAN URL helper; `apksigner verify --min-sdk-version 10` reports v1 verification. **Installation, LAN connectivity, live view, camera controls and recording have not been tested on a physical a6000.**
