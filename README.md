# SonyLiveMonitor

Low-latency wireless monitor for the **Sony a6000** (and other cameras with the
Sony Camera Remote API) — a lightweight alternative to Imaging Edge.

Live view on your phone that **keeps running while the camera records video**,
plus in-app access to the camera's SD card so you can browse shots and pull
JPEG **or RAW/ARW** straight to your phone.

*[Léeme en español](README_es.md)*

---

## Quick start

**1. Patch the camera** — download the installer, connect the camera over USB,
press one button. No command line, no Python, no PMCA-RE setup.

| System | File |
|---|---|
| Windows | `SonyLiveMonitor-Installer-vX.Y-windows.exe` |
| macOS | `SonyLiveMonitor-Installer-vX.Y-macos.dmg` |
| Linux | `SonyLiveMonitor-Installer-vX.Y-linux` |

**2. Install the phone app** — `SonyLiveMonitor-vX.Y.apk` on Android, or build
the iOS app in Xcode.

**3. Connect** — open *Applications → SonyLiveMonitor* on the camera and join
its `DIRECT-xxxx:ILCE-6000` Wi-Fi from the phone.

All files are on the
[Releases page](https://github.com/otonielpv/SonyLiveMonitor/releases/latest).

📖 **[Quick install guide](docs/installer-guide.md)** — start here.
🔧 **[Manual guide](docs/a6000-live-monitor-guide.md)** — every step by hand, and
the reference if something fails.

> ⚠️ Replacing an in-camera app relies on reverse-engineered tools and is not an
> official Sony method. It is reversible: the installer ships Sony's original app
> and puts it back with one button. Use at your own risk.

---

## Components

| Piece | Where it runs | What it is |
|---|---|---|
| **Desktop installer** (`installer/`) | Windows / macOS / Linux | Detects the camera over USB and installs the patched Smart Remote |
| **Patched Smart Remote** (`camera-patches/`) | On the camera | Smart Remote with `avContent` enabled, so the card gallery and RAW download work |
| **Android app** (`android/`) | Android phone | The main monitor. Validated on a real a6000: ~25 fps, ~5 ms frame age |
| **iOS app** (`ios/`, SwiftUI) | iPhone | Full port of the Android app |
| **Python prototype** (root) | Desktop | Useful for diagnostics and development |

---

## Features

- **Full-screen live view** with a HUD (fps, frame age, dropped frames).
- **Live view keeps running while recording** — press MOVIE on the camera, or
  start recording from the app, and keep monitoring on the phone.
- **Exposure meter** computed from the live view: luminance histogram, EV
  deviation from mid-grey and clipping percentage. (Sony's API does not expose
  the camera's internal meter.)
- **Focus peaking** computed on the phone, with configurable colour and
  sensitivity — works with fully manual lenses too.
- **Framing grids**: thirds, thirds + diagonals, or centre cross.
- **Camera controls**: ISO, shutter, aperture, EV compensation, white balance,
  drive mode, flash, timer, powered zoom and shutter release. Available values
  are queried from the camera according to the mode dial.
- **Touch focus** by tapping the image (`setTouchAFPosition`).
- **Mirror preview** for filming yourself while watching the monitor. It only
  transforms the preview — the recording is never flipped — and touch focus is
  corrected automatically while active.
- **Tabbed control panel** (`Camera`, `View`, `App`) that keeps the live view
  size stable; the last tab is remembered.
- **Camera card gallery** (`avContent`): browse everything on the SD card,
  including shots taken with the physical shutter. Paged thumbnails, full-screen
  viewer with pinch-zoom and swipe between shots.
- **Download JPEG or RAW/ARW** with multi-select, a progress dialog and a
  choosable destination folder. Always an explicit action.
- **Optional phone GPS geotagging for full-resolution JPEG and Sony ARW.** Enable
  `Location` before shooting. While connected, Sony camera events freeze the
  latest phone position at the instant of a physical or in-app shutter release;
  downloaded files are then matched by capture time and receive standard GPS
  metadata without resizing or recompressing image data.
  Files on the camera card are never modified, and a download is left unchanged
  when no recent location matches it.
- **Delete from the card** with a second confirmation, where the camera reports
  API support.
- **Automatic reconnection**, including re-binding to the active Wi-Fi.

Android saves to `Download/SonyLiveMonitor`; iOS saves to the Files app under
*Sony Live Monitor*. Either can be pointed at a folder you pick.

---

## How it works

In **Smart Remote Control** mode the camera creates a Wi-Fi access point and
exposes a JSON-RPC API. The app:

1. Discovers the endpoint over SSDP (or uses
   `http://192.168.122.1:8080/sony/camera`).
2. Calls `startRecMode` + `startLiveview` to get the stream URL.
3. Reads the JPEG frame stream over a raw socket (`TCP_NODELAY`) on a dedicated
   thread that **keeps only the most recent frame** — stale frames are dropped
   rather than queued, which is what avoids accumulated lag.
4. Renders with the frame age and drop count on screen.

---

## Building from source

### Android

```
cd android
gradle :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Release APKs attached to `v*` tags are signed with a stable key so Android
allows upgrades. Configure these GitHub Actions secrets:
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`,
`ANDROID_KEY_PASSWORD`.

> Keep that key. If it is lost or changed, Android will require uninstalling the
> previous version first. APKs published earlier as `debug` use a different
> signature and also need one uninstall before the first stable release.

### iOS

Open `ios/SonyLiveMonitor.xcodeproj` in Xcode, set your signing Team under
*Signing & Capabilities*, select your iPhone and Run. With a free account you
must trust the profile on the phone the first time
(*Settings → General → Device Management*).

### Desktop installer

See [`installer/README.md`](installer/README.md). Note that PMCA-RE is **not**
pip-installable and must be cloned:

```
git clone --branch v0.18 https://github.com/ma1co/Sony-PMCA-RE.git installer/pmca-re
pip install -r installer/requirements.txt
python installer/installer.py
```

### Python prototype

```
pip install -r requirements.txt
python monitor.py
```

| Option | Description |
|---|---|
| `--endpoint URL` | Skip SSDP discovery (faster start) |
| `--size L` | Request a larger live view if the camera supports it |
| `--scale 2` | Window scale factor (default 2x) |
| `--no-hud` | Hide the fps/latency overlay |

Quit with `q` or `ESC`.

- `sony_camera.py` — SSDP discovery and JSON-RPC API client.
- `liveview_stream.py` — live view container parser with the "latest frame only"
  strategy.
- `monitor.py` — display window with the performance HUD.

---

## iOS differences

- You must join the camera's `DIRECT-xxxx` network from *Settings → Wi-Fi*
  before using the app; iOS cannot do it programmatically. The **Wi-Fi** button
  shows the instructions.
- iOS asks for **Local Network** permission the first time — it must be allowed
  or the camera is unreachable.

---

*SonyLiveMonitor is an independent project and is not affiliated with or
endorsed by Sony. "Sony" and "a6000" are trademarks of their respective owner.
The installer builds on [PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) (MIT)
by ma1co.*
