"""Ventana del instalador (Tkinter, incluido en la libreria estandar).

El trabajo USB se hace en un hilo aparte: PMCA-RE bloquea durante decenas de
segundos y la ventana no debe congelarse. El hilo nunca toca widgets; se
comunica con la interfaz por una cola que el bucle de Tk vacia periodicamente.
"""

import os
import queue
import threading
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import __version__, assets, backup, camera

RELEASES_URL = "https://github.com/otonielpv/SonyLiveMonitor/releases/latest"
# Guia del instalador (la de un clic). La manual, paso a paso, esta en
# docs/a6000-live-monitor-guide.md y se enlaza desde ella.
GUIDE_URL = (
    "https://github.com/otonielpv/SonyLiveMonitor/blob/main/docs/"
    "installer-guide.md"
)

BG = "#1e1f22"
FG = "#e8e8ea"
MUTED = "#9a9aa2"
ACCENT = "#3b82f6"
OK = "#22c55e"
WARN = "#f59e0b"
ERR = "#ef4444"


class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.camera_info = None

        root.title("Sony Live Monitor - Installer")
        root.configure(bg=BG)
        root.geometry("680x620")
        root.minsize(600, 540)

        self._build_styles()
        self._build_ui()

        self.root.after(100, self._drain_events)
        # Deteccion automatica al abrir: el usuario no deberia tener que pedirla.
        self.root.after(300, self.detect)

    # ------------------------------------------------------------------ UI

    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI", 16, "bold"))
        style.configure("Status.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI", 11))
        style.configure("TCheckbutton", background=BG, foreground=MUTED)
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("active", FG)])
        style.configure("TProgressbar", background=ACCENT, troughcolor="#2c2d31",
                        borderwidth=0, thickness=8)

    def _build_ui(self):
        pad = {"padx": 20}

        header = ttk.Frame(self.root)
        header.pack(fill="x", pady=(18, 4), **pad)
        ttk.Label(header, text="Sony Live Monitor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Install the patched Smart Remote on your Sony a6000.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # --- Estado de la camara ---
        card = tk.Frame(self.root, bg="#26272b", highlightthickness=0)
        card.pack(fill="x", pady=14, **pad)

        self.status_dot = tk.Label(card, text="●", bg="#26272b", fg=MUTED,
                                   font=("Segoe UI", 14))
        self.status_dot.grid(row=0, column=0, padx=(14, 8), pady=14)

        self.status_label = tk.Label(
            card, text="Looking for a camera...", bg="#26272b", fg=FG,
            font=("Segoe UI", 11, "bold"), anchor="w", justify="left",
        )
        self.status_label.grid(row=0, column=1, sticky="w", pady=(14, 0))

        self.detail_label = tk.Label(
            card, text="", bg="#26272b", fg=MUTED, font=("Segoe UI", 9),
            anchor="w", justify="left", wraplength=460,
        )
        self.detail_label.grid(row=1, column=1, sticky="w", pady=(2, 14))

        card.columnconfigure(1, weight=1)

        self.refresh_btn = tk.Button(
            card, text="Search again", command=self.detect,
            bg="#33343a", fg=FG, activebackground="#3d3e45", activeforeground=FG,
            relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
        )
        self.refresh_btn.grid(row=0, column=2, rowspan=2, padx=14)

        # --- Progreso ---
        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", **pad)

        self.progress_label = ttk.Label(self.root, text="", style="Muted.TLabel")
        self.progress_label.pack(anchor="w", pady=(4, 0), **pad)

        # --- Acciones ---
        actions = ttk.Frame(self.root)
        actions.pack(fill="x", pady=(14, 0), **pad)

        self.install_btn = tk.Button(
            actions, text="Install on camera", command=self.install,
            bg=ACCENT, fg="white", activebackground="#2f6fd0", activeforeground="white",
            relief="flat", bd=0, font=("Segoe UI", 11, "bold"),
            padx=18, pady=10, cursor="hand2", state="disabled",
        )
        self.install_btn.pack(side="left")

        self.restore_btn = tk.Button(
            actions, text="Restore original", command=self.restore,
            bg="#33343a", fg=FG, activebackground="#3d3e45", activeforeground=FG,
            relief="flat", bd=0, font=("Segoe UI", 10),
            padx=14, pady=10, cursor="hand2", state="disabled",
        )
        self.restore_btn.pack(side="left", padx=(10, 0))

        self.backup_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            actions,
            text="Back up via ADB",
            variable=self.backup_var,
            command=self._on_backup_toggle,
        ).pack(side="left", padx=(14, 0))

        # --- Log plegable ---
        log_bar = ttk.Frame(self.root)
        log_bar.pack(fill="x", pady=(16, 0), **pad)

        self.log_visible = False
        self.log_toggle = tk.Button(
            log_bar, text="▸ Show details", command=self._toggle_log,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=FG,
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 9),
        )
        self.log_toggle.pack(side="left")

        tk.Button(
            log_bar, text="Installation guide", cursor="hand2",
            command=lambda: webbrowser.open(GUIDE_URL),
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=FG,
            relief="flat", bd=0, font=("Segoe UI", 9),
        ).pack(side="right")

        self.log_frame = ttk.Frame(self.root)
        self.log_text = tk.Text(
            self.log_frame, height=10, bg="#141519", fg="#b9b9c0",
            insertbackground=FG, relief="flat", bd=0, wrap="word",
            font=("Consolas", 9), state="disabled",
        )
        scroll = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(
            self.root,
            text="v%s  -  Independent project, not affiliated with Sony." % __version__,
            style="Muted.TLabel", font=("Segoe UI", 8),
        ).pack(side="bottom", anchor="w", pady=(0, 10), **pad)

    def _toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_frame.pack(fill="both", expand=True, padx=20, pady=(6, 0))
            self.log_toggle.configure(text="▾ Hide details")
        else:
            self.log_frame.pack_forget()
            self.log_toggle.configure(text="▸ Show details")

    def _on_backup_toggle(self):
        if self.backup_var.get():
            messagebox.showinfo(
                "Back up via ADB",
                "Copying your original app requires ADB enabled on the "
                "camera:\n\n"
                "1. Install 'OpenMemories: Tweak' (via PMCA-RE).\n"
                "2. On the camera: Applications > OpenMemories: Tweak >\n"
                "   Developer > Enable Wi-Fi and Enable ADB.\n"
                "3. Connect this computer to the camera's Wi-Fi.\n\n"
                "You can skip this: the installer already ships Sony's "
                "original app, so a normal install needs no ADB.",
            )

    # -------------------------------------------------------------- eventos

    def _post(self, kind, **payload):
        """Llamado desde el hilo de trabajo. Nunca toca widgets."""
        self.events.put((kind, payload))

    def _drain_events(self):
        """Bucle de la GUI: aplica lo que el hilo de trabajo haya enviado."""
        try:
            while True:
                kind, payload = self.events.get_nowait()
                handler = getattr(self, "_on_" + kind, None)
                if handler:
                    handler(**payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _on_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_status(self, text, detail="", color=MUTED):
        self.status_label.configure(text=text)
        self.detail_label.configure(text=detail)
        self.status_dot.configure(fg=color)

    def _on_progress(self, message="", percent=None):
        self.progress_label.configure(text=message)
        if percent is None:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=percent)

    def _on_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.refresh_btn.configure(state=state)
        if busy:
            self.install_btn.configure(state="disabled")
            self.restore_btn.configure(state="disabled")
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            ready = "normal" if self.camera_info else "disabled"
            self.install_btn.configure(state=ready)
            # Restaurar solo tiene sentido si el APK de fabrica viaja dentro.
            has_original = assets.find_original_apk() is not None
            self.restore_btn.configure(
                state=ready if has_original else "disabled"
            )

    def _on_detected(self, info):
        self.camera_info = info
        if info.is_a6000:
            detail = ("SonyLiveMonitor is already installed - continue to "
                      "update or reinstall it."
                      if info.has_patched_app else "Ready to install.")
            color = OK
        else:
            detail = (
                "This installer is tested on the a6000 (ILCE-6000). You can "
                "continue, but at your own risk."
            )
            color = WARN
        extra = []
        if info.firmware:
            extra.append("firmware %s" % info.firmware)
        if info.serial:
            extra.append("s/n %s" % info.serial)
        if extra:
            detail += "  (%s)" % ", ".join(extra)
        self._on_status("Camera detected: %s" % info.model, detail, color)
        self.install_btn.configure(
            text="Update / reinstall" if info.has_patched_app
            else "Install on camera"
        )

    def _on_failed(self, title, message, fatal=True):
        self.camera_info = None
        self._on_status(title, message.split("\n")[0], ERR if fatal else WARN)
        self._on_progress("")
        messagebox.showerror(title, message)

    def _on_waiting(self, title, message):
        """Estado de espera, no error: aun no hay camara que usar.

        Las instrucciones se muestran en la propia ventana en vez de en un
        dialogo de error, que dan a entender que algo se ha roto.
        """
        self.camera_info = None
        self._on_status(title, "", WARN)
        self._on_progress("")
        # La primera linea repite el titulo que ya se muestra arriba.
        body = message.split("\n", 1)[1].strip() if "\n" in message else message
        self.detail_label.configure(text=body)

    def _on_done(self, message):
        self._on_progress("Done", 100)
        messagebox.showinfo("Finished", message)

    # --------------------------------------------------------------- tareas

    def _run(self, target):
        """Lanza `target` en un hilo, con manejo de errores homogeneo."""
        if self.busy:
            return
        self._post("busy", busy=True)

        def wrapper():
            try:
                target()
            except camera.NoCameraFound as exc:
                # Sin camara no hay nada roto: el usuario aun no la ha
                # enchufado. Se muestran los pasos, sin dialogo de error.
                self._post("waiting", title="No camera detected",
                           message=str(exc))
            except (camera.CameraError, assets.AssetError, backup.BackupError) as exc:
                self._post("failed", title="Cannot continue",
                           message=str(exc))
            except Exception as exc:  # error inesperado: log completo
                self._post("log", message=traceback.format_exc())
                self._post(
                    "failed",
                    title="Unexpected error",
                    message="%s\n\nOpen 'Show details' for the full log."
                            % exc,
                )
            finally:
                self._post("busy", busy=False)

        threading.Thread(target=wrapper, daemon=True).start()

    def detect(self):
        def task():
            log = lambda msg: self._post("log", message=msg)
            self._post("status", text="Looking for a camera...", detail="",
                       color=MUTED)
            self._post("progress", message="Scanning USB ports...", percent=None)
            with camera.CameraSession(log) as session:
                info = session.detect()
            self._post("detected", info=info)
            self._post("progress", message="")

        self._run(task)

    def install(self):
        if not self.camera_info:
            return

        already = self.camera_info.has_patched_app
        if already:
            # Instalar encima sobrescribe la copia existente (mismo paquete).
            # Es el camino normal para actualizar a una version nueva y tambien
            # para reparar una instalacion a medias.
            title = "Update or reinstall"
            warning = (
                "This camera already has SonyLiveMonitor installed.\n\n"
                "Continuing will overwrite it with the version shipped in this "
                "installer. That is how you update to a newer release, and it "
                "also repairs a broken install.\n\n"
                "Your photos and camera settings are not affected.\n\n"
            )
        else:
            title = "Confirm installation"
            warning = (
                "The patched Smart Remote will be installed on the camera.\n\n"
                "Sony's original app uses a different package name, so it is "
                "not removed: both will appear in the Applications menu.\n\n"
            )
            if not self.backup_var.get():
                warning += (
                    "You can undo this at any time with 'Restore original'.\n\n"
                )
        warning += "Do not disconnect the camera during the process.\n\nContinue?"

        if not messagebox.askyesno(title, warning, icon="warning"):
            return

        dest = None
        if self.backup_var.get():
            dest = filedialog.asksaveasfilename(
                title="Save a copy of the original Smart Remote",
                defaultextension=".apk",
                initialfile="SmartRemote_original_a6000.apk",
                filetypes=[("APK", "*.apk")],
            )
            if not dest:
                return

        def task():
            log = lambda msg: self._post("log", message=msg)

            if dest:
                self._post("progress", message="Backing up the original app...",
                           percent=None)
                backup.backup_original_apk(dest, log)
                log("Backup finished.")

            self._post("progress", message="Preparing the APK...", percent=None)
            apk_path = assets.resolve_apk(log)

            self._post("progress", message="Installing on the camera...",
                       percent=0)

            def progress(message, percent):
                self._post("progress", message=message, percent=percent)

            with camera.CameraSession(log) as session:
                session.install_apk(apk_path, progress)

            headline = ("SonyLiveMonitor has been updated." if already
                        else "The patched Smart Remote is installed.")
            message = (
                headline + "\n\n"
                "1. Restart the camera.\n"
                "2. Open Applications > SonyLiveMonitor.\n"
                "3. Connect your phone to the DIRECT-xxxx:ILCE-6000 Wi-Fi "
                "and open the phone app."
            )
            if dest:
                message += ("\n\nOriginal app saved to:\n%s"
                            % os.path.basename(dest))
            self._post("done", message=message)

        self._run(task)

    def restore(self):
        """Reinstala el Smart Remote Control de fabrica."""
        if not self.camera_info:
            return

        if not messagebox.askyesno(
            "Restore the original app",
            "Sony's original 'Smart Remote Control' (v4.30) will be "
            "installed on the camera.\n\n"
            "The patched version uses a different package name, so it does "
            "not need to be uninstalled: both can coexist and you can choose "
            "which one to open from the Applications menu.\n\n"
            "Do not disconnect the camera during the process.\n\nContinue?",
            icon="warning",
        ):
            return

        def task():
            log = lambda msg: self._post("log", message=msg)

            self._post("progress", message="Preparing the original app...",
                       percent=None)
            apk_path = assets.resolve_original_apk()

            self._post("progress", message="Restoring...", percent=0)

            def progress(message, percent):
                self._post("progress", message=message, percent=percent)

            with camera.CameraSession(log) as session:
                session.install_apk(apk_path, progress)

            self._post(
                "done",
                message=(
                    "The original app is installed.\n\n"
                    "Restart the camera and look for 'Smart Remote Control' "
                    "in the Applications menu."
                ),
            )

        self._run(task)


def main():
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()
    return 0
