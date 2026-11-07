#!/usr/bin/swift
// 文本层 PDF → 文本（macOS PDFKit，逐页 string 提取）
// 用法: swift pdf_text.swift <pdf路径> <输出txt> [起始页1基] [结束页] [--probe]
//   --probe: 打印文本层统计摘要（页数/有文本页/零文本页区间，不写文件）
import Foundation
import PDFKit

let args = CommandLine.arguments
let probe = args.contains("--probe")
guard args.count >= 3 else {
    FileHandle.standardError.write("用法: swift pdf_text.swift <pdf> <out.txt> [起页] [止页] [--probe]\n".data(using: .utf8)!)
    exit(2)
}
let pdfURL = URL(fileURLWithPath: args[1])
let outPath = args[2]
let rest = Array(args.dropFirst(3).filter { !$0.hasPrefix("--") })
let startPage = rest.count > 0 ? max(Int(rest[0]) ?? 1, 1) : 1
let endPage = rest.count > 1 ? (Int(rest[1]) ?? 0) : 0

guard let pdfDoc = PDFDocument(url: pdfURL) else {
    FileHandle.standardError.write("无法打开 PDF: \(args[1])\n".data(using: .utf8)!)
    exit(3)
}
let pageCount = pdfDoc.pageCount
FileHandle.standardError.write("PDF \(args[1]): 共 \(pageCount) 页\n".data(using: .utf8)!)

let last = endPage > 0 ? min(endPage, pageCount) : pageCount
guard last >= startPage else { exit(0) }

var all = ""
var totalChars = 0
var pagesWithText = 0
var zeroPages: [Int] = []  // 探测模式记录零文本页

for i in startPage...last {
    autoreleasepool {
        guard let page = pdfDoc.page(at: i - 1) else { return }  // PDFKit 0 基
        let text = page.string ?? ""
        let n = text.count
        totalChars += n
        if n > 0 { pagesWithText += 1 } else { zeroPages.append(i) }
        if probe { return }
        all += "\n===== [PDF第\(i)页] =====\n" + text + "\n"
        if i % 50 == 0 {
            FileHandle.standardError.write("  已提取 \(i)/\(last) 页\n".data(using: .utf8)!)
        }
    }
}

if probe {
    // 零文本页压缩为区间
    var ranges: [String] = []
    var idx = 0
    while idx < zeroPages.count {
        let s = zeroPages[idx]
        var e = s
        while idx + 1 < zeroPages.count && zeroPages[idx + 1] == e + 1 { idx += 1; e = zeroPages[idx] }
        ranges.append(s == e ? "p\(s)" : "p\(s)-\(e)")
        idx += 1
    }
    let avg = pagesWithText > 0 ? totalChars / pagesWithText : 0
    FileHandle.standardError.write("探测: 共\(pageCount)页, 有文本\(pagesWithText)页, 合计\(totalChars)字符, 均值\(avg)/页\n".data(using: .utf8)!)
    if !ranges.isEmpty {
        let shown = ranges.prefix(30).joined(separator: ",")
        let more = ranges.count > 30 ? " …(共\(ranges.count)段)" : ""
        FileHandle.standardError.write("零文本页: \(shown)\(more)\n".data(using: .utf8)!)
    } else {
        FileHandle.standardError.write("零文本页: 无\n".data(using: .utf8)!)
    }
    exit(0)
}

let tmp = outPath + ".part"
try? all.data(using: .utf8)?.write(to: URL(fileURLWithPath: tmp))
// 原子替换
_ = try? FileManager.default.removeItem(atPath: outPath)
if ((try? FileManager.default.moveItem(atPath: tmp, toPath: outPath)) as Void?? != nil) {}
FileHandle.standardError.write("完成: \(outPath) 共\(last-startPage+1)页, 有文本\(pagesWithText)页, 合计\(totalChars)字符\n".data(using: .utf8)!)