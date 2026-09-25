# Desktop webcam and infrastructure Wi-Fi investigation

Source baseline: upstream `59e967c` (v0.11), inspected 2026-09-25. Findings below distinguish source evidence from behavior that needs an a6000. Camera APK observations come from a read-only JADX decompilation of the bundled APK; JADX reported six decompilation errors, so individual methods still need hardware confirmation.

## Current architecture

| Component | Role |
| --- | --- |
| `camera-patches/*.apk` | Prebuilt original and modified Sony Smart Remote Control APKs installed on the camera. The repository has no source or patch recipe for the modified camera APK. The documented patch enables `avContent` for gallery/RAW access. |
| `installer/` | Python/Tk desktop installer, using Sony-PMCA-RE to install/restore the camera APK over USB. Optional ADB backup of the camera's own original APK. It is not the desktop monitor. |
| `android/` | Kotlin/Android phone monitor, API client, own live-view parser, controls, gallery and optional HDMI/UVC capture. |
| `ios/` | SwiftUI/iPhone/iPad monitor with corresponding API client and parser. |
| `sony_camera.py`, `liveview_stream.py`, `monitor.py` | Independent Python desktop prototype. Requires only root `requirements.txt`; the installer and phone apps are not needed to run it. |

There is no `CONTRIBUTING` or project license file, and GitHub reports no declared license. The repository has no current issues or open pull requests as of the inspection. Clarify contribution and redistribution terms with the maintainer before treating a fork as a freely redistributable project, particularly for the bundled Sony APKs.

### Exact desktop frame path

1. On the a6000, open the installed Smart Remote/SonyLiveMonitor camera application. Its documented behavior is to create `DIRECT-xxxx:ILCE-6000`; the desktop joins this Wi-Fi network (`README.md`, `docs/a6000-live-monitor-guide.md`). The repository has no camera source or patch recipe, but its bundled DEX can be inspected read-only (see below).
2. `monitor.py:main` constructs `SonyCamera`. `sony_camera.py:discover_endpoint` sends Sony ScalarWebAPI SSDP M-SEARCH to `239.255.255.250:1900`, fetches the response's `LOCATION` XML through `_endpoint_from_description`, and appends `/camera` to its ActionList URL. On timeout it falls back to `http://192.168.122.1:8080/sony/camera`. `--endpoint` bypasses discovery, so an arbitrary reachable API URL is already configurable.
3. `SonyCamera.call` POSTs Sony JSON requests (`method`, `params`, `id`, `version`) to `/sony/camera`. `SonyCamera.start_liveview` attempts `startRecMode`, then optionally `startLiveviewWithSize`, then `startLiveview`. The returned URL is the live-view stream endpoint.
4. `monitor.py:main` passes that URL to `LiveviewStream.start`. `LiveviewStream._connect` opens a TCP socket, enables `TCP_NODELAY`, issues HTTP GET and detects `Transfer-Encoding: chunked`.
5. `LiveviewStream._fill`, `_raw_readline` and `_read_exact` remove HTTP chunk framing. `_reader` parses the Sony 8-byte common header and 128-byte payload header, reads JPEG plus padding, ignores non-image payload types, and stores a `Frame(jpeg, sequence, received_at)`.
6. The reader owns one `_latest` slot. Replacing an unconsumed frame increments `frames_dropped`. `poll_frame` removes the newest frame; there is no growing application frame queue.
7. `monitor.py:main` decodes JPEG bytes with `cv2.imdecode(np.frombuffer(...), cv2.IMREAD_COLOR)` to a `uint8` BGR NumPy array, optionally scales and draws a HUD, then displays it with `cv2.imshow`/`waitKey`. `Frame.received_at` is when the JPEG finished arriving, so the HUD's frame age is **not** camera-to-screen latency.

The desktop client has no shutter or exposure UI. Its generic `SonyCamera.call` can issue commands, while `SonyCamera.start_liveview`/`stop_liveview` are its only dedicated controls. Android implements the controls in `MainActivity.kt` through `SonyCamera.kt:call`: `settings` maps ISO, shutter and aperture to `setIsoSpeedRate`, `setShutterSpeed`, `setFNumber`; `takePicture` calls `actTakePicture` or `startMovieRec`/`stopMovieRec`. iOS does the same in `MonitorViewModel.swift` via `SonyCamera.swift:call`. Available settings depend on the camera's mode and reported API capabilities.

The mobile implementations have their own parsers (`android/.../LiveviewStream.kt:parseContainer`; `ios/SonyLiveMonitor/LiveviewStream.swift:parseContainer`) and JPEG decoders (`BitmapFactory.decodeByteArray`; `UIImage(data:)`). Android `MainActivity.bindToWifi` binds its process to Wi-Fi and its Connect action joins the DIRECT SSID. iOS uses a fixed `192.168.122.1` API URL and instructs the user to join DIRECT manually. These are mobile app assumptions, not restrictions in the Python parser.

## Webcam feasibility

**High for software integration. Hardware validation outstanding.** The Python path already yields BGR `uint8` arrays. `pyvirtualcam.Camera(..., fmt=PixelFormat.BGR)` accepts these directly and supports Windows OBS and Unity Capture virtual camera backends, macOS OBS, and Linux `v4l2loopback`. The backend may internally convert to its native pixel format, but the application needs no extra JPEG encode/decode or RGB conversion. Windows users need OBS installed for its virtual camera driver, or Unity Capture. OBS' single virtual camera cannot simultaneously be fed by Python and used as OBS' own mixed output; Unity Capture is an option for that workflow.

Use the first valid decoded frame to select output width/height. Neither `monitor.py` nor the stream parser fixes a live-view size. The APK's `LiveviewContainer` sets default `M` width to 640 pixels and `L` width to 1024 pixels (with a VGA-only exception); the actual output height and active size still need measurement. That class initializes a frame-rate field to `30000` (apparently a 30 fps target in milli-fps), while the project reports about 25 received fps on an a6000. Actual fps may vary with camera state, Wi-Fi quality, shooting and capture pauses. Start with a nominal 25 fps virtual output. Keep a latest-frame-only slot through the existing parser, decode each new JPEG once, and repeat the last image at the output cadence during short gaps. After a prolonged gap, send a black frame so consumers do not mistake a frozen image for live video. Preserve simultaneous preview as an option. On disconnect, report the failure and release the virtual device cleanly; automatic reconnection can follow after hardware testing.

The smallest useful CLI is `monitor.py --webcam`, with the existing `--endpoint` for a manual LAN API URL and an optional `--no-preview` for headless operation. A new `webcam.py` would duplicate connection and frame loop logic; a focused mode in `monitor.py` can share both. Later options can add output fps and resize only if measurements show a need.

## Infrastructure/client Wi-Fi feasibility

**The a6000 can join an infrastructure access point in at least some camera application states, but Remote API reachability in that state is unproven.** OpenMemories: Tweak `DeveloperActivity.java` uses Android `WifiManager.setWifiEnabled` and a Sony Wi-Fi settings activity, displays connected SSID/IP, and its README says Enable Wifi connects the camera to an access point. Its telnet daemon can be reached over that connection. This establishes station-mode capability, not simultaneous Smart Remote operation.

Sony-PMCA-RE defines `GetWifiAPInfo`, `SetWifiAPInfo`, `GetMultiWifiAPInfo`, `SetMultiWifiAPInfo` in `pmca/usb/sony.py` and a USB `wifiCommand` in `pmca/commands/usb.py`. Their docstrings identify saved **live-streaming access-point configuration**; these APIs are not evidence that Smart Remote uses infrastructure mode, and writing settings is unnecessary for the first experiments. OpenMemories: Tweak issue [#218](https://github.com/ma1co/OpenMemories-Tweak/issues/218) requests this exact multi-Wi-Fi Remote API capability and contains no solution. Its mention of QX1 multi-camera mode does not establish a6000 support.

### Camera APK findings

Read-only decompilation of `camera-patches/SonyLiveMonitor-a6000-avcontent.apk` identifies the responsible camera app path (these are DEX class names, **not** source files in this repository):

- `com.sony.imaging.app.srctrl.SRCtrlRootState.onResume` disables Wi-Fi if already enabled, then reenables it after the disabled event. `handleWifiStateChanged` enables Wi-Fi Direct, `handleDirectStateChanged` calls `startGroupOwner`, and that calls `WifiP2pManagerFactory.IWifiP2pManager.startGo`. The Jelly Bean implementation calls Android `WifiP2pManager.createGroup`; the Gingerbread implementation calls Sony `DirectManager.startGo`. This is an explicit AP/Group Owner startup path in Smart Remote, not merely a desktop assumption.
- `SRCtrlRootState.handleGroupCreateSuccess` starts both SSDP device-description and web-server services **after** Group Owner creation. `NetworkRootState.onResume` requires Wi-Fi Direct enabled and the local device in Group Owner mode outside initial setup. Avoiding AP creation may therefore need camera-app lifecycle changes, not just changing a network setting.
- `com.sony.imaging.app.srctrl.webapi.service.OrbAndroidServiceEx.onBind` registers `/sony/camera` and `/liveview/liveviewstream` on port 8080. Its `ServerBuilder` defaults to host `0.0.0.0`, and this call does not override the host. That suggests the HTTP server may accept LAN traffic *if* a station interface coexists and the server starts, but Android/Sony network routing and firewall behavior are untested.
- `com.sony.imaging.app.srctrl.util.SRCtrlConstants.LIVEVIEW_URL` is hardcoded to `http://192.168.122.1:8080/liveview/liveviewstream`; both `startLiveview` and `startLiveviewWithSize` return it through `SRCtrlServlet`. The bundled `assets/scalarwebapi_template_dd.xml` also advertises `http://192.168.122.1:8080/sony`. The original APK has these same AP URLs. Even if a LAN POST to `/sony/camera` works, returned URLs and SSDP discovery can still point to the AP address. A client-side URL rewrite could be a reversible diagnostic, but the camera's advertised URLs need a proper solution for general LAN use.

This establishes that Smart Remote explicitly resets Wi-Fi and requests AP/Group Owner mode, so **A is strongly suggested for the normal startup path** and **E is not required to explain that path**. It does **not** prove that station mode cannot coexist after startup, nor whether the API is reachable via LAN (**B/C/D remain hardware questions**). A/B are not perfectly exclusive as phrased: the app can request AP mode while the platform still preserves a station interface. The Python client can already use a LAN API endpoint via `--endpoint`, but the hardcoded returned live-view URL is a concrete LAN obstacle.

### Safe a6000 experiment sequence

1. Back up the camera's original Smart Remote APK using the documented ADB procedure before replacing any installed camera app. Record model, firmware and app versions. Do not modify firmware or saved Wi-Fi configuration for initial diagnostics.
2. With OpenMemories: Tweak Enable Wifi active and Smart Remote **closed**, record station SSID, LAN IP, interfaces (`ip addr` or `ifconfig`), routes (`ip route` or `route`), process list and TCP listeners (`ss -ltnp`, `netstat -ltnp`, or `/proc/net/tcp`, depending on camera tools). Record ADB and telnet availability.
3. Start Smart Remote. Observe whether the station IP and route persist, whether DIRECT appears, whether a second interface/address appears, and whether the service processes/ports change. Repeat the interface and listener snapshots. This distinguishes station replacement from possible coexistence, but a listening socket alone does not prove external reachability.
4. From a desktop **remaining on the normal LAN**, check router client list/ARP, ping where supported, TCP 8080/5555, then POST harmless `getVersions` to `http://LAN_IP:8080/sony/camera`. Try SSDP M-SEARCH on that interface. If the API answers, call `startRecMode` and `startLiveview`, inspect the returned URL and attempt a short GET of live-view bytes. If it returns the hardcoded AP URL, try the same path on `LAN_IP:8080` directly as a diagnostic; do not infer from this alone that SSDP or all API responses are LAN-ready.
5. Only after endpoint reachability is proven, run `monitor.py --endpoint http://LAN_IP:8080/sony/camera` and the webcam mode. Observe stream survival, controls while streaming, movie recording, and disconnect/reconnect. Measure actual camera-to-output latency (e.g. filmed clock/LED in the scene), frame cadence, losses and router-vs-DIRECT paths under comparable conditions.

If station drops when Smart Remote starts, correlate logcat and process transitions with the identified `SRCtrlRootState` Wi-Fi reset and group-owner startup; examine Sony framework/native effects and actual server bind addresses. There is no basis yet for asserting a small APK patch will work: service startup is tied to group creation, the returned URLs are fixed to AP IP, and the radio/platform may not support concurrent operation. Any experiment that replaces an APK needs an original backup and a separately reviewable patch source; no binary patch was attempted here.

Example read-only API probe once `LAN_IP` is known (replace the placeholder):

```sh
curl --max-time 5 -H 'Content-Type: application/json' \
  -d '{"method":"getVersions","params":[],"id":1,"version":"1.0"}' \
  http://LAN_IP:8080/sony/camera
```

For LAN discovery, manual `--endpoint` (or a later `--camera-ip` convenience option) is enough for a prototype, but the returned live-view URL may require a diagnostic LAN-host rewrite. Existing SSDP discovery may receive a LAN response yet parse the hardcoded AP endpoint from the XML. Fix the advertisement or validate a client-side override before adding mDNS or subnet scans; neither is evidenced in this repository.

## Implementation and contribution plan

1. Fork with history intact. Put webcam support on `feature/desktop-webcam`. Add an optional `pyvirtualcam` dependency, a small `monitor.py` mode and usage notes. Keep the default monitor behavior intact. Test parser/decode/output with synthetic frames where practical and verify the real Windows virtual device with an a6000 and OBS/Discord/browser. This can be one upstream PR.
2. Put LAN observations and any eventual camera networking work on a separate `research/infrastructure-wifi` or `feature/infrastructure-wifi` branch. Test station reachability and the returned URL first. If API and stream work on LAN, discovery/URL handling may be a small desktop follow-up PR. Camera-side changes would involve at least `SRCtrlRootState` lifecycle logic and `SRCtrlConstants`/description URLs; recreate changes from reviewable source and obtain licensing/maintainer guidance before distributing an APK. Keep this out of the webcam PR.

Webcam files in this prototype: `monitor.py`, `requirements-webcam.txt`, `README.md`, and this report. Existing `sony_camera.py` and `liveview_stream.py` need no planned change. Network work may later touch `sony_camera.py` for discovery/URL handling; the candidate camera-side classes are identified above but have no source files in this repository.

Prototype validation in this checkout: Python dependencies installed in an isolated environment; `monitor.py` compiles and its CLI help works. A local simulated Sony JSON API and chunked live-view stream carried JPEG frames through the real `SonyCamera`, `LiveviewStream`, OpenCV decoder and webcam mode into a mock virtual-camera backend, with BGR pixels verified. There is no connected a6000, Windows host or local `v4l2loopback` device here, so selection by Discord/OBS/Zoom and real performance are **not verified**.

Risk levels: the Python virtual-camera integration is straightforward; real a6000 stream geometry, cadence and Windows backend compatibility require device testing; infrastructure Remote API access is experimental; altering the camera APK or Sony networking service is reverse engineering with unknown effort; simultaneous AP and station mode or LAN-facing Smart Remote may be unsupported on this hardware/firmware. The missing repository license and proprietary APKs are separate upstream contribution/distribution questions.

## References

- SonyLiveMonitor `README.md`, `docs/a6000-live-monitor-guide.md`, `sony_camera.py`, `liveview_stream.py`, `monitor.py`, and mobile sources cited above, baseline `59e967c`.
- [OpenMemories: Tweak README](https://github.com/ma1co/OpenMemories-Tweak/blob/master/README.md) and [`DeveloperActivity.java`](https://github.com/ma1co/OpenMemories-Tweak/blob/master/app/src/main/java/com/github/ma1co/openmemories/tweak/DeveloperActivity.java).
- [Sony-PMCA-RE USB Wi-Fi command](https://github.com/ma1co/Sony-PMCA-RE/blob/master/pmca/commands/usb.py) and [USB command definitions](https://github.com/ma1co/Sony-PMCA-RE/blob/master/pmca/usb/sony.py).
- [pyvirtualcam documentation](https://github.com/letmaik/pyvirtualcam/blob/main/README.md) and API source, release 0.15.0 at inspection.
