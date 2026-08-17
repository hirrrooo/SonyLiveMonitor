import Foundation
import ImageIO

enum JpegGpsWriter {
    /// ImageIO copia el bitstream JPEG y fusiona solo metadatos: no recomprime.
    static func write(_ fix: GeoFix, to url: URL) throws {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let type = CGImageSourceGetType(source) else {
            throw CocoaError(.fileReadCorruptFile)
        }
        let metadata = CGImageSourceCopyMetadataAtIndex(source, 0, nil)
            .flatMap { CGImageMetadataCreateMutableCopy($0) } ?? CGImageMetadataCreateMutable()
        func set(_ key: CFString, _ value: CFTypeRef) {
            CGImageMetadataSetValueMatchingImageProperty(metadata, kCGImagePropertyGPSDictionary, key, value)
        }
        set(kCGImagePropertyGPSLatitude, NSNumber(value: abs(fix.latitude)))
        set(kCGImagePropertyGPSLatitudeRef, (fix.latitude < 0 ? "S" : "N") as CFString)
        set(kCGImagePropertyGPSLongitude, NSNumber(value: abs(fix.longitude)))
        set(kCGImagePropertyGPSLongitudeRef, (fix.longitude < 0 ? "W" : "E") as CFString)
        set(kCGImagePropertyGPSAltitude, NSNumber(value: abs(fix.altitude)))
        set(kCGImagePropertyGPSAltitudeRef, NSNumber(value: fix.altitude < 0 ? 1 : 0))
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0); formatter.dateFormat = "yyyy:MM:dd"
        set(kCGImagePropertyGPSDateStamp, formatter.string(from: fix.time) as CFString)
        formatter.dateFormat = "HH:mm:ss.SSSSSS"
        set(kCGImagePropertyGPSTimeStamp, formatter.string(from: fix.time) as CFString)

        let output = url.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".jpg")
        defer { try? FileManager.default.removeItem(at: output) }
        guard let destination = CGImageDestinationCreateWithURL(output as CFURL, type, 1, nil) else {
            throw CocoaError(.fileWriteUnknown)
        }
        let options: [CFString: Any] = [
            kCGImageDestinationMetadata: metadata,
            kCGImageDestinationMergeMetadata: true,
        ]
        var error: Unmanaged<CFError>?
        guard CGImageDestinationCopyImageSource(destination, source, options as CFDictionary, &error) else {
            if let error { throw error.takeRetainedValue() }
            throw CocoaError(.fileWriteUnknown)
        }
        _ = try FileManager.default.replaceItemAt(url, withItemAt: output)
    }
}
