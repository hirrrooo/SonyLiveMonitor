import Foundation

enum ArwGpsError: LocalizedError {
    case invalid(String)
    var errorDescription: String? {
        if case .invalid(let message) = self { return message }
        return "Invalid ARW"
    }
}

/// Anade un GPS IFD a un ARW/TIFF sin decodificar ni modificar los datos RAW.
enum ArwGpsWriter {
    private enum Endian { case little, big }
    private static let gpsTag: UInt16 = 0x8825

    static func write(_ fix: GeoFix, to url: URL) throws {
        var data = try Data(contentsOf: url, options: .mappedIfSafe)
        guard data.count >= 8 else { throw ArwGpsError.invalid("Truncated ARW") }
        let order: Endian
        if data[0] == 0x49 && data[1] == 0x49 { order = .little }
        else if data[0] == 0x4d && data[1] == 0x4d { order = .big }
        else { throw ArwGpsError.invalid("Not a TIFF/ARW file") }
        guard u16(data, 2, order) == 42 else { throw ArwGpsError.invalid("Not a TIFF/ARW file") }
        let oldIFD = Int(u32(data, 4, order))
        guard oldIFD >= 8, oldIFD + 2 <= data.count else { throw ArwGpsError.invalid("Invalid ARW IFD0") }
        let count = Int(u16(data, oldIFD, order))
        guard count > 0, count <= 4096, oldIFD + 2 + count * 12 + 4 <= data.count else {
            throw ArwGpsError.invalid("Unsupported ARW IFD0")
        }

        var entries: [(UInt16, Data)] = []
        for index in 0..<count {
            let start = oldIFD + 2 + index * 12
            let tag = u16(data, start, order)
            if tag != gpsTag { entries.append((tag, data.subdata(in: start..<(start + 12)))) }
        }
        let nextStart = oldIFD + 2 + count * 12
        let nextIFD = data.subdata(in: nextStart..<(nextStart + 4))
        if data.count % 2 != 0 { data.append(0) }
        let newIFD = data.count
        entries.append((gpsTag, Data()))
        let gpsOffset = newIFD + 2 + entries.count * 12 + 4
        let gps = gpsBlock(fix, at: gpsOffset, order)

        appendU16(&data, UInt16(entries.count), order)
        for entry in entries.sorted(by: { $0.0 < $1.0 }) {
            if entry.0 == gpsTag {
                appendU16(&data, gpsTag, order); appendU16(&data, 4, order)
                appendU32(&data, 1, order); appendU32(&data, UInt32(gpsOffset), order)
            } else {
                data.append(entry.1)
            }
        }
        data.append(nextIFD)
        data.append(gps)
        setU32(&data, 4, UInt32(newIFD), order)
        try data.write(to: url, options: .atomic)
    }

    private static func gpsBlock(_ fix: GeoFix, at offset: Int, _ order: Endian) -> Data {
        var entries: [(UInt16, Data)] = []
        var extras = Data()
        let entryCount = 10
        let dataStart = offset + 2 + entryCount * 12 + 4
        func entry(_ tag: UInt16, _ type: UInt16, _ count: UInt32, _ value: Data) -> Data {
            var out = Data(); appendU16(&out, tag, order); appendU16(&out, type, order)
            appendU32(&out, count, order); out.append(value); return out
        }
        func inline(_ tag: UInt16, _ type: UInt16, _ count: UInt32, _ value: Data) {
            var padded = value; while padded.count < 4 { padded.append(0) }
            entries.append((tag, entry(tag, type, count, padded)))
        }
        func external(_ tag: UInt16, _ type: UInt16, _ count: UInt32, _ value: Data) {
            var pointer = Data(); appendU32(&pointer, UInt32(dataStart + extras.count), order)
            entries.append((tag, entry(tag, type, count, pointer)))
            extras.append(value); if extras.count % 2 != 0 { extras.append(0) }
        }
        inline(0x0000, 1, 4, Data([2, 3, 0, 0]))
        inline(0x0001, 2, 2, Data([fix.latitude < 0 ? 0x53 : 0x4e, 0]))
        external(0x0002, 5, 3, dms(abs(fix.latitude), order))
        inline(0x0003, 2, 2, Data([fix.longitude < 0 ? 0x57 : 0x45, 0]))
        external(0x0004, 5, 3, dms(abs(fix.longitude), order))
        inline(0x0005, 1, 1, Data([fix.altitude < 0 ? 1 : 0]))
        external(0x0006, 5, 1, rational(abs(fix.altitude), denominator: 1000, order))
        let calendar = Calendar(identifier: .gregorian)
        let utc = TimeZone(secondsFromGMT: 0)!
        let parts = calendar.dateComponents(in: utc, from: fix.time)
        var clock = Data()
        clock.append(rational(Double(parts.hour ?? 0), denominator: 1, order))
        clock.append(rational(Double(parts.minute ?? 0), denominator: 1, order))
        clock.append(rational(Double(parts.second ?? 0), denominator: 1, order))
        external(0x0007, 5, 3, clock)
        external(0x0012, 2, 7, Data("WGS-84\0".utf8))
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = utc; formatter.dateFormat = "yyyy:MM:dd"
        external(0x001d, 2, 11, Data((formatter.string(from: fix.time) + "\0").utf8))

        var out = Data(); appendU16(&out, UInt16(entryCount), order)
        entries.sorted(by: { $0.0 < $1.0 }).forEach { out.append($0.1) }
        appendU32(&out, 0, order); out.append(extras)
        return out
    }

    private static func dms(_ value: Double, _ order: Endian) -> Data {
        let degrees = floor(value), minutesValue = (value - degrees) * 60
        let minutes = floor(minutesValue), seconds = (minutesValue - minutes) * 60
        var out = Data(); out.append(rational(degrees, denominator: 1, order))
        out.append(rational(minutes, denominator: 1, order))
        out.append(rational(seconds, denominator: 1_000_000, order)); return out
    }
    private static func rational(_ value: Double, denominator: UInt32, _ order: Endian) -> Data {
        var out = Data(); appendU32(&out, UInt32(max(0, value * Double(denominator)).rounded()), order)
        appendU32(&out, denominator, order); return out
    }
    private static func u16(_ data: Data, _ offset: Int, _ order: Endian) -> UInt16 {
        let a = UInt16(data[offset]), b = UInt16(data[offset + 1]); return order == .little ? a | b << 8 : a << 8 | b
    }
    private static func u32(_ data: Data, _ offset: Int, _ order: Endian) -> UInt32 {
        let bytes = (0..<4).map { UInt32(data[offset + $0]) }
        return order == .little ? bytes[0] | bytes[1] << 8 | bytes[2] << 16 | bytes[3] << 24
                                : bytes[0] << 24 | bytes[1] << 16 | bytes[2] << 8 | bytes[3]
    }
    private static func appendU16(_ data: inout Data, _ value: UInt16, _ order: Endian) {
        if order == .little { data.append(UInt8(value & 0xff)); data.append(UInt8(value >> 8)) }
        else { data.append(UInt8(value >> 8)); data.append(UInt8(value & 0xff)) }
    }
    private static func appendU32(_ data: inout Data, _ value: UInt32, _ order: Endian) {
        let shifts = order == .little ? [0, 8, 16, 24] : [24, 16, 8, 0]
        shifts.forEach { data.append(UInt8((value >> UInt32($0)) & 0xff)) }
    }
    private static func setU32(_ data: inout Data, _ offset: Int, _ value: UInt32, _ order: Endian) {
        var bytes = Data(); appendU32(&bytes, value, order)
        data.replaceSubrange(offset..<(offset + 4), with: bytes)
    }
}
