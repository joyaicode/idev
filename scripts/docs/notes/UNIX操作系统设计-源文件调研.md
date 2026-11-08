# 《UNIX操作系统设计》源文件调研

## 结论

- **已落地**：`scripts/docs/UNIX操作系统设计.pdf` 已替换为推荐英文原版 PDF（485 页、484 页文本层），并生成 `scripts/docs/notes/UNIX操作系统设计-全文.txt`。
- **推荐使用英文原版**：Internet Archive 条目 `DesignUNIXOperatingSystem` 中的 `DesignUnixOs.pdf`，以及 GitHub 上的同一字节文件 `the_design_of_the_unix_operating_system.pdf`。该版本共 485 页，484 页带文本层，平均 2031 字符/页，仅第 4 页为空白图片页；文件大小 11,122,120 字节，MD5 `d384a58346f7ebb94cef1b66233d237e`。可直接用于精读和检索。
- **如需中文译本**：GitHub `jyfc/ebook` 与 `lancetw/ebook-1` 中的 `UNIX操作系统设计.pdf` 为同一份 369 页扫描版，文件大小 9,106,786 字节，MD5 `eec068ea1406e9c7fcb50ddc3746a635`。PDF 本身无文本层，但用本仓 `scripts/docs/ocr_pdf.swift` 可稳定识别第 1、100、200、300 页等抽样页，正文可读。
- **不推荐使用**：本地 `scripts/docs/UNIX操作系统设计.pdf` 与 GitHub `Dujltqzv/Some-Many-Books` 源文件均为 367 页空白扫描页，无文本层，OCR 也无有效内容。
- 另一个 GitHub 候选 `CharlesLeex/ebooks/linux/UNIX操作系统设计.pdf` 体积 72MB，但本地 PDFKit 报“无法打开 PDF”，不建议使用。
- 公开可得不等于版权授权；以上只说明技术可读性，不构成版权结论。

## 检索范围

检索对象包括：

- Internet Archive：英文书名、中文书名、罗马化题名 `Unix cao zuo xi tong she ji`。
- GitHub / 公共代码索引：精确书名、`DesignUnixOs.pdf`、`the_design_of_the_unix_operating_system.pdf`。
- Bing / Google / Jina 代理检索：中英文书名 + `PDF`、`文本层`、`epub`。

命中并实测的候选如下。

## 候选源与验证

| 语言/版本 | 来源 | 页数 | 文本层 | OCR | 结论 |
|---|---|---:|---|---|---|
| 英文原版 | `https://archive.org/details/DesignUNIXOperatingSystem` | 485 | 484 页有文本，均值 2031 字符/页；仅 p4 无文本 | 不需要 | **推荐** |
| 英文原版（同文件） | `https://raw.githubusercontent.com/jyfc/ebook/master/03_operating_system/the_design_of_the_unix_operating_system.pdf` | 485 | 同上；与 Archive 文件 MD5 完全一致 | 不需要 | **推荐**，下载更稳定 |
| 中文译本扫描版 | `https://raw.githubusercontent.com/jyfc/ebook/master/03_operating_system/UNIX操作系统设计.pdf` | 369 | 0 页有文本 | 第 1、100、200、300 页抽样可读 | 可用，适合 OCR |
| 中文译本扫描版（同文件） | `https://raw.githubusercontent.com/lancetw/ebook-1/master/03_operating_system/UNIX操作系统设计.pdf` | 369 | 与上一行 MD5 完全一致 | 同上 | 同一文件的重复镜像 |
| 已知空白源 | `scripts/docs/UNIX操作系统设计.pdf` | 367 | 0 页有文本，整本空白 | 无有效内容 | **不推荐** |
| 已知空白源 | `https://raw.githubusercontent.com/Dujltqzv/Some-Many-Books/main/PDF-file/linux/UNIX操作系统设计.pdf` | 367 | 同上 | 无有效内容 | **不推荐** |
| 大体积候选 | `https://raw.githubusercontent.com/CharlesLeex/ebooks/master/linux/UNIX操作系统设计.pdf` | 未能打开 | 本地 PDFKit 报错 | 未继续 | 不推荐 |

## 验证命令与结果

### 英文原版

```bash
curl -L --fail --max-time 120 \
  -o /private/tmp/the_design_of_the_unix_operating_system.pdf \
  'https://raw.githubusercontent.com/jyfc/ebook/master/03_operating_system/the_design_of_the_unix_operating_system.pdf'

swift scripts/docs/pdf_text.swift \
  /private/tmp/the_design_of_the_unix_operating_system.pdf \
  /dev/null --probe
```

输出：

```text
PDF /private/tmp/the_design_of_the_unix_operating_system.pdf: 共 485 页
探测: 共485页, 有文本484页, 合计983464字符, 均值2031/页
零文本页: p4
```

同文件校验：

```text
Archive:   d384a58346f7ebb94cef1b66233d237e
GitHub:    d384a58346f7ebb94cef1b66233d237e
```

### 中文扫描版

```bash
curl -L --fail --max-time 120 \
  -o /private/tmp/UNIX操作系统设计.pdf \
  'https://raw.githubusercontent.com/jyfc/ebook/master/03_operating_system/UNIX操作系统设计.pdf'

swift scripts/docs/pdf_text.swift \
  /private/tmp/UNIX操作系统设计.pdf \
  /dev/null --probe
```

输出：

```text
PDF /private/tmp/UNIX操作系统设计.pdf: 共 369 页
探测: 共369页, 有文本0页, 合计0字符, 均值0/页
零文本页: p1-369
```

OCR 抽样：

```bash
swift scripts/docs/ocr_pdf.swift \
  /private/tmp/UNIX操作系统设计.pdf \
  /private/tmp/UNIX操作系统设计-ocr.txt 1 5

swift scripts/docs/ocr_pdf.swift \
  /private/tmp/UNIX操作系统设计.pdf \
  /private/tmp/UNIX操作系统设计-page100.txt 100 100

swift scripts/docs/ocr_pdf.swift \
  /private/tmp/UNIX操作系统设计.pdf \
  /private/tmp/UNIX操作系统设计-page200.txt 200 200

swift scripts/docs/ocr_pdf.swift \
  /private/tmp/UNIX操作系统设计.pdf \
  /private/tmp/UNIX操作系统设计-page300.txt 300 300
```

抽样结论：

- 第 1–5 页：封面、版权页、译者前言、作者前言可读。
- 第 100 页：第 5 章文件系统内容可读。
- 第 200 页：第 8 章进程调度和时间内容可读。
- 第 300 页：第 11 章进程间通信内容可读。

同文件校验：

```text
jyfc/ebook:    eec068ea1406e9c7fcb50ddc3746a635
lancetw/ebook-1: eec068ea1406e9c7fcb50ddc3746a635
```

## 建议

- **优先使用英文原版 PDF**：它是带文本层的完整 485 页版本，检索和精读成本最低。
- **若必须使用中文译本**：用 GitHub 扫描版跑全本 OCR；抽样页已证明可读。
- **不要继续使用本地 367 页空白扫描件或 Some-Many-Books 源**。
