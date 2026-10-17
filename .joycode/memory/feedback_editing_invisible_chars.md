---
name: 隐形字符文件的编辑与验证方式
description: 本仓库编辑含转义/隐形字符的文件（如 cases.yaml）时必须用终端+Python heredoc，且码点分析只能靠 Python，不能信终端渲染
type: feedback
---

编辑 test/signoff/cases.yaml 等含隐形字符（U+200B/FEFF/NBSP 等）或需要 `\uXXXX` 转义的文件时，用终端 + Python heredoc 读写，不用 write_file/replace_file/read_file。

**Why:** write_file 不解释反斜杠转义（会把 `\uFEFF` 写成字面 6 字符）；replace_file 在搜索串含多字节/隐形字符时报过假 no-changes；read_file 有缓存过期史。终端 XTerm 渲染会损坏多字节字符（与 cat -v 的 M-x 表示混排），肉眼看到的字符不可信。

**How to apply:**
- 读码点：`python3 - <<'EOF'` + `q.encode('unicode_escape')`，注意 unicode_escape 输出小写（`\ufeff` 不是 `\uFEFF`，过滤时别用大写匹配）
- 改文件：heredoc 里按行号断言后重写（assert 行内容再替换，防错位）
- run_in_terminal 的 get_terminal_output 偶发 "Terminal session not found"，重跑同一命令即可，不是真失败