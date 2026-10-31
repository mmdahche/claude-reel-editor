import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count == 3 else { print("usage: seg <in_dir> <out_dir>"); exit(1) }
let inDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
let files = try FileManager.default.contentsOfDirectory(atPath: inDir.path).filter { $0.hasSuffix(".png") || $0.hasSuffix(".jpg") }.sorted()
let ctx = CIContext()
let gray = CGColorSpaceCreateDeviceGray()
for f in files {
    let url = inDir.appendingPathComponent(f)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil), let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { continue }
    let req = VNGeneratePersonSegmentationRequest()
    req.qualityLevel = .accurate
    req.outputPixelFormat = kCVPixelFormatType_OneComponent8
    let h = VNImageRequestHandler(cgImage: img, options: [:])
    try h.perform([req])
    guard let m = req.results?.first?.pixelBuffer else { print("no mask \(f)"); continue }
    var ci = CIImage(cvPixelBuffer: m)
    let sx = CGFloat(img.width) / ci.extent.width, sy = CGFloat(img.height) / ci.extent.height
    ci = ci.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
    let out = outDir.appendingPathComponent(f.replacingOccurrences(of: ".jpg", with: ".png"))
    try ctx.writePNGRepresentation(of: ci, to: out, format: .L8, colorSpace: gray)
}
print("done \(files.count)")
