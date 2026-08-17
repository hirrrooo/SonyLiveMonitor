import CoreLocation
import Foundation

struct GeoFix: Codable {
    let time: Date
    let latitude: Double
    let longitude: Double
    let altitude: Double
    let accuracy: Double
}

/// Guarda una pista local corta para geolocalizar cada foto por su hora de captura.
final class GeotagManager: NSObject, CLLocationManagerDelegate {
    static let shared = GeotagManager()
    static let enabledKey = "geotag_enabled"
    private static let samplesKey = "geotag_samples"
    private let manager = CLLocationManager()
    private let lock = NSLock()
    private let maxAge: TimeInterval = 24 * 60 * 60
    private let maxMatch: TimeInterval = 5 * 60
    private let maxCaptureFixAge: TimeInterval = 5 * 60
    private var samples: [GeoFix] = []

    var enabled: Bool { UserDefaults.standard.bool(forKey: Self.enabledKey) }

    private override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 5
        if let data = UserDefaults.standard.data(forKey: Self.samplesKey),
           let saved = try? JSONDecoder().decode([GeoFix].self, from: data) {
            samples = saved.filter { Date().timeIntervalSince($0.time) <= maxAge }
        }
    }

    func setEnabled(_ value: Bool) {
        UserDefaults.standard.set(value, forKey: Self.enabledKey)
        if value {
            manager.requestWhenInUseAuthorization()
            startIfEnabled()
        } else {
            manager.stopUpdatingLocation()
        }
    }

    func startIfEnabled() {
        guard enabled else { return }
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            manager.startUpdatingLocation()
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        default:
            break
        }
    }

    func stop() { manager.stopUpdatingLocation() }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if enabled && (manager.authorizationStatus == .authorizedWhenInUse ||
                       manager.authorizationStatus == .authorizedAlways) {
            manager.startUpdatingLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        lock.lock()
        defer { lock.unlock() }
        let now = Date()
        samples.removeAll { now.timeIntervalSince($0.time) > maxAge }
        for location in locations where location.horizontalAccuracy >= 0 && location.horizontalAccuracy <= 200 {
            let fix = GeoFix(time: location.timestamp, latitude: location.coordinate.latitude,
                             longitude: location.coordinate.longitude, altitude: location.altitude,
                             accuracy: location.horizontalAccuracy)
            if let last = samples.last,
               abs(last.time.timeIntervalSince(fix.time)) < 5,
               abs(last.latitude - fix.latitude) < 0.00001,
               abs(last.longitude - fix.longitude) < 0.00001 { continue }
            samples.append(fix)
        }
        if samples.count > 2000 { samples.removeFirst(samples.count - 2000) }
        if let data = try? JSONEncoder().encode(samples) {
            UserDefaults.standard.set(data, forKey: Self.samplesKey)
        }
    }

    /// Congela el ultimo fix disponible en el instante en que la camara entra
    /// en StillCapturing. Pedir una posicion nueva aqui llegaria demasiado tarde.
    @discardableResult
    func recordCapture(at capturedAt: Date = Date()) -> Bool {
        guard enabled else { return false }
        lock.lock()
        defer { lock.unlock() }
        guard let source = samples.min(by: {
            abs($0.time.timeIntervalSince(capturedAt)) < abs($1.time.timeIntervalSince(capturedAt))
        }), abs(source.time.timeIntervalSince(capturedAt)) <= maxCaptureFixAge else { return false }
        samples.append(GeoFix(time: capturedAt, latitude: source.latitude,
                              longitude: source.longitude, altitude: source.altitude,
                              accuracy: source.accuracy))
        if samples.count > 2000 { samples.removeFirst(samples.count - 2000) }
        if let data = try? JSONEncoder().encode(samples) {
            UserDefaults.standard.set(data, forKey: Self.samplesKey)
        }
        return true
    }

    func closest(to created: String) -> GeoFix? {
        let captured = Self.captureDates(created)
        guard !captured.isEmpty else { return nil }
        lock.lock()
        defer { lock.unlock() }
        func distance(_ fix: GeoFix) -> TimeInterval {
            captured.map { abs(fix.time.timeIntervalSince($0)) }.min() ?? .infinity
        }
        return samples.min(by: { distance($0) < distance($1) })
            .flatMap { distance($0) <= maxMatch ? $0 : nil }
    }

    /// Algunas Sony antiguas declaran +00:00 pero escriben la hora local en el
    /// texto. Se prueban ambas interpretaciones y se escoge la cercana al GPS.
    private static func captureDates(_ value: String) -> [Date] {
        guard !value.isEmpty else { return [] }
        var dates: [Date] = []
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso.date(from: value) { dates.append(date) }
        iso.formatOptions = [.withInternetDateTime]
        if let date = iso.date(from: value), !dates.contains(date) { dates.append(date) }
        let wallTime = String(value.prefix(19))
        for pattern in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy:MM:dd HH:mm:ss"] {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = .current
            formatter.dateFormat = pattern
            let input = pattern.hasPrefix("yyyy-MM-dd") ? wallTime : value
            if let date = formatter.date(from: input), !dates.contains(date) { dates.append(date) }
        }
        return dates
    }
}
