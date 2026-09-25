# a6000 infrastructure Wi-Fi: first hardware test

This branch is for LAN research only. It starts from upstream v0.11; it does not contain the desktop webcam change or any modified camera APK.

## Evidence so far

- The user's `sony-pmca-apps` Camera Web Companion has operated as a client on an existing Wi-Fi network. Its `packages/pmca-core/.../SonyWifiHelper.java:connectAndWait` enables Android Wi-Fi and associates a saved SSID with `WifiManager`; `apps/camera-webcompanion/.../WebServerService.java:serve` listens on `0.0.0.0:8080`. This establishes a working station-mode path in a separate camera app on the user's device. It does not establish that Smart Remote preserves that connection.
- Read-only decompilation of the SonyLiveMonitor bundled Smart Remote APK found `com.sony.imaging.app.srctrl.SRCtrlRootState.onResume` resets enabled Wi-Fi. Its subsequent state handlers enable Wi-Fi Direct and call `startGroupOwner`; the implementation creates a Wi-Fi Direct group. `handleGroupCreateSuccess` starts the Sony web server and SSDP device description only after group creation. `NetworkRootState.onResume` expects Group Owner mode. This is a concrete camera-app dependency on the DIRECT network.
- Smart Remote's `OrbAndroidServiceEx` creates an HTTP server on port 8080 using `ServerBuilder`'s default host `0.0.0.0`. If a station interface remains available and the server runs, the socket may accept LAN traffic. That has not been tested on the user's camera.
- The APK returns `http://192.168.122.1:8080/liveview/liveviewstream` from both live-view start methods and advertises `http://192.168.122.1:8080/sony` in its SSDP XML. Even a successful LAN API probe would leave an advertised-URL problem.
- Camera Web Companion's service uses port 8080 and returns `START_STICKY`; closing its activity does not stop that service. Restart the camera between Web Companion and Smart Remote tests so the two servers cannot be confused or conflict.

## First test without ADB or camera modifications

Use the existing working Camera Web Companion setup as the station-mode control. Keep the PC on the ordinary LAN/Ethernet throughout steps 1–3. The PC must **not** join `DIRECT-xxxx` during the LAN test.

1. Run Camera Web Companion on the a6000. Note the LAN address shown on its screen, for example `192.168.1.50`. From the PC, open `http://LAN_IP:8080/` in a browser and verify the page loads. Record whether the camera also appears in the router's currently connected clients list.
2. Power the camera off and on. This clears Web Companion's port-8080 service. Leave the PC connected to the normal LAN.
3. Launch the camera's **SonyLiveMonitor/Smart Remote Control** application and wait for its `DIRECT-xxxx:ILCE-6000` screen. Check the router's *active clients* list; a saved DHCP lease alone is not proof of a live connection. From Windows PowerShell, replace the example IP with the address recorded in step 1:

   ```powershell
   $cameraIp = '192.168.1.50'
   Test-NetConnection $cameraIp -Port 8080
   $api = "http://$($cameraIp):8080/sony/camera"
   $body = @{ method='getVersions'; params=@(); id=1; version='1.0' } | ConvertTo-Json -Compress
   Invoke-RestMethod -Uri $api -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 5
   ```

   `getVersions` is read-only. Record the `TcpTestSucceeded` value, the JSON response or exact error, whether the DIRECT SSID is visible, and whether the LAN client still appears active in the router. A failed ping alone is inconclusive; the TCP and API checks matter more.

4. Only after recording the LAN result, the PC may join the camera's DIRECT Wi-Fi and repeat the same `getVersions` request against `192.168.122.1`. A successful AP response confirms Smart Remote's API is operating; it does not prove anything about the LAN interface.

### Interpret the result

| Observation while Smart Remote runs | What it establishes | What remains open |
| --- | --- | --- |
| LAN `getVersions` returns Sony JSON | Remote API is reachable on LAN (case D for this firmware/session). | Whether live-view bytes can be fetched on LAN despite the hardcoded AP URL; sustained operation. |
| LAN IP still responds, but TCP 8080 is closed | Station connectivity may coexist with AP (B/C candidates). | Why the Remote API service is not reachable there; rule out a stale/different responder. |
| LAN IP disappears and router shows no active client | Smart Remote likely breaks the prior station connection (A in normal startup). | Whether the radio can rejoin station while Group Owner is running, or a small app change could bypass AP mode. |
| AP endpoint also fails | Smart Remote may not have started correctly. | Fix this control case before drawing any LAN conclusion. |

The first probe will not identify every interface or bind address. If the result is ambiguous, the next step is to enable ADB through OpenMemories: Tweak and observe interfaces, routes, listeners and processes before and after Smart Remote starts. Do not replace or patch a camera APK for this first test.

If the LAN API answers, try a second, separately controlled experiment: call `startLiveview`, record the returned URL, and request the same `/liveview/liveviewstream` path on `LAN_IP:8080`. Then test `monitor.py --endpoint http://LAN_IP:8080/sony/camera`; it may still fail because Smart Remote returns the AP host in the stream URL. A temporary desktop URL override would be a safe diagnostic before considering camera-side work.
