# 标注循环：方案文档作为人机共享可变状态

需求和设计阶段最贵的一次来回，是人看完方案、心里有十处要改，然后在聊天里把它们复述一遍。
复述会漏，会走样，而且下一轮没有任何东西能对照着查。

所以把文档本身当成共享可变状态：人在原地写标注，Agent 处理完在原地标掉，台账留下原文与处置。

## 怎么用

人在方案文档里直接写注释：

```yaml
# arch.yaml
approach: 加一层缓存
# @me: 队列消费者已经处理了重试，这里的重试逻辑是多余的，删掉它
```

```markdown
<!-- design.md -->
<!-- @me: 这是错的，visibility 字段要放在 list 上，不是 item 上，重构 schema 那一节 -->
```

两种都是各自语言里的注释，不影响解析，也不进入任何正文。

Agent 这一轮：

```bash
python3 ~/.cursor/skills/idev/scripts/annotate.py scan   --feature <f>
# 逐条处理，更新文档
python3 ~/.cursor/skills/idev/scripts/annotate.py settle --feature <f> \
    --at .idev/task/<f>/arch.yaml:3 --how "删掉重试那一节，改为交给队列消费者"
# 把文里的 `@me:` 改成 `@done:`，原文一个字都不动
python3 ~/.cursor/skills/idev/scripts/annotate.py check  --feature <f>
```

## 三条判据

`check-feature.py` 在 `req-review` / `req` / `arch` 三个 stage 调它，命中走 `FAIL`。

| 判据 | 命中说明 |
|---|---|
| 文里还有 `@me:` | 这一条还没处置 |
| 文里有 `@done:` 而台账里没有 | 处置没有留痕，等于口头说改了 |
| 台账里有、文里两种标记都找不到 | **标注被抹掉了** |

第三条是这个工具存在的主要理由。前两条只是漏做；第三条是人的意见被一次重写悄悄吃掉 ——
那比没有这套机制更坏，因为人会以为自己提过了。

原文是身份：台账存的是 `sha256(原文)`（只归一化空白）。改掉措辞就是另一条标注，台账会同时
报「被抹掉」和「无留痕」。要改措辞，让提标注的人改。

## 为什么是 FAIL 而不是 SIGNAL

SKILL.md 硬规则 3 本来就写着「矛盾、冲突或不清楚没对齐之前禁止写 sealed / arch.accepted」。
人写下的标注就是显式的那一个「不清楚」。这里不新增判准，只是让它判得出来。

## 为什么不等人点头

Agent 处置完（`settle` + 改成 `@done:`）这一关就能过。人不满意，下一轮再标一次。

答问不是签字，处置也不是。这里留的是可审计的痕迹，不是批准 —— 和
[chat-confirm-signoff.md](chat-confirm-signoff.md)「检查过了就写这一关，不问确认」是同一条线。

## 扫哪些文档

票目录的 `baseline.yaml` `req.yaml` `arch.yaml` `design.md`，以及 `doc_home` 给出的
`prd` / `spec` / `test-case` 三份工程文档。

## 来源

机制取自 `coding.jd.com/dts-ai-agent` `docs/rules/AI编程规约.md` §1.4，那里把它称作整条
AI 协作工作流里「最具价值的环节」，并给出「我在文档中添加了一些注释，请处理所有注释并更新
文档。**先不要实现**」这个守卫。idev 这一版把守卫换成了本来就有的那条：标注没对齐之前不写
`sealed` / `accepted`。
