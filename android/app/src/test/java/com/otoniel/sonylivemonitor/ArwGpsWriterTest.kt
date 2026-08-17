package com.otoniel.sonylivemonitor

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.file.Files

class ArwGpsWriterTest {
    @Test fun writesGpsDirectoryWithoutChangingOriginalPayload() {
        val source = System.getProperty("arwSample")?.let(::File)
            ?: File(System.getProperty("user.home"), "Downloads/_DSC7391.ARW")
        assumeTrue("Sony ARW sample is not available", source.isFile)
        val original = source.readBytes()
        val requestedOutput = System.getProperty("arwOutput")?.let(::File)
        val copy = requestedOutput ?: Files.createTempFile("sony-arw-gps-", ".ARW").toFile()
        try {
            source.copyTo(copy, overwrite = true)
            ArwGpsWriter.write(copy, 28.123456, -15.654321, 42.5, 1_723_737_845_000L)
            val tagged = copy.readBytes()
            assertTrue(tagged.size > original.size)
            // Solo cambia el puntero IFD0 de la cabecera; el resto del ARW
            // original, incluidos todos los datos del sensor, queda identico.
            assertArrayEquals(original.copyOfRange(0, 4), tagged.copyOfRange(0, 4))
            assertArrayEquals(original.copyOfRange(8, original.size), tagged.copyOfRange(8, original.size))

            val order = if (tagged[0] == 'I'.code.toByte()) ByteOrder.LITTLE_ENDIAN else ByteOrder.BIG_ENDIAN
            val ifd = u32(tagged, 4, order)
            val count = u16(tagged, ifd, order)
            val gpsEntry = (0 until count).map { ifd + 2 + it * 12 }
                .first { u16(tagged, it, order) == 0x8825 }
            val gps = u32(tagged, gpsEntry + 8, order)
            val gpsCount = u16(tagged, gps, order)
            assertEquals(10, gpsCount)
            val tags = (0 until gpsCount).map { u16(tagged, gps + 2 + it * 12, order) }
            assertTrue(tags.containsAll(listOf(0x0001, 0x0002, 0x0003, 0x0004, 0x0006, 0x001d)))
        } finally { if (requestedOutput == null) copy.delete() }
    }

    private fun u16(data: ByteArray, offset: Int, order: ByteOrder) =
        ByteBuffer.wrap(data, offset, 2).order(order).short.toInt() and 0xffff
    private fun u32(data: ByteArray, offset: Int, order: ByteOrder) =
        ByteBuffer.wrap(data, offset, 4).order(order).int
}
