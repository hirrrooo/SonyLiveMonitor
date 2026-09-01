import UIKit
import Combine
import Darwin

enum GridMode: Int, CaseIterable {
    case off, thirds, thirdsDiag, cross

    var label: String {
        switch self {
        case .off: return "off"
        case .thirds: return "3x3"
        case .thirdsDiag: return "3x3+X"
        case .cross: return "cross"
        }
    }
}

enum PeakingColor: Int, CaseIterable {
    case off, red, yellow, white

    var label: String {
        switch self {
        case .off: return "off"
        case .red: return "red"
        case .yellow: return "yellow"
        case .white: return "white"
        }
    }

    var rgba: (UInt8, UInt8, UInt8, UInt8) {
        switch self {
        case .off: return (0, 0, 0, 0)
        case .red: return (255, 32, 32, 230)
        case .yellow: return (255, 220, 0, 230)
        case .white: return (255, 255, 255, 235)
        }
    }
}

enum PeakingSensitivity: Int, CaseIterable {
    case low, medium, high

    var label: String {
        switch self {
        case .low: return "low"
        case .medium: return "medium"
        case .high: return "high"
        }
    }

    var shortLabel: String {
        switch self {
        case .low: return "L"
        case .medium: return "M"
        case .high: return "H"
        }
    }

    // Umbrales sobre el gradiente Sobel a resolucion completa. Al calcularse por
    // pixel (no sobre pares de 2px como antes) las magnitudes son menores, y con
    // supresion de no-maximos solo sobrevive la cresta del borde, asi que se
    // pueden usar umbrales mas bajos sin ensuciar.
    var threshold: Int {
        switch self {
        case .low: return 190
        case .medium: return 130
        case .high: return 80
        }
    }
}

struct Exposure {
    let hist: [Int]           // 64 bins de luminancia
    let evOffset: Float       // desviacion respecto al gris medio (18%)
    let clipShadows: Float    // % de pixeles recortados en sombras
    let clipHighlights: Float // % de pixeles recortados en altas luces
}

/// Ajuste editable en vivo desde el panel de control.
struct CameraSetting: Identifiable {
    let id: String
    let getMethod: String
    let setMethod: String
    var numeric = false  // el setter espera un numero, no un string
    let chipLabel: (String) -> String

    /// getAvailableX devuelve valores editables; getX devuelve siempre el
    /// valor actual y es mas fiable durante la inicializacion en la a6000.
    var currentMethod: String { getMethod.replacingOccurrences(of: "getAvailable", with: "get") }
}

/// Tira horizontal de valores de un ajuste abierta en el panel.
struct ValueStrip {
    let owner: String
    var values: [String]
    var current: String?
    let apply: (String) -> Void  // llamar desde el hilo principal
}

enum VideoSource: Int {
    case wifi, hdmi
    var label: String { self == .hdmi ? "HDMI" : "WiFi" }
}

final class MonitorViewModel: ObservableObject {

    static let settings: [CameraSetting] = [
        CameraSetting(id: "ISO", getMethod: "getAvailableIsoSpeedRate", setMethod: "setIsoSpeedRate",
                      chipLabel: { "ISO \($0)" }),
        CameraSetting(id: "Shutter", getMethod: "getAvailableShutterSpeed", setMethod: "setShutterSpeed",
                      chipLabel: { $0 }),
        CameraSetting(id: "Aperture", getMethod: "getAvailableFNumber", setMethod: "setFNumber",
                      chipLabel: { "f/\($0)" }),
        CameraSetting(id: "Focus", getMethod: "getAvailableFocusMode", setMethod: "setFocusMode",
                      chipLabel: { $0 }),
        CameraSetting(id: "Drive", getMethod: "getAvailableContShootingMode", setMethod: "setContShootingMode",
                      chipLabel: { "Drive \($0)" }),
        CameraSetting(id: "Flash", getMethod: "getAvailableFlashMode", setMethod: "setFlashMode",
                      chipLabel: { "Flash \($0)" }),
        CameraSetting(id: "Timer", getMethod: "getAvailableSelfTimer", setMethod: "setSelfTimer",
                      numeric: true, chipLabel: { "T:\($0)s" }),
    ]

    // -- estado publicado (solo se toca en el hilo principal) --------------------

    @Published var image: UIImage?
    @Published var peakingImage: UIImage?
    @Published var hudText: String?
    @Published var alertText: String?
    @Published var statusMessage: String? = "Waiting for the camera WiFi..."
    @Published var zoomText: String?
    @Published var exposure: Exposure?
    @Published var focusMarker: CGPoint?
    @Published var toast: String?
    @Published var strip: ValueStrip?
    @Published var chipLabels: [String: String] = [:]
    @Published var rotation: Int
    @Published var mirror: Bool
    @Published var panelTab: Int
    @Published var grid: GridMode
    @Published var meterOn: Bool
    @Published var peakingColor: PeakingColor
    @Published var peakingSensitivity: PeakingSensitivity
    @Published var hudOn: Bool
    @Published var videoSource: VideoSource
    @Published var shootMode = "still"
    @Published var movieRecording = false
    @Published var showConnectHelp = false
    @Published var showGallery = false
    @Published var geotagEnabled: Bool
    // Salud del enlace con la camara. iOS no expone el RSSI del WiFi, asi que
    // se estima del transporte real: huecos entre frames (jitter) + drops. Es
    // el sintoma directo de mala red, que es lo que importa para diagnosticar.
    @Published var linkText: String?          // ej. "link: fair (1.5 gaps/s)"
    @Published var linkQuality = 0            // 0=desconocido 1=good 2=fair 3=weak
    @Published var diagnosticsReport: String?  // no-nil mientras se muestra la hoja

    private let apiQueue = DispatchQueue(label: "camera-api")
    private let eventQueue = DispatchQueue(label: "camera-events")
    private let defaults = UserDefaults.standard

    // Una generacion identifica cada sesion. Un hilo antiguo nunca puede
    // reactivarse al volver la app a primer plano porque conserva su generacion.
    private let lifecycleLock = NSLock()
    private var sessionActive = false
    private var sessionGeneration = 0
    private var currentStream: LiveviewStream?
    private var currentExternalStream: ExternalCameraStream?
    private var worker: Thread?

    // Copia sincronizada del pequeno subconjunto de estado que consume el hilo
    // de render. Las propiedades @Published siguen perteneciendo a main.
    private let renderStateLock = NSLock()
    private var meterOnStorage = false
    private var peakingColorStorage = PeakingColor.off
    private var peakingSensitivityStorage = PeakingSensitivity.medium
    private var capturingStorage = false
    private var zoomTextGeneration = 0
    private var focusGeneration = 0
    private var touchFocusActive = false
    private var toastGeneration = 0
    private let cameraEventLock = NSLock()
    private var eventListenerRunning = false
    private var lastCameraStatus: String?
    private var appCapturePendingAt: Date?
    private var evStepIndex = 1

    // Como maximo puede haber una actualizacion de video esperando en main.
    // Sin esta coalescencia, una bajada puntual de rendimiento acumula un
    // UIImage por frame y puede terminar agotando memoria y congelando la UI.
    private let framePublishLock = NSLock()
    private var framePublishScheduled = false
    private var pendingFramePublish: (UIImage?, UIImage?, Exposure?, String?, String)?

    init() {
        rotation = defaults.integer(forKey: "rot")
        mirror = defaults.bool(forKey: "mirror")
        panelTab = min(max(defaults.integer(forKey: "panelTab"), 0), 2)
        grid = GridMode(rawValue: defaults.integer(forKey: "grid")) ?? .off
        meterOn = defaults.bool(forKey: "meter")
        peakingColor = PeakingColor(rawValue: defaults.integer(forKey: "peakingColor")) ?? .off
        peakingSensitivity = PeakingSensitivity(
            rawValue: defaults.object(forKey: "peakingSensitivity") == nil
                ? PeakingSensitivity.medium.rawValue
                : defaults.integer(forKey: "peakingSensitivity")
        ) ?? .medium
        hudOn = defaults.object(forKey: "hud") == nil ? true : defaults.bool(forKey: "hud")
        videoSource = VideoSource(rawValue: defaults.integer(forKey: "videoSource")) ?? .wifi
        if UIDevice.current.userInterfaceIdiom != .pad { videoSource = .wifi }
        geotagEnabled = GeotagManager.shared.enabled
        meterOnStorage = meterOn
        peakingColorStorage = peakingColor
        peakingSensitivityStorage = peakingSensitivity
        for s in Self.settings { chipLabels[s.id] = s.id }
        chipLabels["EV"] = "EV"
        chipLabels["WB"] = "WB"
        chipLabels["MODE"] = "Mode: Photo"
    }

    // -- ciclo de vida ------------------------------------------------------------

    /// Detiene el liveview y abre la galeria de la tarjeta a pantalla completa.
    /// El monitor se reinicia al cerrar la galeria (onDismiss en ContentView).
    func openGallery() {
        stop()
        showGallery = true
    }

    func start() {
        guard !showGallery else { return }
        geotagEnabled = GeotagManager.shared.enabled
        GeotagManager.shared.startIfEnabled()

        lifecycleLock.lock()
        guard !sessionActive else { lifecycleLock.unlock(); return }
        sessionActive = true
        sessionGeneration &+= 1
        let generation = sessionGeneration
        UIApplication.shared.isIdleTimerDisabled = true
        let t = Thread { [weak self] in
            autoreleasepool { self?.monitorLoop(generation: generation) }
        }
        t.name = "monitor"
        worker = t
        lifecycleLock.unlock()
        t.start()
    }

    func stop() {
        GeotagManager.shared.stop()
        lifecycleLock.lock()
        sessionActive = false
        sessionGeneration &+= 1
        let stream = currentStream
        let external = currentExternalStream
        currentStream = nil
        currentExternalStream = nil
        worker?.cancel()
        worker = nil
        lifecycleLock.unlock()

        // Cerrar el socket despierta inmediatamente awaitFrame/read; no dejamos
        // que una sesion anterior sobreviva hasta el siguiente start().
        stream?.stop()
        external?.stop()
        SonyCamera.cancelEventWait()
        UIApplication.shared.isIdleTimerDisabled = false

        framePublishLock.lock()
        pendingFramePublish = nil
        framePublishLock.unlock()
        image = nil
        peakingImage = nil
        exposure = nil
    }

    func toggleGeotagging() {
        geotagEnabled.toggle()
        GeotagManager.shared.setEnabled(geotagEnabled)
        showToast(geotagEnabled ? "Geotagging enabled for future photos" : "Geotagging disabled")
    }

    func toggleVideoSource() {
        if videoSource == .wifi && UIDevice.current.userInterfaceIdiom != .pad {
            showToast("HDMI/UVC is available only on iPad")
            return
        }
        stop()
        videoSource = videoSource == .wifi ? .hdmi : .wifi
        defaults.set(videoSource.rawValue, forKey: "videoSource")
        start()
    }

    private func isSessionActive(_ generation: Int) -> Bool {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        return sessionActive && sessionGeneration == generation
    }

    private func activeSessionGeneration() -> Int? {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        return sessionActive ? sessionGeneration : nil
    }

    private func registerStream(_ stream: LiveviewStream, generation: Int) -> Bool {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        guard sessionActive, sessionGeneration == generation else { return false }
        currentStream = stream
        return true
    }

    private func clearStream(_ stream: LiveviewStream) {
        lifecycleLock.lock()
        if currentStream === stream { currentStream = nil }
        lifecycleLock.unlock()
    }

    private func registerExternalStream(_ stream: ExternalCameraStream, generation: Int) -> Bool {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        guard sessionActive, sessionGeneration == generation else { return false }
        currentExternalStream = stream
        return true
    }

    private func clearExternalStream(_ stream: ExternalCameraStream) {
        lifecycleLock.lock()
        if currentExternalStream === stream { currentExternalStream = nil }
        lifecycleLock.unlock()
    }

    private func renderSettings() -> (meter: Bool, color: PeakingColor,
                                      sensitivity: PeakingSensitivity, capturing: Bool) {
        renderStateLock.lock()
        defer { renderStateLock.unlock() }
        return (meterOnStorage, peakingColorStorage,
                peakingSensitivityStorage, capturingStorage)
    }

    private func setCapturing(_ value: Bool) {
        renderStateLock.lock()
        capturingStorage = value
        renderStateLock.unlock()
    }

    // -- toggles persistentes -------------------------------------------------------

    func cycleRotation() {
        rotation = (rotation + 90) % 360
        defaults.set(rotation, forKey: "rot")
    }

    func toggleMirror() {
        mirror.toggle()
        defaults.set(mirror, forKey: "mirror")
    }

    func selectPanelTab(_ tab: Int) {
        guard (0...2).contains(tab), panelTab != tab else { return }
        panelTab = tab
        strip = nil
        defaults.set(tab, forKey: "panelTab")
    }

    func cycleGrid() {
        grid = GridMode(rawValue: (grid.rawValue + 1) % GridMode.allCases.count) ?? .off
        defaults.set(grid.rawValue, forKey: "grid")
    }

    func toggleMeter() {
        meterOn.toggle()
        renderStateLock.lock(); meterOnStorage = meterOn; renderStateLock.unlock()
        defaults.set(meterOn, forKey: "meter")
        if !meterOn { exposure = nil }
    }

    func cyclePeakingColor() {
        peakingColor = PeakingColor(
            rawValue: (peakingColor.rawValue + 1) % PeakingColor.allCases.count
        ) ?? .off
        renderStateLock.lock(); peakingColorStorage = peakingColor; renderStateLock.unlock()
        defaults.set(peakingColor.rawValue, forKey: "peakingColor")
        if peakingColor == .off { peakingImage = nil }
    }

    func cyclePeakingSensitivity() {
        peakingSensitivity = PeakingSensitivity(
            rawValue: (peakingSensitivity.rawValue + 1) % PeakingSensitivity.allCases.count
        ) ?? .medium
        renderStateLock.lock()
        peakingSensitivityStorage = peakingSensitivity
        renderStateLock.unlock()
        defaults.set(peakingSensitivity.rawValue, forKey: "peakingSensitivity")
    }

    func toggleHud() {
        hudOn.toggle()
        defaults.set(hudOn, forKey: "hud")
    }

    // -- bucle principal (hilo propio, nunca bloquea la UI) ---------------------------

    private func monitorLoop(generation: Int) {
        while isSessionActive(generation) {
            // Foundation/UIKit generan objetos autoreleased tambien durante los
            // reintentos. Esta piscina exterior se vacia en cada vuelta.
            autoreleasepool {
                do {
                    if videoSource == .hdmi {
                        publishMessage("Waiting for an HDMI/UVC capture device...")
                        try streamExternalAndRender(generation: generation)
                        return
                    }
                    publishMessage("Connecting to the camera...")
                    let url = try SonyCamera.startLiveview()
                    guard isSessionActive(generation) else { return }
                    refreshChips()
                    startCameraEventListener(generation: generation)
                    streamAndRender(url: url, generation: generation)
                } catch {
                    guard isSessionActive(generation) else { return }
                    let message: String
                    if error is URLError {
                        // Aun no estamos en la WiFi de la camara: instrucciones, no error crudo
                        message = "Waiting for the camera WiFi...\n\n"
                            + "On the camera: 'Ctrl w/ Smartphone'.\n"
                            + "On the iPhone: Settings > WiFi and join the\n"
                            + "DIRECT-xxxx network shown on the camera."
                    } else {
                        message = "Error: \(error.localizedDescription)\nRetrying..."
                    }
                    publishMessage(message)
                    Thread.sleep(forTimeInterval: 2)
                }
            }
        }
    }

    /// HDMI proporciona la imagen; la API Sony por WiFi sigue alimentando los
    /// controles, el disparador, los eventos y la galeria cuando esta disponible.
    private func connectControlsForHdmi(generation: Int) {
        apiQueue.async {
            guard self.isSessionActive(generation) else { return }
            if (try? SonyCamera.call("getVersions")) != nil {
                self.refreshChips()
                self.startCameraEventListener(generation: generation)
            } else {
                self.apiQueue.asyncAfter(deadline: .now() + 3) {
                    self.connectControlsForHdmi(generation: generation)
                }
            }
        }
    }

    private func streamExternalAndRender(generation: Int) throws {
        let stream = ExternalCameraStream()
        try stream.start()
        guard registerExternalStream(stream, generation: generation) else {
            stream.stop()
            return
        }
        connectControlsForHdmi(generation: generation)
        defer {
            stream.stop()
            clearExternalStream(stream)
        }

        DispatchQueue.main.async {
            self.linkText = "video: HDMI/UVC"
            self.linkQuality = 1
        }

        var fps: Float = 0
        var fpsWindowStart = ProcessInfo.processInfo.systemUptime
        var fpsWindowCount = 0
        var lastFrameAt = fpsWindowStart
        var lastMeterAt: TimeInterval = 0
        var lastPeakingAt: TimeInterval = 0
        var peakingOverlay: UIImage?
        var meterExposure: Exposure?
        let peakingProcessor = FocusPeakingProcessor()

        while isSessionActive(generation), videoSource == .hdmi {
            let frame = stream.awaitFrame(timeout: 0.25)
            let now = ProcessInfo.processInfo.systemUptime
            guard let frame else {
                if now - lastFrameAt > 1.2 {
                    publishFrame(nil, alert: stream.status, fps: fps, ageMs: -1,
                                 dropped: stream.framesDropped)
                }
                continue
            }

            autoreleasepool {
                fpsWindowCount += 1
                lastFrameAt = now
                if now - fpsWindowStart >= 1 {
                    fps = Float(fpsWindowCount) / Float(now - fpsWindowStart)
                    fpsWindowStart = now
                    fpsWindowCount = 0
                }

                let settings = renderSettings()
                if !settings.meter {
                    meterExposure = nil
                } else if now - lastMeterAt >= 0.15, let cg = frame.image.cgImage {
                    lastMeterAt = now
                    meterExposure = ExposureMeter.compute(cg)
                }

                if settings.color == .off {
                    peakingOverlay = nil
                } else if now - lastPeakingAt >= 0.12, let cg = frame.image.cgImage {
                    lastPeakingAt = now
                    peakingOverlay = peakingProcessor.compute(
                        cg, color: settings.color, sensitivity: settings.sensitivity
                    )
                }

                let ageMs = Int((ProcessInfo.processInfo.systemUptime - frame.receivedAt) * 1000)
                publishFrame(frame.image, peaking: peakingOverlay, exposure: meterExposure,
                             alert: nil, fps: fps, ageMs: ageMs,
                             dropped: stream.framesDropped)
            }
        }
    }

    private func streamAndRender(url: String, generation: Int) {
        let stream = LiveviewStream(url: url)
        stream.start()
        guard registerStream(stream, generation: generation) else {
            stream.stop()
            return
        }
        defer {
            stream.stop()
            clearStream(stream)
        }

        var fps: Float = 0
        var fpsWindowStart = ProcessInfo.processInfo.systemUptime
        var fpsWindowCount = 0
        var lastFrameAt = fpsWindowStart
        var lastMeterAt: TimeInterval = 0
        var lastPeakingAt: TimeInterval = 0
        var peakingOverlay: UIImage?
        var meterExposure: Exposure?
        let peakingProcessor = FocusPeakingProcessor()
        // Ventana para la salud del enlace: contamos "huecos" (intervalos entre
        // frames mayores de 120 ms, ~3x el periodo a 25 fps) y drops por segundo.
        var linkWindowStart = fpsWindowStart
        var gapCount = 0
        var dropsAtWindowStart = 0

        while isSessionActive(generation) {
            let frame = stream.awaitFrame(timeout: 0.25)
            let now = ProcessInfo.processInfo.systemUptime

            guard let frame else {
                let stalled = now - lastFrameAt
                if renderSettings().capturing {
                    // El liveview se pausa mientras la camara captura y procesa
                    // la foto: es normal, no es perdida de senal.
                    lastFrameAt = now
                    publishFrame(nil, alert: "CAPTURING...", fps: fps, ageMs: -1, dropped: stream.framesDropped)
                    continue
                }
                if stalled > 20 { return }  // sin frames 20 s: reiniciar liveview desde cero
                if stalled > 1.2 {
                    publishFrame(nil, alert: "NO SIGNAL \(Int(stalled))s (\(stream.status))",
                                 fps: fps, ageMs: -1, dropped: stream.framesDropped)
                }
                continue
            }

            // UIImage/ImageIO y CoreGraphics crean objetos autoreleased. Al
            // vaciar por frame la memoria temporal no crece durante toda la sesion.
            autoreleasepool {
                guard let decoded = UIImage(data: frame.jpeg) else { return }

                fpsWindowCount += 1
                // Un intervalo largo entre frames = hueco de transporte (jitter/red)
                if now - lastFrameAt > 0.12 { gapCount += 1 }
                lastFrameAt = now
                if now - fpsWindowStart >= 1 {
                    fps = Float(fpsWindowCount) / Float(now - fpsWindowStart)
                    fpsWindowStart = now
                    fpsWindowCount = 0
                }
                if now - linkWindowStart >= 1 {
                    let elapsed = now - linkWindowStart
                    let gapsPerSec = Double(gapCount) / elapsed
                    let dropsPerSec = Double(stream.framesDropped - dropsAtWindowStart) / elapsed
                    updateLinkHealth(gapsPerSec: gapsPerSec, dropsPerSec: dropsPerSec)
                    linkWindowStart = now
                    gapCount = 0
                    dropsAtWindowStart = stream.framesDropped
                }

                let ageMs = Int((ProcessInfo.processInfo.systemUptime - frame.receivedAt) * 1000)

                let settings = renderSettings()
                // El analisis de exposicion es barato pero 7 muestras/s bastan.
                // Se publica junto al frame para que tampoco pueda formar cola.
                if !settings.meter {
                    meterExposure = nil
                } else if now - lastMeterAt >= 0.15, let cg = decoded.cgImage {
                    lastMeterAt = now
                    meterExposure = ExposureMeter.compute(cg)
                }

                if settings.color == .off {
                    peakingOverlay = nil
                } else if now - lastPeakingAt >= 0.12, let cg = decoded.cgImage {
                    // 8 fps dan respuesta visual suficiente y reducen CPU/temperatura.
                    lastPeakingAt = now
                    peakingOverlay = peakingProcessor.compute(
                        cg, color: settings.color, sensitivity: settings.sensitivity
                    )
                }

                guard isSessionActive(generation) else { return }
                publishFrame(decoded, peaking: peakingOverlay, exposure: meterExposure,
                             alert: nil, fps: fps, ageMs: ageMs,
                             dropped: stream.framesDropped)
            }
        }
    }

    private func publishFrame(_ image: UIImage?, peaking: UIImage? = nil,
                              exposure: Exposure? = nil, alert: String?,
                              fps: Float, ageMs: Int, dropped: Int) {
        let hud = ageMs >= 0
            ? String(format: "%.1f fps | age %d ms | drops %d", fps, ageMs, dropped)
            : String(format: "%.1f fps | drops %d", fps, dropped)

        framePublishLock.lock()
        pendingFramePublish = (image, peaking, exposure, alert, hud)
        let shouldSchedule = !framePublishScheduled
        if shouldSchedule { framePublishScheduled = true }
        framePublishLock.unlock()
        guard shouldSchedule else { return }

        DispatchQueue.main.async {
            self.framePublishLock.lock()
            let update = self.pendingFramePublish
            self.pendingFramePublish = nil
            self.framePublishScheduled = false
            self.framePublishLock.unlock()

            guard let (image, peaking, exposure, alert, hud) = update else { return }
            self.statusMessage = nil
            if let image { self.image = image }
            self.peakingImage = peaking
            self.exposure = exposure
            self.hudText = hud
            self.alertText = alert
        }
    }

    /// Traduce jitter (huecos/s) y drops/s a una salud de enlace legible.
    /// Umbrales conservadores: a 25 fps un enlace sano tiene ~0 huecos.
    private func updateLinkHealth(gapsPerSec: Double, dropsPerSec: Double) {
        let quality: Int      // 1=good 2=fair 3=weak
        if gapsPerSec >= 3 || dropsPerSec >= 8 {
            quality = 3
        } else if gapsPerSec >= 1 || dropsPerSec >= 3 {
            quality = 2
        } else {
            quality = 1
        }
        let label = quality == 1 ? "good" : (quality == 2 ? "fair" : "weak")
        let text = String(format: "link: %@ (%.1f gaps/s)", label, gapsPerSec)
        DispatchQueue.main.async {
            self.linkQuality = quality
            self.linkText = text
        }
    }

    /// Genera el informe de diagnostico y lo publica para mostrar en una hoja.
    func runDiagnostics() {
        showToast("Reading camera info...")
        apiQueue.async {
            let report = SonyCamera.diagnostics()
            DispatchQueue.main.async { self.diagnosticsReport = report }
        }
    }

    private func publishMessage(_ message: String) {
        DispatchQueue.main.async {
            self.statusMessage = message
            self.hudText = nil
            self.alertText = nil
            self.linkText = nil       // sin stream no hay salud de enlace valida
            self.linkQuality = 0
        }
    }

    // -- acciones de camara ------------------------------------------------------------

    private static func stringify(_ value: Any) -> String {
        if let n = value as? NSNumber { return n.stringValue }
        return "\(value)"
    }

    private func applySetting(_ method: String, value: Any, onOK: @escaping () -> Void) {
        apiQueue.async {
            do {
                self.cancelTouchFocusBeforeSetting()
                try self.callSettingWhenAvailable(method, params: [value])
                DispatchQueue.main.async(execute: onOK)
            } catch {
                self.showToast("Error: \(error.localizedDescription)")
            }
        }
    }

    /// Sony bloquea temporalmente ISO, WB, modo, etc. mientras sigue activo el
    /// enfoque tactil. Se cancela antes de cambiar un ajuste y se tolera el breve
    /// estado de transicion que algunos modelos notifican como error 1.
    private func cancelTouchFocusBeforeSetting() {
        guard touchFocusActive else { return }
        _ = try? callSettingWhenAvailable("cancelTouchAFPosition")
        touchFocusActive = false
    }

    @discardableResult
    private func callSettingWhenAvailable(_ method: String, params: [Any] = []) throws -> [Any] {
        let delays: [TimeInterval] = [0.15, 0.3, 0.6]
        for attempt in 0...delays.count {
            do {
                return try SonyCamera.call(method, params: params)
            } catch {
                let temporarilyBusy = error.localizedDescription.localizedCaseInsensitiveContains(
                    "[1] Not Available Now"
                )
                guard temporarilyBusy, attempt < delays.count else { throw error }
                Thread.sleep(forTimeInterval: delays[attempt])
            }
        }
        throw CameraError("\(method) failed")
    }

    /// Abre/cierra la tira de valores de un ajuste. Cada valor se aplica al
    /// instante y la tira permanece abierta para seguir ajustando.
    func toggleStrip(for setting: CameraSetting) {
        if setting.id == "Drive" {
            toggleDriveStrip(for: setting)
            return
        }
        if strip?.owner == setting.id { strip = nil; return }
        strip = ValueStrip(owner: setting.id, values: [], current: nil, apply: { _ in })
        apiQueue.async {
            do {
                let r = try SonyCamera.call(setting.getMethod)
                guard r.count >= 2, let cand = r[1] as? [Any], !cand.isEmpty else {
                    throw CameraError("not available in this mode")
                }
                let current = Self.stringify(r[0])
                let values = cand.map(Self.stringify)
                DispatchQueue.main.async {
                    guard self.strip?.owner == setting.id else { return }
                    self.strip = ValueStrip(owner: setting.id, values: values, current: current) { value in
                        self.applySetting(setting.setMethod,
                                          value: setting.numeric ? (Int(value) ?? 0) : value) {
                            self.chipLabels[setting.id] = setting.chipLabel(value)
                            if self.strip?.owner == setting.id { self.strip?.current = value }
                        }
                    }
                }
            } catch {
                self.showToast("\(setting.id): \(error.localizedDescription)")
                DispatchQueue.main.async {
                    if self.strip?.owner == setting.id { self.strip = nil }
                }
            }
        }
    }

    /// La compensacion EV va por indices de paso (1/3 o 1/2 EV por paso).
    func toggleEvStrip() {
        if strip?.owner == "EV" { strip = nil; return }
        strip = ValueStrip(owner: "EV", values: [], current: nil, apply: { _ in })
        apiQueue.async {
            do {
                let r = try SonyCamera.call("getAvailableExposureCompensation")
                guard r.count >= 4,
                      let cur = (r[0] as? NSNumber)?.intValue,
                      let maxStep = (r[1] as? NSNumber)?.intValue,
                      let minStep = (r[2] as? NSNumber)?.intValue,
                      let stepIndex = (r[3] as? NSNumber)?.intValue,
                      minStep <= maxStep else {
                    throw CameraError("unexpected response")
                }
                let stepEv = stepIndex == 2 ? 0.5 : 1.0 / 3.0
                let steps = Array(minStep...maxStep)
                let labels = steps.map { String(format: "%+.1f", Double($0) * stepEv) }
                let current = String(format: "%+.1f", Double(cur) * stepEv)
                DispatchQueue.main.async {
                    guard self.strip?.owner == "EV" else { return }
                    self.strip = ValueStrip(owner: "EV", values: labels, current: current) { label in
                        guard let index = labels.firstIndex(of: label) else { return }
                        self.applySetting("setExposureCompensation", value: steps[index]) {
                            self.chipLabels["EV"] = "\(label) EV"
                            if self.strip?.owner == "EV" { self.strip?.current = label }
                        }
                    }
                }
            } catch {
                self.showToast("EV: \(error.localizedDescription)")
                DispatchQueue.main.async { if self.strip?.owner == "EV" { self.strip = nil } }
            }
        }
    }

    /// El balance de blancos usa objetos {whiteBalanceMode: ...} en la API.
    func toggleWbStrip() {
        if strip?.owner == "WB" { strip = nil; return }
        strip = ValueStrip(owner: "WB", values: [], current: nil, apply: { _ in })
        apiQueue.async {
            do {
                let r = try SonyCamera.call("getAvailableWhiteBalance")
                guard r.count >= 2,
                      let current = (r[0] as? [String: Any])?["whiteBalanceMode"] as? String,
                      let cand = r[1] as? [[String: Any]] else {
                    throw CameraError("unexpected response")
                }
                let modes = cand.compactMap { $0["whiteBalanceMode"] as? String }
                DispatchQueue.main.async {
                    guard self.strip?.owner == "WB" else { return }
                    self.strip = ValueStrip(owner: "WB", values: modes, current: current) { mode in
                        self.apiQueue.async {
                            do {
                                self.cancelTouchFocusBeforeSetting()
                                // Para "Color Temperature" hace falta un kelvin: 5500 por defecto
                                let temp = mode == "Color Temperature"
                                try self.callSettingWhenAvailable(
                                    "setWhiteBalance", params: [mode, temp, temp ? 5500 : 0]
                                )
                                DispatchQueue.main.async {
                                    self.chipLabels["WB"] = "WB \(Self.trimWbSuffix(mode))"
                                    if self.strip?.owner == "WB" { self.strip?.current = mode }
                                }
                            } catch {
                                self.showToast("WB: \(error.localizedDescription)")
                            }
                        }
                    }
                }
            } catch {
                self.showToast("WB: \(error.localizedDescription)")
                DispatchQueue.main.async { if self.strip?.owner == "WB" { self.strip = nil } }
            }
        }
    }

    /// Cambio entre foto y video (el disparador pasa a iniciar/parar REC).
    func toggleModeStrip() {
        if strip?.owner == "MODE" { strip = nil; return }
        strip = ValueStrip(owner: "MODE", values: [], current: nil, apply: { _ in })
        apiQueue.async {
            do {
                let r = try SonyCamera.call("getAvailableShootMode")
                guard r.count >= 2, let current = r[0] as? String, let cand = r[1] as? [String] else {
                    throw CameraError("unexpected response")
                }
                DispatchQueue.main.async {
                    guard self.strip?.owner == "MODE" else { return }
                    self.strip = ValueStrip(owner: "MODE", values: cand, current: current) { mode in
                        self.applySetting("setShootMode", value: mode) {
                            self.shootMode = mode
                            self.movieRecording = false
                            self.chipLabels["MODE"] = mode == "movie" ? "Mode: Video" : "Mode: Photo"
                            if self.strip?.owner == "MODE" { self.strip?.current = mode }
                        }
                    }
                }
            } catch {
                self.showToast("Mode: \(error.localizedDescription)")
                DispatchQueue.main.async { if self.strip?.owner == "MODE" { self.strip = nil } }
            }
        }
    }

    func closeStrip() {
        strip = nil
    }

    /// Zoom motorizado: mantener pulsado para acercar/alejar.
    func zoom(direction: String, movement: String) {
        apiQueue.async {
            do {
                try SonyCamera.call("actZoom", params: [direction, movement])
            } catch {
                if movement == "start" { self.showToast("Zoom: requires a power zoom lens") }
            }
        }
    }

    /// El grupo Continuous shooting de Sony usa un objeto para leer y escribir,
    /// no el formato posicional simple del resto de ajustes.
    private func toggleDriveStrip(for setting: CameraSetting) {
        if strip?.owner == setting.id { strip = nil; return }
        strip = ValueStrip(owner: setting.id, values: [], current: nil, apply: { _ in })
        apiQueue.async {
            if self.shootMode == "movie" {
                self.showToast("Drive: available only in Photo mode")
                DispatchQueue.main.async { if self.strip?.owner == setting.id { self.strip = nil } }
                return
            }
            do {
                // No bloquear por getAvailableApiList: una app Sony parcheada
                // puede aceptar comandos que no declara en esa lista.
                let result = try SonyCamera.call(setting.getMethod)
                guard let state = result.first as? [String: Any],
                      let current = state["contShootingMode"] as? String,
                      let values = state["candidate"] as? [String], !values.isEmpty else {
                    throw CameraError("unexpected response")
                }
                DispatchQueue.main.async {
                    guard self.strip?.owner == setting.id else { return }
                    self.strip = ValueStrip(owner: setting.id, values: values, current: current) { value in
                        self.applySetting(setting.setMethod,
                                          value: ["contShootingMode": value]) {
                            self.chipLabels[setting.id] = setting.chipLabel(value)
                            if self.strip?.owner == setting.id { self.strip?.current = value }
                        }
                    }
                }
            } catch {
                let unavailable = error.localizedDescription.localizedCaseInsensitiveContains("Not Available Now")
                self.showToast(unavailable
                    ? "Drive: not available in the camera's current mode or state"
                    : "Drive: \(error.localizedDescription)")
                DispatchQueue.main.async { if self.strip?.owner == setting.id { self.strip = nil } }
            }
        }
    }

    func takePicture() {
        if shootMode == "movie" {
            // En modo video el disparador inicia/detiene la grabacion
            let recording = movieRecording
            apiQueue.async {
                do {
                    try SonyCamera.call(recording ? "stopMovieRec" : "startMovieRec")
                    DispatchQueue.main.async { self.movieRecording = !recording }
                    self.showToast(recording ? "Recording stopped" : "Recording...")
                } catch {
                    self.showToast("Video: \(error.localizedDescription)")
                }
            }
            return
        }
        setCapturing(true)
        cameraEventLock.lock()
        appCapturePendingAt = Date()
        cameraEventLock.unlock()
        GeotagManager.shared.recordCapture()
        apiQueue.async {
            defer { self.setCapturing(false) }
            do {
                try SonyCamera.call("actTakePicture")
                self.showToast("Photo taken")
                self.refreshChips()  // los valores pueden cambiar tras el disparo (p.ej. ISO auto)
            } catch {
                self.cameraEventLock.lock()
                self.appCapturePendingAt = nil
                self.cameraEventLock.unlock()
                self.showToast("Shutter: \(error.localizedDescription)")
            }
        }
    }

    /// Enfoque tactil: coordenadas en % del frame, ya des-rotadas por la vista.
    func touchFocus(xPct: Double, yPct: Double, marker: CGPoint) {
        focusMarker = marker
        focusGeneration += 1
        let generation = focusGeneration
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            if self.focusGeneration == generation { self.focusMarker = nil }
        }
        apiQueue.async {
            do {
                try SonyCamera.call("setTouchAFPosition", params: [xPct, yPct])
                self.touchFocusActive = true
            } catch {
                self.touchFocusActive = false
                self.showToast("Focus: \(error.localizedDescription)")
            }
        }
    }

    /// Actualiza las etiquetas de los chips con los valores actuales de la camara.
    func refreshChips() {
        apiQueue.async {
            var currentById: [String: String] = [:]
            for setting in Self.settings {
                if let result = try? SonyCamera.call(setting.currentMethod), let current = result.first {
                    if setting.id == "Drive", let state = current as? [String: Any],
                       let mode = state["contShootingMode"] as? String {
                        currentById[setting.id] = mode
                    } else {
                        currentById[setting.id] = Self.stringify(current)
                    }
                }
            }

            for setting in Self.settings {
                if currentById[setting.id] == nil,
                   let r = try? SonyCamera.call(setting.getMethod), let current = r.first {
                    currentById[setting.id] = Self.stringify(current)
                }
            }
            let labels = Dictionary(uniqueKeysWithValues: Self.settings.compactMap { setting in
                currentById[setting.id].map { (setting.id, setting.chipLabel($0)) }
            })
            DispatchQueue.main.async { self.chipLabels.merge(labels) { _, new in new } }
            if let r = try? SonyCamera.call("getAvailableExposureCompensation"), r.count >= 4,
               let cur = (r[0] as? NSNumber)?.intValue,
               let stepIndex = (r[3] as? NSNumber)?.intValue {
                self.evStepIndex = stepIndex
                let stepEv = stepIndex == 2 ? 0.5 : 1.0 / 3.0
                let label = String(format: "%+.1f EV", Double(cur) * stepEv)
                DispatchQueue.main.async { self.chipLabels["EV"] = label }
            }
            if let r = try? SonyCamera.call("getAvailableWhiteBalance"),
               let mode = (r.first as? [String: Any])?["whiteBalanceMode"] as? String {
                DispatchQueue.main.async { self.chipLabels["WB"] = "WB \(Self.trimWbSuffix(mode))" }
            }
            if let r = try? SonyCamera.call("getAvailableShootMode"), let mode = r.first as? String {
                DispatchQueue.main.async {
                    self.shootMode = mode
                    self.chipLabels["MODE"] = mode == "movie" ? "Mode: Video" : "Mode: Photo"
                }
            }
        }
    }

    /// Un unico long polling recibe cambios hechos desde el movil o directamente
    /// en la camara sin consultar el estado una vez por segundo.
    private func startCameraEventListener(generation: Int) {
        cameraEventLock.lock()
        guard !eventListenerRunning else { cameraEventLock.unlock(); return }
        eventListenerRunning = true
        lastCameraStatus = nil
        cameraEventLock.unlock()

        eventQueue.async {
            var version = "1.1"
            defer {
                self.cameraEventLock.lock()
                self.eventListenerRunning = false
                self.cameraEventLock.unlock()
                if let activeGeneration = self.activeSessionGeneration() {
                    self.startCameraEventListener(generation: activeGeneration)
                }
            }
            while self.isSessionActive(generation) {
                do {
                    let result = try SonyCamera.call("getEvent", params: [true], version: version,
                                                     timeout: 65, eventWait: true)
                    if self.isSessionActive(generation) { self.handleCameraEvents(result) }
                } catch {
                    guard self.isSessionActive(generation) else { return }
                    if version == "1.1" { version = "1.0" }
                    else { Thread.sleep(forTimeInterval: 0.5) }
                }
            }
        }
    }

    private func eventObjects(_ value: Any) -> [[String: Any]] {
        if let object = value as? [String: Any] { return [object] }
        if let array = value as? [Any] { return array.flatMap { eventObjects($0) } }
        return []
    }

    private func handleCameraEvents(_ result: [Any]) {
        let objects = eventObjects(result)
        let keys = [
            "currentIsoSpeedRate": "ISO",
            "currentShutterSpeed": "Shutter",
            "currentFNumber": "Aperture",
            "currentFocusMode": "Focus",
            "currentContShootingMode": "Drive",
            "currentFlashMode": "Flash",
            "currentSelfTimer": "Timer",
        ]
        var labels: [String: String] = [:]
        var zoomPosition: Int?
        var newShootMode: String?

        for event in objects {
            if let status = event["cameraStatus"] as? String { handleCameraStatus(status) }
            for (key, id) in keys {
                guard let value = event[key],
                      let setting = Self.settings.first(where: { $0.id == id }) else { continue }
                labels[id] = setting.chipLabel(Self.stringify(value))
            }
            if let current = (event["currentExposureCompensation"] as? NSNumber)?.intValue {
                if let step = (event["stepIndexOfExposureCompensation"] as? NSNumber)?.intValue {
                    evStepIndex = step
                }
                let step = evStepIndex == 2 ? 0.5 : 1.0 / 3.0
                labels["EV"] = String(format: "%+.1f EV", Double(current) * step)
            }
            if let wb = event["currentWhiteBalanceMode"] as? String {
                labels["WB"] = "WB \(Self.trimWbSuffix(wb))"
            }
            if let mode = event["currentShootMode"] as? String {
                newShootMode = mode
                labels["MODE"] = mode == "movie" ? "Mode: Video" : "Mode: Photo"
            }
            if let pct = (event["zoomPosition"] as? NSNumber)?.intValue { zoomPosition = pct }
        }

        if !labels.isEmpty || newShootMode != nil {
            DispatchQueue.main.async {
                self.chipLabels.merge(labels) { _, new in new }
                if let mode = newShootMode { self.shootMode = mode }
            }
        }
        if let pct = zoomPosition {
            let mm = 16.0 * pow(50.0 / 16.0, Double(pct) / 100.0)
            let text = String(format: "Zoom %d%%  ~%.0f mm", pct, mm)
            DispatchQueue.main.async {
                self.zoomText = text
                self.zoomTextGeneration += 1
                let generation = self.zoomTextGeneration
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                    if self.zoomTextGeneration == generation { self.zoomText = nil }
                }
            }
        }
    }

    private func handleCameraStatus(_ status: String) {
        var recordPhysicalCapture = false
        cameraEventLock.lock()
        let previous = lastCameraStatus
        if status != previous {
            let wasCapturing = previous == "StillCapturing" || previous == "StillSaving"
            switch status {
            case "StillCapturing", "StillSaving":
                setCapturing(true)
                if !wasCapturing {
                    let pending = appCapturePendingAt.map {
                        let age = Date().timeIntervalSince($0)
                        return age >= 0 && age <= 30
                    } ?? false
                    if pending { appCapturePendingAt = nil }
                    else { recordPhysicalCapture = true }
                }
            case "IDLE":
                setCapturing(false)
                if wasCapturing { appCapturePendingAt = nil }
            default:
                break
            }
            lastCameraStatus = status
        }
        cameraEventLock.unlock()
        if recordPhysicalCapture { GeotagManager.shared.recordCapture() }
    }

    private static func trimWbSuffix(_ mode: String) -> String {
        mode.hasSuffix(" WB") ? String(mode.dropLast(3)) : mode
    }

    private func showToast(_ message: String) {
        DispatchQueue.main.async {
            self.toast = message
            self.toastGeneration += 1
            let generation = self.toastGeneration
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) {
                if self.toastGeneration == generation { self.toast = nil }
            }
        }
    }
}

// -- focus peaking calculado integramente en el movil -----------------------------

final class FocusPeakingProcessor {
    private let graySpace = CGColorSpaceCreateDeviceGray()
    private let rgbSpace = CGColorSpaceCreateDeviceRGB()
    private var width = 0
    private var height = 0
    private var luma = [UInt8]()
    private var grad = [Int32]()
    private var rgba = [UInt8]()

    private func prepare(width: Int, height: Int) {
        guard self.width != width || self.height != height else { return }
        self.width = width
        self.height = height
        luma = [UInt8](repeating: 0, count: width * height)
        // Int32 cubre de sobra el maximo Sobel y usa la mitad que Int en arm64.
        grad = [Int32](repeating: 0, count: width * height)
        rgba = [UInt8](repeating: 0, count: width * height * 4)
    }

    /// Sobel a resolucion completa con supresion de no-maximos: solo se marca la
    /// cresta del borde (linea de ~1px) y no su relleno. Imita el peaking fino de
    /// la Sony y evita colorear bordes anchos y desenfocados. Trabajar a full-res
    /// cuesta CPU, por eso el llamador lo limita a unas 8 muestras/s.
    func compute(_ image: CGImage, color: PeakingColor,
                 sensitivity: PeakingSensitivity) -> UIImage? {
        guard color != .off else { return nil }
        let width = image.width
        let height = image.height
        guard width >= 3, height >= 3 else { return nil }
        prepare(width: width, height: height)

        let drewImage = luma.withUnsafeMutableBytes { bytes -> Bool in
            guard let base = bytes.baseAddress,
                  let ctx = CGContext(data: base, width: width, height: height,
                                      bitsPerComponent: 8, bytesPerRow: width,
                                      space: graySpace,
                                      bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return false }
            ctx.interpolationQuality = .low
            ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drewImage else { return nil }

        // Paso 1: magnitud del gradiente Sobel en cada pixel interior.
        luma.withUnsafeBufferPointer { l in
            grad.withUnsafeMutableBufferPointer { g in
                for y in 1..<(height - 1) {
                    for x in 1..<(width - 1) {
                        let i = y * width + x
                        let gx = -Int(l[i - width - 1]) + Int(l[i - width + 1])
                            - 2 * Int(l[i - 1]) + 2 * Int(l[i + 1])
                            - Int(l[i + width - 1]) + Int(l[i + width + 1])
                        let gy = -Int(l[i - width - 1]) - 2 * Int(l[i - width])
                            - Int(l[i - width + 1]) + Int(l[i + width - 1])
                            + 2 * Int(l[i + width]) + Int(l[i + width + 1])
                        g[i] = Int32(abs(gx) + abs(gy))
                    }
                }
            }
        }

        rgba.withUnsafeMutableBytes { bytes in
            if let base = bytes.baseAddress { memset(base, 0, bytes.count) }
        }
        let (red, green, blue, alpha) = color.rgba
        // El contexto de salida usa alpha premultiplicado.
        let outR = UInt8(Int(red) * Int(alpha) / 255)
        let outG = UInt8(Int(green) * Int(alpha) / 255)
        let outB = UInt8(Int(blue) * Int(alpha) / 255)
        let threshold = Int32(sensitivity.threshold)
        // Paso 2: marcamos solo donde el gradiente supera el umbral y es un maximo
        // local frente a los cuatro vecinos. Asi la banda ancha de un borde
        // borroso se reduce a su cresta y desaparece si la transicion es suave.
        for y in 1..<(height - 1) {
            for x in 1..<(width - 1) {
                let i = y * width + x
                let g = grad[i]
                guard g >= threshold,
                      g >= grad[i - 1], g >= grad[i + 1],
                      g >= grad[i - width], g >= grad[i + width] else { continue }
                let p = i * 4
                rgba[p] = outR; rgba[p + 1] = outG; rgba[p + 2] = outB; rgba[p + 3] = alpha
            }
        }

        return rgba.withUnsafeMutableBytes { bytes -> UIImage? in
            guard let base = bytes.baseAddress,
                  let ctx = CGContext(data: base, width: width, height: height,
                                      bitsPerComponent: 8, bytesPerRow: width * 4,
                                      space: rgbSpace,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                                        | CGBitmapInfo.byteOrder32Big.rawValue),
                  let mask = ctx.makeImage() else { return nil }
            return UIImage(cgImage: mask)
        }
    }
}

// -- medidor de exposicion (calculado del liveview; la API de Sony no expone
//    el fotometro interno de la camara) --------------------------------------

enum ExposureMeter {

    private static let colorSpace = CGColorSpaceCreateDeviceRGB()
    private static let linearLut: [Float] = (0..<256).map { pow(Float($0) / 255, 2.2) }

    /// Reescala el frame a una muestra pequena y calcula histograma, EV y recorte.
    static func compute(_ image: CGImage) -> Exposure? {
        let width = 120
        let height = 68
        guard let ctx = CGContext(data: nil, width: width, height: height,
                                  bitsPerComponent: 8, bytesPerRow: width * 4,
                                  space: colorSpace,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return nil
        }
        ctx.interpolationQuality = .low
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        guard let pixels = ctx.data?.assumingMemoryBound(to: UInt8.self) else { return nil }

        var hist = [Int](repeating: 0, count: 64)
        var sumLinear: Float = 0
        var shadows = 0
        var highlights = 0
        let count = width * height
        for i in 0..<count {
            let p = i * 4
            // Luma BT.709 en aritmetica entera
            let luma = (Int(pixels[p]) * 54 + Int(pixels[p + 1]) * 183 + Int(pixels[p + 2]) * 19) >> 8
            hist[luma >> 2] += 1
            sumLinear += linearLut[luma]
            if luma <= 4 { shadows += 1 } else if luma >= 251 { highlights += 1 }
        }
        let meanLinear = sumLinear / Float(count)
        // Desviacion respecto al gris medio (18% reflectancia)
        let ev = log2(meanLinear / 0.18)
        return Exposure(hist: hist, evOffset: ev,
                        clipShadows: Float(shadows) * 100 / Float(count),
                        clipHighlights: Float(highlights) * 100 / Float(count))
    }
}
