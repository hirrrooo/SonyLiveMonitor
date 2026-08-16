# Release notes

## v0.9

**Fixed**

- **Stable long iOS sessions** — live-view frames and HTTP chunks now drain
  temporary Foundation, UIKit and ImageIO objects continuously instead of
  retaining them for the lifetime of the monitor thread. Meter updates are
  coalesced with video updates so a temporary UI slowdown cannot build a queue.
- **Safe stop and resume on Android and iOS** — every monitor run has a unique
  generation and owns an explicitly tracked stream. Going to the background,
  opening the camera-card gallery or returning quickly can no longer leave an
  older socket and rendering thread running alongside the new session.
- **Lower-cost focus peaking** — iOS now reuses its full-resolution Sobel buffers
  and uses 32-bit gradients; Android uses compact luminance and gradient buffers.
  Both platforms sample peaking at about 8 fps while keeping the live view at its
  normal frame rate, reducing allocation pressure, memory bandwidth and heat.
- **Faster iOS stream parsing** — chunked HTTP data is appended directly from the
  socket buffer, avoiding an extra temporary `Data` allocation for every chunk.

**Notes**

- The grid and exposure meter remain available at the same quality. Focus
  peaking still runs at full image resolution; only its refresh cadence changed.
- The patched camera APK is unchanged. Installers are republished so every
  downloadable asset remains available together under the same release.

**Downloads**

- `SonyLiveMonitor-Installer-v0.9-windows.exe` — desktop installer (Windows).
- `SonyLiveMonitor-Installer-v0.9-macos.dmg` — desktop installer (macOS).
- `SonyLiveMonitor-Installer-v0.9-linux` — desktop installer (Linux).
- `SonyLiveMonitor-v0.9.apk` — Android phone app.
- `SonyLiveMonitor-v0.9-unsigned.ipa` — iOS, sideload with AltStore.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — unchanged patched
  camera app (do **not** install it on the phone).
- `SmartRemote-a6000-original-v4.30.apk` — Sony's original camera app.

## v0.8

**New**

- **One-click desktop installer for Windows, macOS and Linux** — patching the
  camera no longer needs the command line, Python, PMCA-RE or ADB. Connect the
  camera in *Mass Storage* mode, press **Install on camera**, done. The
  installer detects the camera, shows the model and handles the whole process,
  including the reboot into app-install mode.
- **One-button undo** — the installer ships Sony's original *Smart Remote
  Control* (v4.30) and reinstalls it with **Restore original**. This works
  offline and needs no backup of your own. The patched app uses a different
  package name, so both apps coexist on the camera and you choose which to open.
- **Update in place** — running a newer installer over an existing install
  simply replaces it. The button reads *Update / reinstall* when the app is
  already on the camera.
- **Optional ADB backup** — a checkbox still saves the APK from *your* camera to
  disk, discovering the camera's IP on the network by itself.
- **English README and a new quick-install guide**
  ([`docs/installer-guide.md`](installer-guide.md)). The Spanish README moved to
  `README_es.md`; the manual step-by-step guide is unchanged and remains the
  reference if anything fails.

**Notes**

- Validated end to end on a real a6000: detection, install and restore.
- Installer filenames now carry the version (for example
  `SonyLiveMonitor-Installer-v0.8-windows.exe`), which is always the version of
  the camera app they install.
- The installer is self-contained: it carries the camera APKs inside and works
  without an internet connection. Use the installer from the same release as the
  phone app.
- The binaries are not code-signed. Windows SmartScreen shows a warning
  (*More info → Run anyway*); on macOS use right-click → *Open* the first time.
  On Linux, `chmod +x` first, and USB access may need `sudo` or a udev rule.
- The phone apps are unchanged in this release.

**Downloads**

- `SonyLiveMonitor-Installer-v0.8-windows.exe` — desktop installer (Windows).
- `SonyLiveMonitor-Installer-v0.8-macos.dmg` — desktop installer (macOS).
- `SonyLiveMonitor-Installer-v0.8-linux` — desktop installer (Linux).
- `SonyLiveMonitor-v0.8.apk` — Android phone app.
- `SonyLiveMonitor-v0.8-unsigned.ipa` — iOS, sideload with AltStore.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — patched camera app,
  installed for you by the installer (do **not** install it on the phone).
- `SmartRemote-a6000-original-v4.30.apk` — Sony's original camera app, for
  restoring by hand if you ever need to.

## v0.7

**New**

- **Mirror preview on Android and iOS** — the live monitor can now be flipped
  horizontally for selfie/vlogging use. It affects only the phone preview, not
  the camera recording. Focus peaking follows the mirrored image and touch-focus
  coordinates remain accurate at every screen rotation.
- **Scalable tabbed controls** — the panel is split into *Camera*, *View* and
  *App* groups instead of showing every control at once. The selected tab is
  remembered and the layout continues to adapt between portrait and landscape.
- **Modern control design** — compact rounded cards, a segmented tab selector,
  clear green active states and a circular floating shutter replace the legacy
  platform buttons. Every tab reserves the same panel size, so switching groups
  no longer makes the live-view image resize.

**Notes**

- Mirror mode and the selected control tab are persisted independently on each
  device.
- This update only changes the Android and iOS phone apps. The patched camera APK
  used for card browsing and RAW support is unchanged.

**Downloads**

- `SonyLiveMonitor-v0.7.apk` — Android phone app.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — unchanged patched
  camera app (install on the **camera** with PMCA-RE, not on the phone).
- `SonyLiveMonitor-v0.7-unsigned.ipa` — iOS, sideload with AltStore.

See the [install guide](https://github.com/otonielpv/SonyLiveMonitor/blob/main/docs/a6000-live-monitor-guide.md).

---

## v0.6

**Improved**

- **Sharper focus peaking on Android and iOS** — the edge highlight is now a thin
  ~1px line, closer to the camera's own peaking, instead of a thick band. Edge
  detection runs at full resolution and keeps only the crest of each edge
  (non-maximum suppression), so soft, out-of-focus transitions between differently
  coloured areas are no longer marked. The result is more precise and less noisy.

**Notes**

- Sensitivity thresholds were recalibrated for the full-resolution processing; the
  low/medium/high levels behave as before but are more selective about what counts
  as an in-focus edge.
- This update only changes the Android and iOS phone apps. The patched camera APK
  used for card browsing and RAW support is unchanged.

**Downloads**

- `SonyLiveMonitor-v0.6.apk` — Android phone app.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — unchanged patched
  camera app (install on the **camera** with PMCA-RE, not on the phone).
- `SonyLiveMonitor-v0.6-unsigned.ipa` — iOS, sideload with AltStore.

See the [install guide](https://github.com/otonielpv/SonyLiveMonitor/blob/main/docs/a6000-live-monitor-guide.md).

---

## v0.5

**New**

- **Delete from camera card on Android and iOS** — select one or more photos in
  *Camera card*, or open an individual photo, and permanently delete it after an
  explicit confirmation. The button is shown only when the camera reports
  `deleteContent` support.

**Notes**

- Deleting a photo removes its associated files from the camera card and cannot
  be undone. Protected files that the camera refuses to delete remain on the card.
- This update only changes the Android and iOS phone apps. The patched camera APK
  used for card browsing and RAW support is unchanged.

**Downloads**

- `SonyLiveMonitor-v0.5.apk` — Android phone app.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — unchanged patched
  camera app (install on the **camera** with PMCA-RE, not on the phone).
- `SonyLiveMonitor-v0.5-unsigned.ipa` — iOS, sideload with AltStore.

See the [install guide](https://github.com/otonielpv/SonyLiveMonitor/blob/main/docs/a6000-live-monitor-guide.md).

---

## v0.4

**New**

- **Focus peaking on Android and iOS** — edge highlighting is calculated from
  the live-view frames entirely on the phone, so it also works with vintage
  manual-focus lenses and requires no further camera-app patch. The control
  offers red, yellow and white overlays plus low, medium and high sensitivity.
- Peaking settings are remembered independently on each device. Processing is
  performed on a reduced-resolution mask and rate-limited to preserve the
  low-latency, latest-frame rendering strategy.
**Fixed**

- **Photo viewer pan on Android and iOS** — dragging a zoomed image now tracks
  the finger at the expected speed and stops at the actual image edges instead
  of feeling damped or allowing the photo to drift off-screen.
- Android now uses an image matrix for pinch zoom, keeping the point beneath
  the fingers stable and avoiding gesture jitter on devices such as the Oppo A5.

**Notes**

- Focus peaking runs entirely in the phone app. It works with the stock Smart
  Remote camera app and does not require reinstalling or updating the patched
  camera APK.

**Downloads**

- `SonyLiveMonitor-v0.4.apk` — Android phone app.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — unchanged patched
  camera app for card browsing/RAW support (install on the **camera** with
  PMCA-RE, not on the phone).
- `SonyLiveMonitor-v0.4-unsigned.ipa` — iOS, sideload with AltStore.

See the [install guide](https://github.com/otonielpv/SonyLiveMonitor/blob/main/docs/a6000-live-monitor-guide.md).

---

## v0.3

**New**

- **Link health monitor in the HUD** — a second HUD line tells you whether low
  fps are caused by the WiFi link or the camera, colour-coded (green / amber /
  red). On Android it shows the WiFi RSSI (dBm) and link speed; on iOS (where
  Apple blocks RSSI) it shows a link-health estimate from frame gaps and drops.
- **Camera diagnostics** — a *Diagnostics* button produces a shareable report of
  what the connected camera supports, on both Android and iOS. Handy for testers
  on unverified models.
- **Camera capability detection** — the app reads the camera's available API
  and hides controls a body genuinely doesn't support, so it behaves better
  across different Sony models (a6000, a6300, …).

**Fixed**

- **a6000 regression** where zoom, touch focus and the *Camera card* button
  could disappear: the a6000 reports an incomplete API list, so those methods
  are now always assumed available (each already fails safely on its own).

**Notes**

- The *Camera card* button appears on all cameras, but browsing the SD card and
  downloading RAW only work if the patched camera app
  (`SonyLiveMonitor-a6000-avcontent.apk`, installed on the camera via PMCA-RE)
  is in use. Zoom and touch focus work with the stock Smart Remote too.

**Downloads**

- `SonyLiveMonitor-v0.3.apk` — Android phone app.
- `SonyLiveMonitor-a6000-avcontent-ONLY-FOR-CAMERA.apk` — patched camera app
  (install on the **camera** with PMCA-RE, not on the phone).
- `SonyLiveMonitor-v0.3-unsigned.ipa` — iOS, sideload with AltStore.

See the [install guide](https://github.com/otonielpv/SonyLiveMonitor/blob/main/docs/a6000-live-monitor-guide.md).

---

## v0.2

**New**

- **Camera card gallery** — browse the camera's SD card from the app (including
  shots taken with the physical shutter), with a full-screen viewer (pinch to
  zoom, swipe between photos).
- **JPEG / RAW download** to the phone — single or multi-select, with a centered
  progress dialog that blocks the screen until it finishes.
- **iOS parity** — the whole gallery + download flow ported to the iOS app.

**Requires** the patched camera app (`avContent` enabled) for the gallery/RAW
features.

---

## v0.1

- Initial release: low-latency wireless live-view monitor for the Sony a6000
  (Android + iOS), with HUD, grids, exposure meter, camera controls, touch
  focus, powered zoom and a draggable floating shutter.
