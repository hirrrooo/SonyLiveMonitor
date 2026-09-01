package com.otoniel.sonylivemonitor

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.hardware.usb.UsbDevice
import android.os.SystemClock
import android.view.SurfaceView
import com.jiangdg.ausbc.MultiCameraClient
import com.jiangdg.ausbc.callback.ICameraStateCallBack
import com.jiangdg.ausbc.callback.IDeviceConnectCallBack
import com.jiangdg.ausbc.callback.IPreviewDataCallBack
import com.jiangdg.ausbc.camera.CameraUVC
import com.jiangdg.ausbc.camera.bean.CameraRequest
import com.jiangdg.usb.USBMonitor
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingDeque
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Entrada para una capturadora HDMI que se anuncie como USB Video Class. */
class UvcVideoSource(context: Context, private val previewSink: SurfaceView) {
    data class Frame(val bitmap: Bitmap, val receivedAtMs: Long)

    private val appContext = context.applicationContext
    private val frames = LinkedBlockingDeque<Frame>(1)
    private val converting = AtomicBoolean(false)
    private val converter = Executors.newSingleThreadExecutor()
    private val cameras = mutableMapOf<Int, MultiCameraClient.ICamera>()
    private var activeCamera: MultiCameraClient.ICamera? = null

    @Volatile var status = "waiting for an HDMI/UVC capture device"
        private set
    @Volatile var framesDropped = 0
        private set

    private val previewCallback = object : IPreviewDataCallBack {
        override fun onPreviewData(
            data: ByteArray?, width: Int, height: Int,
            format: IPreviewDataCallBack.DataFormat,
        ) {
            if (data == null || format != IPreviewDataCallBack.DataFormat.NV21) return
            // Nunca encolamos conversiones: si la CPU sigue con el frame anterior,
            // este se descarta para conservar la minima latencia posible.
            if (!converting.compareAndSet(false, true)) {
                framesDropped++
                return
            }
            converter.execute {
                try {
                    val jpeg = ByteArrayOutputStream(data.size / 2)
                    YuvImage(data, ImageFormat.NV21, width, height, null)
                        .compressToJpeg(Rect(0, 0, width, height), 88, jpeg)
                    val bytes = jpeg.toByteArray()
                    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@execute
                    val frame = Frame(bitmap, SystemClock.elapsedRealtime())
                    val old = frames.pollFirst()
                    old?.bitmap?.recycle()
                    if (old != null) framesDropped++
                    frames.offerFirst(frame)
                } finally {
                    converting.set(false)
                }
            }
        }
    }

    private val client: MultiCameraClient by lazy {
        MultiCameraClient(appContext, object : IDeviceConnectCallBack {
            override fun onAttachDev(device: UsbDevice?) {
                device ?: return
                cameras[device.deviceId] = CameraUVC(appContext, device)
                status = "requesting permission for the HDMI capture device"
                client.requestPermission(device)
            }

            override fun onDetachDec(device: UsbDevice?) {
                val camera = cameras.remove(device?.deviceId)
                camera?.closeCamera()
                if (activeCamera === camera) activeCamera = null
                status = "HDMI capture device disconnected"
            }

            override fun onConnectDev(device: UsbDevice?, ctrlBlock: USBMonitor.UsbControlBlock?) {
                val camera = cameras[device?.deviceId] ?: return
                ctrlBlock ?: return
                activeCamera?.takeIf { it !== camera }?.closeCamera()
                activeCamera = camera
                camera.setUsbControlBlock(ctrlBlock)
                camera.addPreviewDataCallBack(previewCallback)
                camera.setCameraStateCallBack(object : ICameraStateCallBack {
                    override fun onCameraState(
                        self: MultiCameraClient.ICamera, code: ICameraStateCallBack.State,
                        msg: String?,
                    ) {
                        status = when (code) {
                            ICameraStateCallBack.State.OPENED -> "HDMI/UVC"
                            ICameraStateCallBack.State.CLOSED -> "HDMI capture stopped"
                            ICameraStateCallBack.State.ERROR -> msg ?: "HDMI capture error"
                        }
                    }
                })

                val request = CameraRequest.Builder()
                    .setPreviewWidth(1280)
                    .setPreviewHeight(720)
                    .setRenderMode(CameraRequest.RenderMode.NORMAL)
                    .setPreviewFormat(CameraRequest.PreviewFormat.FORMAT_MJPEG)
                    .setAudioSource(CameraRequest.AudioSource.NONE)
                    .create()
                status = "opening HDMI capture"
                camera.openCamera(previewSink, request)
            }

            override fun onDisConnectDec(device: UsbDevice?, ctrlBlock: USBMonitor.UsbControlBlock?) {
                cameras[device?.deviceId]?.closeCamera()
                status = "HDMI capture device disconnected"
            }

            override fun onCancelDev(device: UsbDevice?) {
                status = "USB permission denied"
            }
        })
    }

    fun start() {
        framesDropped = 0
        status = "waiting for an HDMI/UVC capture device"
        client.register()
    }

    fun awaitFrame(timeoutMs: Long): Frame? = frames.pollFirst(timeoutMs, TimeUnit.MILLISECONDS)

    fun stop() {
        activeCamera?.removePreviewDataCallBack(previewCallback)
        cameras.values.forEach { it.closeCamera() }
        cameras.clear()
        activeCamera = null
        client.unRegister()
        frames.forEach { it.bitmap.recycle() }
        frames.clear()
    }

    fun destroy() {
        stop()
        client.destroy()
        converter.shutdownNow()
    }
}
