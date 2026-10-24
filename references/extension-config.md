# 扩展与配置

产线扩展根上的三份配置，每个键的解释只在本页。配置文件里只写值。新增键先在本页加一行解释和示例，再让代码去读。`scripts/config-doc-check.py` 核对内核实际读取的键都在这里。

会话仓写了 `extension_root` 时，三份文件都读扩展根，不在会话仓再放一份。

## `marker.yaml`

认出这份仓库已经接入 idev。没有这个文件，或 `marker` 不是 `idev`，后续会话当作未接入。

| 键 | 必填 | 解释 |
|---|---|---|
| `marker` | 是 | 固定写 `idev`。其它值等于没有这份标记 |
| `id` | 否 | 产品 id。人没点产品名时，阶段页用它过滤。空着表示这份仓没有产品 id |
| `evolve` | 否 | `false` 或 `off` 不进自进化。`true` 或 `pilot` 才进。第一次保存写 `false` |
| `extension_root` | 否 | 指向另一份已标记仓库的相对路径，共享阶段页、配方和下面的 defaults。只允许一跳。绝对路径、`~`、以及目标自己再写 `extension_root`，都拒绝 |

```yaml
marker: idev
id: kafka
evolve: false
extension_root: ../joypaas
```

不共享扩展根时删掉 `extension_root`。`id` 用这份产线自己的产品 id。

## `extensions.yaml`

某一阶段要打开的产线页。路径相对 `.idev/`，不能跳出这个目录。缺文件或越界，`stage-extensions.py` 失败。

| 键 | 必填 | 解释 |
|---|---|---|
| `schema_version` | 是 | 只能是 `1` |
| `stages` | 是 | 阶段名到页面列表。名字必须是下面九个之一 |
| `path` | 与 `products` 成对 | 页面相对 `.idev/` 的路径 |
| `products` | 与 `path` 成对 | 非空的产品 id 列表。只有会话产品 id 在列表里才打开 |

阶段名：`req-review`、`req`、`arch`、`code`、`test`、`ops`、`verify-plan`、`s7`、`s8`。

一条字符串对所有产品生效。`{path, products}` 只对列出的产品生效。没写的阶段等于没有页面。`null` 或 `[]` 是空列表。

挂进来的每一页开头两节：这份页约束什么；一个用法例子。没有这两节不要挂。

```yaml
schema_version: 1
stages:
  code:
    - pack/coding-notes.md
    - path: pack/kafka-only.md
      products: [kafka]
  test: []
```

`pack/coding-notes.md` 人人打开。`pack/kafka-only.md` 只在产品 id 是 `kafka` 时打开。

## `workflow-defaults.yaml`

配方用 `from: product` 或命令类 kind 来读的值。缺文件或缺键，预检 BLOCKED，不猜命令。

| 键 | 解释 |
|---|---|
| `coding_root` | 产品目录的共同父路径。和 `products.<id>.dir` 拼出某个产品仓 |
| `commands.start` | 启动本地服务的命令。`{target}` 换成服务名，缺省 `all` |
| `commands.stop` | 停止本地服务的命令。`{target}` 同上 |
| `commands.status` | `shell.confirmed` 且 `command: status` 时执行的命令 |
| `commands.approval_off` | 关掉审批的命令。只跑这条命令，不改产线路由或配置里的开关 |
| `commands.lifecycle` | UI 剧本生命周期命令 |
| `commands.lint_fix` | 前端 lint 并修复的命令。没有这个键就问人，不猜 `npm` |
| `products.<id>.dir` | 该产品仓相对 `coding_root` 的目录 |
| `products.<id>.server` | 该产品的服务名，点了这个产品时用作 `{target}` |

配方里的 `product_key` 若指向上表没有的键，先在上表加一行再写进配方。

```yaml
coding_root: ../..
commands:
  start: "make up TARGET={target}"
  stop: "make down TARGET={target}"
  status: "make status TARGET={target}"
  approval_off: "make approval-off"
  lifecycle: "make ui-lifecycle"
  lint_fix: "npm run lint:fix"
products:
  kafka:
    dir: kafka-web
    server: kafka-web
```

`{target}` 由配方替换。`kafka` 换成实际产品 id，`dir` 换成该仓目录名。
