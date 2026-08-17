package com.otoniel.sonylivemonitor

import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId

class GeotagManagerTest {
    @Test
    fun sonyUtcLabelAlsoProducesLocalWallTimeCandidate() {
        val value = "2026-08-17T14:09:28+00:00"
        val canary = ZoneId.of("Atlantic/Canary")
        val candidates = GeotagManager.parseCaptureTimes(value, canary)

        val declaredInstant = OffsetDateTime.parse(value).toInstant().toEpochMilli()
        val localWallTime = LocalDateTime.parse("2026-08-17T14:09:28")
            .atZone(canary).toInstant().toEpochMilli()

        assertTrue(declaredInstant in candidates)
        assertTrue(localWallTime in candidates)
    }
}
