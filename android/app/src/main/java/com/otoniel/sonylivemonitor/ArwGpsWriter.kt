package com.otoniel.sonylivemonitor

import android.location.Location
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.roundToLong

/**
 * Inserta un GPS IFD estandar en un Sony ARW (TIFF) sin tocar los datos RAW.
 *
 * Se anade un IFD0 nuevo al final y el puntero de cuatro bytes de la cabecera se
 * cambia al final de la operacion. El IFD0 y todos los bloques originales quedan
 * byte por byte intactos. Debe usarse sobre una copia temporal del archivo.
 */
object ArwGpsWriter {
    private const val TIFF_MAGIC = 42
    private const val TAG_GPS_IFD = 0x8825
    private const val TYPE_BYTE = 1
    private const val TYPE_ASCII = 2
    private const val TYPE_LONG = 4
    private const val TYPE_RATIONAL = 5
    private const val MAX_IFD_ENTRIES = 4096

    private data class Entry(val tag: Int, val bytes: ByteArray)
    private data class Fix(val latitude: Double, val longitude: Double, val altitude: Double, val time: Long)

    fun write(file: File, location: Location) =
        write(file, Fix(location.latitude, location.longitude, location.altitude, location.time))

    /** Entrada independiente de Android para pruebas de compatibilidad con ARW reales. */
    fun write(file: File, latitude: Double, longitude: Double, altitude: Double, time: Long) =
        write(file, Fix(latitude, longitude, altitude, time))

    private fun write(file: File, fix: Fix) {
        require(fix.latitude in -90.0..90.0 && fix.longitude in -180.0..180.0)
        RandomAccessFile(file, "rw").use { io ->
            require(io.length() in 8..0xfffffff0L) { "Unsupported ARW size" }
            val marker = ByteArray(2).also { io.readFully(it) }
            val order = when (String(marker, Charsets.US_ASCII)) {
                "II" -> ByteOrder.LITTLE_ENDIAN
                "MM" -> ByteOrder.BIG_ENDIAN
                else -> throw IllegalArgumentException("Not a TIFF/ARW file")
            }
            require(readU16(io, order) == TIFF_MAGIC) { "Not a TIFF/ARW file" }
            val oldIfdOffset = readU32(io, order)
            require(oldIfdOffset in 8 until io.length() - 2) { "Invalid ARW IFD0" }
            io.seek(oldIfdOffset)
            val count = readU16(io, order)
            require(count in 1..MAX_IFD_ENTRIES) { "Unsupported ARW IFD0" }
            val tableEnd = oldIfdOffset + 2 + count * 12L + 4
            require(tableEnd <= io.length()) { "Truncated ARW IFD0" }
            val existing = ArrayList<Entry>(count + 1)
            repeat(count) {
                val raw = ByteArray(12).also { io.readFully(it) }
                val tag = ByteBuffer.wrap(raw, 0, 2).order(order).short.toInt() and 0xffff
                if (tag != TAG_GPS_IFD) existing += Entry(tag, raw)
            }
            val nextIfd = ByteArray(4).also { io.readFully(it) }

            var appendAt = align2(io.length())
            require(appendAt < 0xfffffff0L) { "ARW is too large to extend" }
            if (appendAt != io.length()) { io.seek(io.length()); io.write(0) }
            val newIfdOffset = appendAt
            val entries = existing + Entry(TAG_GPS_IFD, ByteArray(12))
            val gpsIfdOffset = newIfdOffset + 2 + entries.size * 12L + 4
            val gps = buildGpsBlock(gpsIfdOffset, fix, order)

            io.seek(newIfdOffset)
            writeU16(io, entries.size, order)
            entries.sortedBy { it.tag }.forEach { entry ->
                if (entry.tag == TAG_GPS_IFD) {
                    writeU16(io, TAG_GPS_IFD, order)
                    writeU16(io, TYPE_LONG, order)
                    writeU32(io, 1, order)
                    writeU32(io, gpsIfdOffset, order)
                } else {
                    io.write(entry.bytes)
                }
            }
            io.write(nextIfd)
            io.write(gps)
            io.fd.sync()

            // Commit atomico dentro de la copia temporal: hasta aqui el ARW
            // original seguia siendo legible mediante su IFD0 anterior.
            io.seek(4)
            writeU32(io, newIfdOffset, order)
            io.fd.sync()
        }
    }

    private fun buildGpsBlock(offset: Long, location: Fix, order: ByteOrder): ByteArray {
        val entryCount = 10
        val dataStart = offset + 2 + entryCount * 12L + 4
        val extras = ArrayList<ByteArray>()
        var dataOffset = dataStart
        val entries = ArrayList<ByteArray>(entryCount)

        fun inline(tag: Int, type: Int, count: Long, value: ByteArray) {
            require(value.size <= 4)
            entries += entry(tag, type, count, value.copyOf(4), order)
        }
        fun external(tag: Int, type: Int, count: Long, value: ByteArray) {
            entries += entry(tag, type, count, u32Bytes(dataOffset, order), order)
            extras += value
            dataOffset += value.size
            if (dataOffset % 2L != 0L) { extras += byteArrayOf(0); dataOffset++ }
        }

        inline(0x0000, TYPE_BYTE, 4, byteArrayOf(2, 3, 0, 0))
        inline(0x0001, TYPE_ASCII, 2, byteArrayOf(if (location.latitude < 0) 'S'.code.toByte() else 'N'.code.toByte(), 0))
        external(0x0002, TYPE_RATIONAL, 3, dms(abs(location.latitude), order))
        inline(0x0003, TYPE_ASCII, 2, byteArrayOf(if (location.longitude < 0) 'W'.code.toByte() else 'E'.code.toByte(), 0))
        external(0x0004, TYPE_RATIONAL, 3, dms(abs(location.longitude), order))
        inline(0x0005, TYPE_BYTE, 1, byteArrayOf(if (location.altitude < 0) 1 else 0))
        external(0x0006, TYPE_RATIONAL, 1, rational(abs(location.altitude), 1000, order))
        val instant = Instant.ofEpochMilli(location.time)
        val utc = instant.atZone(ZoneOffset.UTC)
        external(0x0007, TYPE_RATIONAL, 3,
            rational(utc.hour.toDouble(), 1, order) + rational(utc.minute.toDouble(), 1, order) +
                rational(utc.second + utc.nano / 1_000_000_000.0, 1000, order))
        external(0x0012, TYPE_ASCII, 7, "WGS-84\u0000".toByteArray(Charsets.US_ASCII))
        external(0x001d, TYPE_ASCII, 11,
            (DateTimeFormatter.ofPattern("yyyy:MM:dd").format(utc) + "\u0000").toByteArray(Charsets.US_ASCII))

        return ByteBuffer.allocate((2 + entryCount * 12 + 4) + extras.sumOf { it.size }).order(order).apply {
            putShort(entryCount.toShort())
            entries.sortedWith(compareBy { ByteBuffer.wrap(it, 0, 2).order(order).short.toInt() and 0xffff }).forEach(::put)
            putInt(0)
            extras.forEach(::put)
        }.array()
    }

    private fun dms(value: Double, order: ByteOrder): ByteArray {
        val degrees = floor(value)
        val minutesValue = (value - degrees) * 60.0
        val minutes = floor(minutesValue)
        val seconds = (minutesValue - minutes) * 60.0
        return rational(degrees, 1, order) + rational(minutes, 1, order) + rational(seconds, 1_000_000, order)
    }

    private fun rational(value: Double, denominator: Int, order: ByteOrder): ByteArray =
        ByteBuffer.allocate(8).order(order).putInt((value * denominator).roundToLong().coerceIn(0, 0xffffffffL).toInt())
            .putInt(denominator).array()

    private fun entry(tag: Int, type: Int, count: Long, value: ByteArray, order: ByteOrder): ByteArray =
        ByteBuffer.allocate(12).order(order).putShort(tag.toShort()).putShort(type.toShort())
            .putInt(count.toInt()).put(value).array()

    private fun u32Bytes(value: Long, order: ByteOrder): ByteArray =
        ByteBuffer.allocate(4).order(order).putInt(value.toInt()).array()

    private fun align2(value: Long) = (value + 1L) and -2L
    private fun readU16(io: RandomAccessFile, order: ByteOrder): Int =
        ByteBuffer.wrap(ByteArray(2).also(io::readFully)).order(order).short.toInt() and 0xffff
    private fun readU32(io: RandomAccessFile, order: ByteOrder): Long =
        ByteBuffer.wrap(ByteArray(4).also(io::readFully)).order(order).int.toLong() and 0xffffffffL
    private fun writeU16(io: RandomAccessFile, value: Int, order: ByteOrder) = io.write(ByteBuffer.allocate(2).order(order).putShort(value.toShort()).array())
    private fun writeU32(io: RandomAccessFile, value: Long, order: ByteOrder) = io.write(u32Bytes(value, order))
}
