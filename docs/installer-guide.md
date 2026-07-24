# Sony a6000 — Wireless Live Monitor: quick install

**Turn your Sony a6000 into a wireless monitor in a few minutes.** Connect the
camera, press one button, done. No command line, no Python, no PMCA‑RE setup.

This is the easy path. If you prefer doing every step by hand — or something
here fails — see the
[manual guide](a6000-live-monitor-guide.md).

> ⚠️ **Not an official Sony method.** This replaces an in‑camera app using
> reverse‑engineered tools. It is reversible: the installer ships Sony's
> original app and can put it back with one button. Do this at your own risk.

---

## What you need

- A **Sony a6000** (ILCE‑6000) with *Smart Remote Control* installed.
- A computer with **Windows, macOS or Linux**.
- A **USB data cable** — many cheap cables only carry power and will not work.
- An **Android phone or iPhone** for the monitor app itself.

You do **not** need Python, PMCA‑RE, ADB or OpenMemories: Tweak. The installer
carries everything inside.

---

## Step 1 — Download the installer

From the [Releases page](https://github.com/otonielpv/SonyLiveMonitor/releases/latest):

| System | File |
|---|---|
| Windows | `SonyLiveMonitor-Installer-vX.Y-windows.exe` |
| macOS | `SonyLiveMonitor-Installer-vX.Y-macos.dmg` |
| Linux | `SonyLiveMonitor-Installer-vX.Y-linux` |

The `vX.Y` in the filename is **the version of the camera app it installs**, so
it always matches the phone app published alongside it in the same release.

Grab the phone app from the same page while you are there:

- **Android:** `SonyLiveMonitor-vX.Y.apk`
- **iOS:** build from source in Xcode, or sideload the unsigned IPA with AltStore.

> **Careful with the two APKs.** `SonyLiveMonitor-vX.Y.apk` goes on your
> **phone**. The one with `avcontent` in the name is for the **camera** and the
> installer handles it for you — you never install that one by hand.

### First‑run notes

- **Windows:** SmartScreen may warn that the app is unrecognised — the binary is
  not code‑signed. Choose *More info → Run anyway*.
- **macOS:** right‑click the app → **Open** the first time (it is not signed
  with an Apple developer account).
- **Linux:** make it executable first, and you may need `sudo` for USB access:

  ```
  chmod +x SonyLiveMonitor-Installer-*-linux
  ./SonyLiveMonitor-Installer-*-linux
  ```

---

## Step 2 — Connect the camera

1. Turn the camera **on**, with a charged battery and an SD card inserted.
2. Set **MENU → Setup → USB Connection → Mass Storage**.
3. Connect it with the USB **data** cable.
4. Close anything that might grab the camera: Imaging Edge, PlayMemories,
   Photos, Dropbox, Google Drive.

Also worth setting: **MENU → Setup → Power Save Start Time → 30 min**, so the
camera does not fall asleep mid‑install.

---

## Step 3 — Install

Open the installer. It looks for the camera on its own and shows the model when
it finds one.

```
┌──────────────────────────────────────────┐
│  Sony Live Monitor                       │
│  Install the patched Smart Remote…       │
│                                          │
│  ● Camera detected: ILCE-6000            │
│    Ready to install.       [Search again]│
│                                          │
│  ▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░                   │
│                                          │
│  [ Install on camera ]  [Restore original]│
└──────────────────────────────────────────┘
```

Press **Install on camera** and confirm. The camera will disconnect and
reconnect on its own partway through — that is normal, do not unplug it.

When it finishes: **restart the camera**, then open
**Applications → SonyLiveMonitor**.

---

## Step 4 — Connect your phone

The camera app creates a Wi‑Fi hotspot called `DIRECT-xxxx:ILCE-6000`.

**Android** — install `SonyLiveMonitor-vX.Y.apk`, open it and tap **Connect**.
It joins the camera's Wi‑Fi and starts live view, and reconnects by itself
afterwards.

**iOS** — iOS cannot join a network programmatically, so join it once by hand:
**Settings → Wi‑Fi → `DIRECT-xxxx:ILCE-6000`**, using the password shown on the
camera. Then return to the app and allow the **Local Network** permission the
first time, or the camera will be unreachable.

That's it — you now have live view on your phone, and it keeps running while
the camera records video.

---

## Updating to a newer version

When a new release comes out, download the new installer and run it exactly as
before. The button will read **Update / reinstall** because the installer notices
the app is already on the camera.

Installing over the top is the normal way to update — the new version simply
replaces the old one. Your photos, camera settings and the phone app are not
affected. There is no need to uninstall anything first or to restore the
original app in between.

Remember to update the **phone app** too (`SonyLiveMonitor-vX.Y.apk` from the
same release), since the two work together.

> **Always use the installer from the same release as the app.** Each installer
> carries its own copy of the camera app inside, so an older installer will
> install an older app. Downloading the newest installer is what gets you the
> newest app.
>
> The camera reports the app's version as `4.30` no matter which release you
> have — the patched app inherits that number from Sony. So the installer cannot
> tell you whether the copy on your camera is older or newer than the one it
> carries. When in doubt, just install: it is harmless.

---

## Going back

Press **Restore original**. The installer ships Sony's stock *Smart Remote
Control* (v4.30), so this works offline and needs no backup of your own.

The patched app uses a different package name
(`mod.sony.imaging.app.srctrl` instead of `com.sony.imaging.app.srctrl`), so
**both apps coexist** on the camera. Restoring does not uninstall anything —
you simply pick which one to open from the *Applications* menu.

### Keeping a copy of your own app (optional)

The **Back up via ADB** checkbox saves the APK from *your* camera to disk. It is
no longer essential, but it is there if your camera runs a version other than
4.30 and you want to preserve it exactly.

It needs ADB enabled on the camera, which is a manual step: install
*OpenMemories: Tweak*, then **Applications → OpenMemories: Tweak → Developer →
Enable Wi‑Fi + Enable ADB**, and connect your computer to the camera's Wi‑Fi.
From there the installer finds the camera and pulls the APK by itself.

---

## If something goes wrong

Open **▸ Show details** in the installer — the full log is there, and it is the
first thing to look at.

**"No camera detected"** — this is the most common one, and it is almost always
the cable or the USB mode. Check that **USB Connection** really is set to *Mass
Storage*, try a different USB port, and try another cable if you have one:
charge‑only cables are extremely common and look identical. If it still does not
show up, unplug it, turn the camera off and on, and reconnect.

**The camera is found but installing fails** — close Imaging Edge / PlayMemories
and any photo or cloud app, then unplug and reconnect the camera. Something else
on the computer may have claimed the device.

**"The camera did not reconnect in time"** — the camera reboots into install
mode partway through and this can occasionally be slow. Unplug it, plug it back
in and press **Install on camera** again.

**"No USB driver available (libusb not found)"** — only expected on Linux
(`sudo apt install libusb-1.0-0`) or macOS (`brew install libusb`). On Windows,
connecting in *Mass Storage* mode avoids needing it at all.

**The camera app shows the wrong icon, or nothing works** — press **Restore
original** and try the install again.

---

## Advanced: command line

The same executable works headless, which is handy for scripting or debugging:

| Option | What it does |
|---|---|
| `--console` | Text mode instead of the window |
| `--restore` | Reinstall Sony's original Smart Remote |
| `-y` | Skip the confirmation prompt |
| `--selftest` | Check that the bundled APKs and PMCA‑RE are present |

---

*SonyLiveMonitor is an independent project and is not affiliated with or
endorsed by Sony. "Sony" and "a6000" are trademarks of their respective owner.
The installer builds on [PMCA‑RE](https://github.com/ma1co/Sony-PMCA-RE) (MIT)
by ma1co, which does the actual work of talking to the camera.*
