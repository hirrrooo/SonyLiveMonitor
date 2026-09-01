package com.otoniel.sonylivemonitor

object CameraCompatibility {
    fun isA6000(modelName: String?): Boolean {
        val model = modelName.orEmpty()
        return model.contains("ILCE-6000", ignoreCase = true) ||
            model.contains("A6000", ignoreCase = true)
    }

    fun driveUnavailableMessage(modelName: String?): String {
        return if (isA6000(modelName)) {
            "Drive: remote burst control is not supported by the Sony A6000"
        } else {
            "Drive: not available in the camera's current mode or state"
        }
    }
}
