#!/usr/bin/swift
// 扫描版 PDF → 文本（macOS Vision OCR，中文优先）
// 用法: swift ocr_pdf.swift <pdf路径> <输出txt> [起始页1基] [结束页]
import Foundation
import CoreGraphics
import Vision

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("用法: swift ocr_pdf.swift <pdf> <out.txt> [起页] [止页]\n".data(using: .utf8)!)
    exit(2)
}
let pdfURL = URL(fileURLWithPath: args[1])
let outPath = args[2]
let startPage = args.count > 3 ? max(Int(args[3]) ?? 1, 1) : 1
let endPage = args.count > 4 ? (Int(args[4]) ?? 0) : 0

guard let pdfDoc = CGPDFDocument(pdfURL as CFURL) else {
    FileHandle.standardError.write("无法打开 PDF: \(args[1])\n".data(using: .utf8)!)
    exit(3)
}
let pageCount = pdfDoc.numberOfPages
let last = endPage > 0 ? min(endPage, pageCount) : pageCount
guard last >= startPage else { exit(0) }

var all = ""
let scale: CGFloat = 2.6

for i in startPage...last {
    autoreleasepool {
        guard let page = pdfDoc.page(at: i) else { return }
        let rect = page.getBoxRect(.mediaBox)
        let w = max(Int(rect.width * scale), 8)
        let h = max(Int(rect.height * scale), 8)
        guard let ctx = CGContext(
            data: nil, width: w, height: h,
            bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return }
        ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: CGFloat(w), height: CGFloat(h)))
        ctx.scaleBy(x: scale, y: scale)
        ctx.translateBy(x: -rect.origin.x, y: -rect.origin.y)
        ctx.drawPDFPage(page)
        guard let img = ctx.makeImage() else { return }

        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
        req.usesLanguageCorrection = true
        let handler = VNImageRequestHandler(cgImage: img, options: [:])
        try? handler.perform([req])
        let text = (req.results ?? []).compactMap {
            $0.topCandidates(1).first?.string
        }.joined(separator: "\n")
        all += "\n===== [PDF第\(i)页] =====\n" + text + "\n"
        if i % 20 == 0 {
            FileHandle.standardError.write("  已识别 \(i)/\(last) 页\n".data(using: .utf8)!)
        }
    }
}

let tmp = outPath + ".part"
try? all.data(using: .utf8)?.write(to: URL(fileURLWithPath: tmp))
// 原子替换
_ = try? FileManager.default.removeItem(atPath: outPath)
if ((try? FileManager.default.moveItem(atPath: tmp, toPath: outPath)) as Void?? != nil) {}
FileHandle.standardError.write("完成: \(outPath) 共\(last-startPage+1)页\n".data(using: .utf8)!)