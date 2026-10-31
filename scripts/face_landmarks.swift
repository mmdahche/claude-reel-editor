// face_landmarks.swift - Apple Vision face + eye finder for face_fit.py (macOS, offline).
//
// Usage: face_landmarks <image> [<image> ...]
// Prints one JSON object per image, one per line:
//   {"file": "...", "w": 1080, "h": 1920, "faces": [{"bbox": [x, y, w, h], "confidence": 1,
//    "leftPupil": [x, y], "rightPupil": [x, y], "leftEye": [x, y], "rightEye": [x, y],
//    "roll": 0.0, "yaw": 0.0}]}
// All points are pixels with the origin at the TOP-left of the image. Eye points are the
// centre of Vision's eye outline; pupils are Vision's pupil landmark. Missing parts are left out.
// Built by face_fit.py with: swiftc -O face_landmarks.swift -o .bin/face_landmarks

import CoreGraphics
import Foundation
import ImageIO
import Vision

func loadImage(_ path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

func centre(_ region: VNFaceLandmarkRegion2D?, _ size: CGSize) -> [Double]? {
    guard let region = region, region.pointCount > 0 else { return nil }
    let pts = region.pointsInImage(imageSize: size)
    var x = 0.0, y = 0.0
    for p in pts { x += Double(p.x); y += Double(p.y) }
    let n = Double(pts.count)
    return [x / n, Double(size.height) - y / n]
}

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    }
}

let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty {
    FileHandle.standardError.write("usage: face_landmarks <image> [<image> ...]\n".data(using: .utf8)!)
    exit(2)
}

for path in paths {
    var rec: [String: Any] = ["file": path]
    guard let img = loadImage(path) else {
        rec["error"] = "could not read the image"
        emit(rec)
        continue
    }
    let w = Double(img.width), h = Double(img.height)
    let size = CGSize(width: w, height: h)
    rec["w"] = w
    rec["h"] = h
    let request = VNDetectFaceLandmarksRequest()
    let handler = VNImageRequestHandler(cgImage: img, options: [:])
    do {
        try handler.perform([request])
    } catch {
        rec["error"] = "Vision failed: \(error.localizedDescription)"
        emit(rec)
        continue
    }
    var faces: [[String: Any]] = []
    for f in request.results ?? [] {
        let bb = f.boundingBox  // normalised, origin bottom-left
        var face: [String: Any] = [
            "bbox": [Double(bb.minX) * w, (1 - Double(bb.maxY)) * h, Double(bb.width) * w, Double(bb.height) * h],
            "confidence": Double(f.confidence),
        ]
        if let roll = f.roll { face["roll"] = roll.doubleValue }
        if let yaw = f.yaw { face["yaw"] = yaw.doubleValue }
        if let lm = f.landmarks {
            if let p = centre(lm.leftPupil, size) { face["leftPupil"] = p }
            if let p = centre(lm.rightPupil, size) { face["rightPupil"] = p }
            if let p = centre(lm.leftEye, size) { face["leftEye"] = p }
            if let p = centre(lm.rightEye, size) { face["rightEye"] = p }
        }
        faces.append(face)
    }
    rec["faces"] = faces
    emit(rec)
}
