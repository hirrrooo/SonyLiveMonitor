package com.otoniel.sonylivemonitor

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import kotlin.math.abs

/** Historial GPS local para asociar una foto con la posicion al dispararla. */
object GeotagManager : LocationListener {
    const val PERMISSION_REQUEST = 6103
    private const val PREFS = "geotag"
    private const val KEY_ENABLED = "enabled"
    private const val KEY_SAMPLES = "samples"
    private const val MAX_AGE_MS = 24 * 60 * 60 * 1000L
    private const val MAX_MATCH_MS = 5 * 60 * 1000L
    private const val MAX_CAPTURE_FIX_AGE_MS = 5 * 60 * 1000L
    private const val MAX_SAMPLES = 2000
    private var app: Context? = null
    private var manager: LocationManager? = null

    data class Sample(val time: Long, val latitude: Double, val longitude: Double,
                      val altitude: Double, val accuracy: Float, val provider: String) {
        fun asLocation() = Location(provider).also {
            it.time = time; it.latitude = latitude; it.longitude = longitude
            it.altitude = altitude; it.accuracy = accuracy
        }
    }

    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_ENABLED, false)

    fun setEnabled(activity: Activity, enabled: Boolean): Boolean {
        activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY_ENABLED, enabled).apply()
        if (!enabled) { stop(); return true }
        if (!hasPermission(activity)) {
            activity.requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION), PERMISSION_REQUEST)
            return false
        }
        start(activity.applicationContext)
        return true
    }

    fun start(context: Context) {
        if (!isEnabled(context) || !hasPermission(context)) return
        app = context.applicationContext
        val lm = context.getSystemService(LocationManager::class.java)
        manager = lm
        runCatching { lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 15_000L, 5f, this) }
        runCatching { lm.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 30_000L, 20f, this) }
        listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
            .filter { System.currentTimeMillis() - it.time <= MAX_AGE_MS }
            .forEach(::onLocationChanged)
    }

    fun stop() {
        manager?.let { runCatching { it.removeUpdates(this) } }
        manager = null
    }

    override fun onLocationChanged(location: Location) {
        if (!location.latitude.isFinite() || !location.longitude.isFinite() || location.accuracy > 200f) return
        val context = app ?: return
        synchronized(this) {
            val now = System.currentTimeMillis()
            val samples = load(context).filter { now - it.time <= MAX_AGE_MS }.toMutableList()
            val sample = Sample(location.time.takeIf { it > 0 } ?: now, location.latitude, location.longitude,
                if (location.hasAltitude()) location.altitude else 0.0,
                if (location.hasAccuracy()) location.accuracy else 0f, location.provider ?: "phone")
            val previous = samples.lastOrNull()
            if (previous == null || abs(previous.time - sample.time) >= 5_000 ||
                abs(previous.latitude - sample.latitude) > 0.00001 || abs(previous.longitude - sample.longitude) > 0.00001) {
                samples += sample
                save(context, samples.takeLast(MAX_SAMPLES))
            }
        }
    }

    /**
     * Congela la posicion mas reciente con la hora en la que la camara empezo
     * a capturar. No solicitamos un GPS nuevo aqui: un fix en frio llegaria
     * varios segundos tarde.
     */
    fun recordCapture(context: Context, capturedAt: Long = System.currentTimeMillis()): Boolean {
        if (!isEnabled(context)) return false
        return synchronized(this) {
            val samples = load(context).filter { abs(capturedAt - it.time) <= MAX_AGE_MS }.toMutableList()
            val source = samples.minByOrNull { abs(it.time - capturedAt) }
                ?.takeIf { abs(it.time - capturedAt) <= MAX_CAPTURE_FIX_AGE_MS }
                ?: return@synchronized false
            samples += source.copy(time = capturedAt, provider = "capture:${source.provider}")
            save(context, samples.takeLast(MAX_SAMPLES))
            true
        }
    }

    fun closest(context: Context, createdTime: String): Location? {
        val captured = parseCaptureTimes(createdTime)
        if (captured.isEmpty()) return null
        return synchronized(this) {
            load(context).minByOrNull { sample -> captured.minOf { abs(sample.time - it) } }
                ?.takeIf { sample -> captured.minOf { abs(sample.time - it) } <= MAX_MATCH_MS }
                ?.asLocation()
        }
    }

    /**
     * Algunas Sony antiguas etiquetan createdTime con +00:00 aunque el texto
     * contiene la hora local configurada en la camara. Conservamos ambas
     * interpretaciones y el historial GPS decide cual es coherente.
     */
    internal fun parseCaptureTimes(value: String, zone: ZoneId = ZoneId.systemDefault()): List<Long> {
        if (value.isBlank()) return emptyList()
        val candidates = linkedSetOf<Long>()
        runCatching {
            val offset = OffsetDateTime.parse(value)
            candidates += offset.toInstant().toEpochMilli()
            candidates += offset.toLocalDateTime().atZone(zone).toInstant().toEpochMilli()
        }
        val formats = listOf(
            DateTimeFormatter.ISO_LOCAL_DATE_TIME,
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"),
            DateTimeFormatter.ofPattern("yyyy:MM:dd HH:mm:ss"),
        )
        for (format in formats) try {
            candidates += LocalDateTime.parse(value, format).atZone(zone).toInstant().toEpochMilli()
        } catch (_: DateTimeParseException) { }
        return candidates.toList()
    }

    private fun load(context: Context): List<Sample> {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_SAMPLES, "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) array.optJSONObject(i)?.let { item ->
                    add(Sample(item.getLong("t"), item.getDouble("lat"), item.getDouble("lon"),
                        item.optDouble("alt", 0.0), item.optDouble("acc", 0.0).toFloat(),
                        item.optString("provider", "phone")))
                }
            }
        }.getOrDefault(emptyList())
    }

    private fun save(context: Context, samples: List<Sample>) {
        val array = JSONArray()
        samples.forEach { s -> array.put(JSONObject().put("t", s.time).put("lat", s.latitude)
            .put("lon", s.longitude).put("alt", s.altitude).put("acc", s.accuracy)
            .put("provider", s.provider)) }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_SAMPLES, array.toString()).apply()
    }

    private fun hasPermission(context: Context) =
        context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    @Suppress("UNUSED_PARAMETER") override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
    override fun onProviderEnabled(provider: String) = Unit
    override fun onProviderDisabled(provider: String) = Unit
}
