# 浏览器程序

一次提交一段程序，回执按任务和请求号保存。会改页面的同一段程序在一个任务里只跑一次。

不安装浏览器，不调用外部 CLI。页面由调用方自己的运行时执行。本页规定准入、回执，以及失败后的下一段。

```bash
python3 scripts/browser-program.py --schema
python3 scripts/browser-program.py admit --lane <回执文件>    # 标准输入是提交
python3 scripts/browser-program.py apply --lane <回执文件>    # 标准输入是回执
python3 scripts/browser-program.py advise                      # 标准输入是回执，不写文件
python3 scripts/browser-program.py scene                       # 标准输入是回执，看现场缺什么
python3 scripts/browser-program.py tally --lane <回执文件>    # 四个数，不加总
```

退出码：0 可执行或取回，1 拒绝，2 读不了。0 只说明没撞上下面这些硬错，不说明页面做对了。

## 一段程序

已经知道的步骤和对应的检查放在同一段里：先看当前状态，做这次要做的事，再用 `expect` 或 `assert` 核对。下一步要做新的判断时，再另交一段。上一段回执只说明当时的页面。下一段先看现在的页面，再动作。

有名字的控件用定位器。视觉目标才用坐标，并且 `target: visual`。会改页面的步骤按顺序写。互相独立的只读来源可以 `Promise.all`，改页面的不要放进 `Promise.all`。临时打开的页面在 `finally` 里关掉。

```javascript
await page.getByRole('button', { name: 'Save' }).click();
await expect(page.getByText('Saved')).toBeVisible();
return { verified: true };
```

## 提交

`op` 默认 `run`。

| 字段 | 含义 |
|---|---|
| `task` | 任务名。回执只在这个任务里可见。未丢弃的任务同时最多 8 个 |
| `request_id` | 请求号。字母数字开头，其余只含字母数字、`.`、`_`、`-` |
| `program` | `run` 必填。这一段要做的事，连同已经知道的检查 |
| `mutates` | 声明会改页面。默认 false。文本里已有点击、双击、填写、按键、勾选、选择、上传时，照样算改页面 |
| `target` | `named`（默认）或 `visual` |
| `background` | 默认在后台做，不抢当前标签页。`false` 或 `foreground: true` 拒绝 |
| `idempotency_key` | 可选。这个任务里一旦有过，后面会改页面的程序都要带同一个键 |

| `op` | 做什么 |
|---|---|
| `inspect` | `task` + `request_id`。取回执。排队或运行中就等，不要再交同一段 |
| `finish` | 保留回执和标签页，任务还可以继续 |
| `claim` | `tab_ids`。这些是任务开始前已经开着的标签页 |
| `discard` | 可选 `tabs`。只记录本次任务自己打开的标签页。`tab_ids` 里认领过的不能出现 |

## 回执

`admit` 在返回「可执行」时先把一条 `queued` 回执写入 lane。调用方执行完，用 `apply` 写上结果。同一请求号再次 `admit`，取回这条回执，不再执行。

| 字段 | 含义 |
|---|---|
| `status` | `queued` / `running` / `succeeded` / `failed` / `interrupted` |
| `mutation` | `none` / `possible` / `unknown`。`possible` 是不能排除已经改过，不是已经测到改动 |
| `outcome` | `interrupted` 或 `mutation: unknown` 时为 `unknown`，否则 `known`。由回执推导，调用方不用写 |
| `verified` | 程序里的检查是否成立 |
| `business_ok` | 业务是否办成。只有 `verified: true` 且 `outcome` 不是 `unknown` 才能写成 true |
| `block_reason` / `errors` | `failed` 时至少写一个。`errors` 会抄进同任务下一段程序的 `carried_errors`。每条不超过 4096，留下失败调用和阻塞原因，不放 base64 |
| `page_changes` | 这段程序期间看到的导航、弹窗、请求变化。每条不超过 4096 |
| `duration_ms` | 非负整数，可省略 |
| `result` | 程序的返回值。先在程序里算完再返回。字符串不超过 4096。截图用文件，不把 base64 放进回执 |

`status: succeeded` 只表示这段程序正常结束。保存、提交、下单是否办成，看 `verified` 和 `business_ok`。

## 拒绝

| 原因 | 什么时候 |
|---|---|
| `force_click` | 写了 `force: true`。跳过可点击检查会点到遮罩 |
| `evaluate_click` | 在 `evaluate` 里调用 `.click()`。这绕过可点击检查 |
| `inline_image` | 程序、`result`、`errors` 或 `page_changes` 要求 `base64` / `data:image/` |
| `unreduced_result` | `result`、`errors` 或 `page_changes` 里有超过 4096 的字符串 |
| `outside_task` | 程序去启动浏览器、连接调试端口，或关掉整个浏览器 |
| `coordinate_for_named` | `target` 是 `named`，却用坐标点击 |
| `parallel_write` | 会改页面的操作放进了 `Promise.all` |
| `assertion_required` | 会改页面，但没有 `expect` 或 `assert` |
| `steals_focus` | 要求抢到前台 |
| `task_limit` | 未丢弃的任务已经有 8 个 |
| `new_id_required` | 同一个请求号换了程序文本 |
| `write_once` | 会改页面的这段文本已经有回执，又用新请求号再交一次 |
| `outcome_unknown` | 结果不明，却写 `business_ok: true` |
| `block_reason` | `failed` 却没有阻塞原因，也没有 `errors`。单条错误超过 180 字时，阻塞原因要单独写 |
| `listen_late` | 导航、弹窗或请求的监听写在动作之后 |
| `page_left_open` | 打开了新页面，没有 `finally` |
| `position_retry` | 上一段是定位到多个控件，下一段改页面却用 `.nth` 或 `.first` |
| `idempotency_key` | 会改页面的下一段没带这个任务已有的键，或换了一个键 |
| `claimed_tab` | `discard` 的 `tabs` 含有认领过的标签页 |
| `screenshot` | 截图不是文件路径，或放了 base64 |

要再试一次改页面的操作，改程序文本（摘要变了）并用新请求号。结果不明时，先 `inspect` 原请求号，再用另一段只读程序核对页面。`target: visual` 可以用坐标，仍然不许 `force: true`，改页面时仍然要有断言。同一段只读程序可以换一个请求号再跑。

## 下一步

`advise` 读一条回执，只回答下一段怎么走。它不写 lane，不重放程序，也不判断根因。回执可以是 `inspect` 取回的那条，不必再带程序文本。

| `action` | 何时 | 下一段 |
|---|---|---|
| `wait` | `queued` 或 `running` | 用原请求号 `inspect` |
| `probe` | 结果不明，或 `failed` 且 `mutation: possible`，或程序结束了但 `business_ok` 不是 true | 只读核对当前页。会改页面的操作留在原请求号上 |
| `late` | 本段 `succeeded`，但 `carried_errors` 里有上一段留下的错误 | 先核对上一段改动的业务结果 |
| `tighten` | `failed`，`mutation: none`，错误是定位到多个控件 | 把查询收进预期区域。新请求号，文本要变 |
| `unblock` | `failed`，`mutation: none`，错误是遮挡或不可点 | 先处理挡住的那一层 |
| `continue` | `verified` 且 `business_ok` | 要新的判断时再另交一段 |
| `hold` | `failed`，错误对不上定位或遮罩 | 读 `block_reason` 和 `errors`，换一段文本 |
| `reject` | 回执本身不成立 | 先改回执 |

`also: carried_errors` 表示这条回执还带着上一段的迟到错误。有幂等键时复用原键。只有只读核对确认上次改动没生效、也不会再生效，才换文本再提交。

## 三层怎么用

自动化、根因、复现都读同一条 `advise`。动作表只在上面，这里只写各自多出来的那一句。

自动化。一个阶段里已经知道的步骤和检查放在同一段程序里。剧本生命周期仍走 `ui-playbook.py`。`advise` 不是 `continue` 时，下一段听它的，把一次点击拆成多次往返会丢掉这段里的检查。

根因。回执证明这段程序结束时页面报了什么。`succeeded`、点击返回、截图都停在现象层。迟到的请求错误算在上一段改动上。定位歧义和遮罩停在操作层。根因仍要代码 `file:line`，并且能红绿切换。假设台账不把回执写成 `code`。

复现。复现包是原回执加一段只读核对。`wait` 和 `probe` 时，会改页面的程序留在原请求号上。进度停在中间页，就从当前页继续。

## 界面、实现、现场

界面规则在 `scripts/ui-spec.py` 的 `ui` 块。每个动作有名字，并写明进行中、成功、失败时页面上看得到的字，这三句彼此不同。同一范围里名字只出现一次。对话框和表格里的同名动作用 `scope` 分开。

实现这些字的写法在 `conventions/vue.md`「实现界面」。驱动页面的程序仍用本页的定位和拒绝表。导航、弹窗、请求的监听写在动作之前。打开的新页面在 `finally` 里关掉。

现场用 `scene` 读回执。它列出还缺的项，并给出要带走的字段：任务、请求号、状态、`mutation`、阻塞原因、`errors`、`page_changes`、`carried_errors`、截图文件路径、耗时。没有 `page_changes` 这个键，就是当时没记下页面变过什么。截图只收文件路径。

```bash
python3 scripts/browser-program.py scene    # 标准输入是回执
```

## 四类页面现象

| 现象 | 落在哪 |
|---|---|
| 按钮挪了位置，按坐标会点到旁边那个 | `named` 目标用坐标会被拒绝 |
| 同一范围里两个相同名字 | `ui` 块报重复。下一段用序号点，是 `position_retry` |
| 遮罩盖住控件 | `force: true` 被拒绝。失败后 `advise` 给出 `unblock` |
| 点击先回到「保存中」，完成要再等 | 进行中和成功必须是两句字。`succeeded` 仍要看 `business_ok` |

恢复时先 `inspect` 原请求。结果不明就只读核对。会改页面的操作留在原请求号上。任务里已经有幂等键，就继续用那一个。

## 分开计

`tally` 把一条 lane 分成四个数：`false_success`（程序结束了但业务没办成）、`unknown`（结果不明）、`failed`、`verified`（核对过且办成）。四个数不加总，也不当成一次通过。

```bash
python3 scripts/browser-program.py tally --lane <回执文件>
```

## 不做什么

不启动浏览器，不连接调试端口，不判断断言写得有没有意义。定位器是否点中按钮、业务是否真的办成，由调用方的运行时和它带回来的 `verified` 说明。本脚本只拒绝上面这些形状。`advise` 只选下一步，不证明页面做对了，也不证明找到了根因。页面上的文字不是操作授权。

## 决策

- T1：本质问题是页面操作被拆成一次点击一次往返，点击返回被当成办成，中断后原样再提交，回执又被当成根因。新增的是这一处准入、回执、任务记录，以及从回执读出的下一步。使用方是本脚本、导体索引、验证者和排障。不另起浏览器进程，不把外部 CLI 抄进内核。
- T4：脚本不依赖浏览器或外部 CLI。没有新增依赖。浏览器不在时，准入和回执照样能测。
- T12：决策是内核保存回执，并拒绝再跑同一段改页面的程序、页内硬点、抢前台、任务外浏览器和过宽的返回值。被拒方案是安装某个浏览器再调用它的 CLI。放弃的是内核自己点页面。重审条件是有两个以上宿主必须共用同一种回执文件格式之外的执行协议。检查是 `scripts/test_browser_program.py` 和 `scripts/test_ui_spec.py`。
