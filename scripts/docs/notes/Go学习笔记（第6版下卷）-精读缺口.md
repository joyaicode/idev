# 《Go学习笔记（第6版下卷）》精读缺口报告

> 源文本：`scripts/docs/notes/Go学习笔记（第6版下卷）-全文.txt`（雨痕《Go 学习笔记》第 6 版下卷，基于 Go 1.10，66 页带文本层，经 macOS PDFKit 逐页提取）。本报告为第 31 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书「第 N 页」序号只作溯源，不建第二套编号。Go 运行时源码（启动序列、内存分配器、GC 标记/清扫、scavenge 归还）是运行时实现内容，不进产品仓真源；过程类经验（不猜性能、显式释放、确定性初始化）落阶段页，不改 T/C/P/R 计数。

## 一、精读范围

全书 66 页读完，主区间如下（行号指 `Go学习笔记（第6版下卷）-全文.txt`）：

- **启动序列（第 7–17 页）**：`rt0_linux_amd64.s` / `asm_amd64.s` 入口点、`runtime·rt0_go` 引导（args → osinit → schedinit → newproc → mstart）、`schedinit`（stackinit / mallocinit / gcinit / GOMAXPROCS）、`runtime.main`（maxstacksize / sysmon / runtime_init / main_init / main_main）、init 执行顺序（runtime.init → main.init → main.main）。
- **内存分配器（第 18–66 页）**：`malloc.go`（mallocgc / newobject / largeAlloc / tiny 分配器 / zerobase）、`sizeclasses.go`（67 个 size class）、`mheap` / `mspan` / `mcentral` / `mcache` 四层结构、spans / bitmap / arena 布局、span 分配/释放（allocSpanLocked / freeSpanLocked / grow / sysAlloc）、GC 标记/清扫（markroot / flushmcache / sweep / sweepgen 双缓冲）、`sysmon` / scavenge（5 分钟未使用 span 归还 OS）、`fixalloc`（定长 free-list）、`persistentAlloc`（持久分配）。

重点复核段落：第 7–9 页启动入口（L22–L70）、第 13 页 `schedinit`（L191–L213）、第 14 页 `runtime.main`（L224–L252）、第 17 页 init 顺序（L278–L289）、第 24–26 页 arena 保留与 `sysReserve`（L402–L432）、第 28–30 页 `newobject` / zerobase（L462–L505）、第 49–50 页 tiny 分配器（L1430–L1468）、第 56–60 页 scavenge 归还（L1513–L1568）、第 61–63 页 fixalloc（L1585–L1620）。

## 二、对照结论

### 1. 主体内容已被真源覆盖或属运行时实现

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 启动序列确定性：`runtime.init` → `main.init` → `main.main` 固定次序，包内按文件顺序（第 15–17 页 `go tool objdump` 展示 init.0…init.5 顺序调用） | C23（顺序约定写进契约，先看签名就知道必须什么顺序）/ T5（单一事实源） | 承载 |
| `GOMAXPROCS` 缺省取逻辑 CPU 数、可显式覆盖（第 13 页 `procs := ncpu`，`GOMAXPROCS` 环境变量覆盖） | C13（默认只允许写在显式配置，禁止请求期猜）/ C17（环境差异收拢为构造期选择） | 承载 |
| 大对象（> 32KB）直接向堆申请、小对象走 per-P cache（第 28 页 `mallocgc` 注释「Small objects are allocated from the per-P cache's free lists」） | T9（性能优化先测量，不靠猜）/ 运行时实现 | 承载（运行时） |
| 0 字节分配共享 `zerobase`、`[0]int` 与 `struct{}` 同地址（第 29–30 页 `&a`/`&b` 同 `0x4c2a00`） | 语言实现事实 | 不落（语言课） |
| tiny 分配器：≤16 字节无指针对象合并进同一 16 字节槽（第 49–50 页 `maxTinySize = 16`） | 运行时实现 | 不落（运行时） |
| 5 分钟未使用 span 归还 OS（第 56 页 `scavengelimit := int64(5 * 60 * 1e9)`，`sysmon` 周期 `scavenge`） | C19（显式释放，不依赖 GC/finalizer 隐式清理）/ T11（输出克制） | 承载 |
| GC 标记/清扫双缓冲：`allocBits` 与 `gcmarkBits` 交替、`sweepgen` 世代计数（第 46–47、53 页） | 运行时实现 | 不落（运行时） |
| fixalloc 定长 free-list、persistentAlloc 持久分配（第 61–65 页） | 运行时实现（经典分配器模式） | 不落（运行时） |
| 悬空指针 / 释放后使用：`spans` 数组按页索引、`freeSpanLocked` 合并相邻空闲 span（第 35–37 页） | C19（显式释放）/ C39（持有资源/身份类型禁止按值复制） | 承载 |

### 2. 语言特性 / 运行时源码 / 工具链知识不落

第 7–66 页的全部内容（启动序列、内存分配器、GC、scavenge、fixalloc、persistentAlloc）是 Go 1.10 运行时实现细节，不进产品仓真源（`coding.md` 文首「不抄目录」边界）；`gdb` / `go tool objdump` / `go build -gcflags` 是工具用法，不进真源。

## 三、真缺口

**无。** 本书可推广的过程类经验（确定性初始化顺序、缺省值显式配置、不猜性能先测量、显式释放不依赖隐式清理、输出克制）均已被 C23 / C13 / T9 / C19 / T11 承载；其余全部是 Go 1.10 运行时实现（启动、分配器、GC、scavenge）与语言事实，不进真源。与第 4 版「第二部分 源码」同源，无新增可落条目。

## 四、重点候选裁定（防后人重复发现）

1. **init 顺序确定性（第 15–17 页）不单列。** C23 已承载（顺序约定写进契约），且属语言特性。
2. **GOMAXPROCS 缺省/覆盖（第 13 页）不单列。** C13 / C17 已承载（默认显式配置、环境差异收拢）。
3. **大对象/小对象分路分配（第 28 页）不单列。** T9 已承载（性能优化先测量），且属运行时实现。
4. **0 字节共享 zerobase（第 29–30 页）不单列。** 语言实现事实，不进真源。
5. **tiny 分配器（第 49–50 页）不单列。** 运行时实现，不进真源。
6. **scavenge 归还 OS（第 56–60 页）不单列。** C19 / T11 已承载（显式释放、输出克制），且属运行时优化。
7. **GC 双缓冲 / sweepgen（第 46–53 页）不单列。** 运行时实现，不进真源。
8. **fixalloc / persistentAlloc（第 61–65 页）不单列。** 经典分配器模式，运行时实现，不进真源。
9. **spans 按页索引 / 相邻 span 合并（第 35–37 页）不单列。** C19 / C39 已承载（显式释放、资源/身份类型）。

## 五、不建议落的内容

- Go 1.10 运行时源码（启动序列 rt0/asm/schedinit/runtime.main、内存分配器 mheap/mspan/mcentral/mcache/sizeclasses/tiny/zerobase、GC markroot/flushmcache/sweep/sweepgen、scavenge、fixalloc、persistentAlloc）：运行时实现细节，不进真源。
- 语言事实（0 字节共享地址、init 顺序、GOMAXPROCS 语义）：语言课内容，不进真源。
- 工具链（gdb、go tool objdump、go build -gcflags）：工具用法，不进真源。
- 与第 4 版「第二部分 源码」重复的内容：已由第 4 版报告裁定不落，本报告不重复。

