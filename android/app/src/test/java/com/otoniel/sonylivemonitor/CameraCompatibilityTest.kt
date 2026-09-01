package com.otoniel.sonylivemonitor

import org.junit.Assert.assertEquals
import org.junit.Test

class CameraCompatibilityTest {
    @Test
    fun `recognizes both Sony names for the a6000`() {
        assertEquals(true, CameraCompatibility.isA6000("Sony ILCE-6000"))
        assertEquals(true, CameraCompatibility.isA6000("Sony A6000"))
        assertEquals(false, CameraCompatibility.isA6000("Sony ILCE-6300"))
    }

    @Test
    fun `a6000 model receives a specific drive message`() {
        assertEquals(
            "Drive: remote burst control is not supported by the Sony A6000",
            CameraCompatibility.driveUnavailableMessage("Sony ILCE-6000"),
        )
    }

    @Test
    fun `unknown model receives capability based explanation`() {
        assertEquals(
            "Drive: not available in the camera's current mode or state",
            CameraCompatibility.driveUnavailableMessage(null),
        )
    }
}
