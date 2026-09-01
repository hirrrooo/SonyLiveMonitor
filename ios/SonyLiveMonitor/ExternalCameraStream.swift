import AVFoundation
import CoreImage
import UIKit

/// Entrada de una capturadora HDMI/UVC conectada a un iPad USB-C. iPhone queda
/// excluido expresamente: Apple solo publica las camaras externas en iPadOS.
final class ExternalCameraStream: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    struct Frame {
        let image: UIImage
        let receivedAt: TimeInterval
    }

    private let session = AVCaptureSession()
    private let captureQueue = DispatchQueue(label: "hdmi.uvc.capture", qos: .userInteractive)
    private let condition = NSCondition()
    private let ciContext = CIContext(options: [.cacheIntermediates: false])
    private var latestFrame: Frame?
    private var running = false

    private(set) var framesDropped = 0
    private(set) var status = "Waiting for an HDMI/UVC capture device"

    func start() throws {
        guard UIDevice.current.userInterfaceIdiom == .pad else {
            throw CameraError("HDMI/UVC is supported only on iPad")
        }

        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            break
        case .notDetermined:
            let semaphore = DispatchSemaphore(value: 0)
            var granted = false
            AVCaptureDevice.requestAccess(for: .video) { value in
                granted = value
                semaphore.signal()
            }
            semaphore.wait()
            guard granted else { throw CameraError("Camera permission denied") }
        default:
            throw CameraError("Camera permission denied")
        }

        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.external], mediaType: .video, position: .unspecified
        )
        guard let device = discovery.devices.first else {
            throw CameraError("Connect an HDMI/UVC capture device to this iPad")
        }

        let input = try AVCaptureDeviceInput(device: device)
        let output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        output.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ]
        output.setSampleBufferDelegate(self, queue: captureQueue)

        session.beginConfiguration()
        if session.canSetSessionPreset(.hd1920x1080) { session.sessionPreset = .hd1920x1080 }
        guard session.canAddInput(input), session.canAddOutput(output) else {
            session.commitConfiguration()
            throw CameraError("The capture device does not provide a compatible video stream")
        }
        session.addInput(input)
        session.addOutput(output)
        session.commitConfiguration()

        framesDropped = 0
        status = "HDMI/UVC: \(device.localizedName)"
        running = true
        session.startRunning()
    }

    func stop() {
        condition.lock()
        running = false
        latestFrame = nil
        condition.broadcast()
        condition.unlock()
        if session.isRunning { session.stopRunning() }
    }

    func awaitFrame(timeout: TimeInterval) -> Frame? {
        condition.lock()
        defer { condition.unlock() }
        if latestFrame == nil && running {
            _ = condition.wait(until: Date(timeIntervalSinceNow: timeout))
        }
        let frame = latestFrame
        latestFrame = nil
        return frame
    }

    func captureOutput(
        _ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        autoreleasepool {
            guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
            let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
            guard let cgImage = ciContext.createCGImage(ciImage, from: ciImage.extent) else { return }
            let frame = Frame(image: UIImage(cgImage: cgImage),
                              receivedAt: ProcessInfo.processInfo.systemUptime)
            condition.lock()
            if latestFrame != nil { framesDropped += 1 }
            latestFrame = frame
            condition.signal()
            condition.unlock()
        }
    }
}
