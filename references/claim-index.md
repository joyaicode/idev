# 主张索引

索引是派生的。一句主张能不能留下，只看来源文件里有没有这句。`claims.yaml` 只写在当前票目录。

## 记录

| 字段 | 含义 |
|------|------|
| `id` | 摄取时按顺序编的 `c1`、`c2` |
| `subject` | 拆解条目用 `baseline_item_id`。显式行默认用来源路径；行尾可写 `\| 主题: <id>` |
| `text` | 主张原句 |
| `source` | 相对仓库根的来源路径，非空 |

## 从哪来

- `req.yaml` 每条 slice 的 `must`。来源是该票 `baseline.yaml`。`must` 为「无」的不收录。
- `design.md`、`req.yaml`、已存在的 `verify/plan.yaml` 里，单独成行、行首（可带 `- `）的 `主张: <句子> | 来源: <路径>`。正文里提到这行格式的，不算一条主张。
- 聊天和这三份之外的文件不读。

句子经空白归一后必须出现在来源文件里。否则摄取失败，不写这条记录。

## 命令

```bash
python3 scripts/claims.py ingest --feature <f>
python3 scripts/claims.py query --feature <f> --subject <id>
python3 scripts/claims.py calibrate --feature <f>
python3 scripts/claims.py guard --feature <f> --path <file>
```

校准退出码 0 表示每句都在来源里，且同一 `subject` 下没有两条互相装不下的文本。装不下是指谁的归一文本都不是另一条的子串。冲突时退出码非 0，并打印所涉来源路径。

`guard` 只在该文件被某条记录的 `source` 点名时才跑校准。没被点名的文件退出码 0。

写方案、拆解或用例之前跑 `calibrate`。改被点名的代码之前跑 `guard --path`。退出码非 0 就不写那一份、不改那个文件。

不调用 `lessons.py` 或 `realign.py`，不把校准加进 `check-feature`。
