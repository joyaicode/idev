"""R2 纯结构重构探针的 v1 模块(故意保留三段复制粘贴)。

行为契约(重构必须保持):
  parse_confirm(text) -> "CONFIRM" | "REJECT"
  - 先去掉首尾空白;
  - 以前缀 全签/确认/同意 开头、且紧随前缀的下一个字符是结尾或允许分隔符,判 CONFIRM;
  - 其余一律 REJECT。
允许分隔符集:。！，：:；;、 空格 制表符
公开 API 与返回值不得改变。
"""


def parse_confirm(text):
    t = text.strip()
    if t.startswith("全签"):
        rest = t[2:]
        if rest == "" or rest[0] in "。！，：:；;、 \t":
            return "CONFIRM"
    if t.startswith("确认"):
        rest = t[2:]
        if rest == "" or rest[0] in "。！，：:；;、 \t":
            return "CONFIRM"
    if t.startswith("同意"):
        rest = t[2:]
        if rest == "" or rest[0] in "。！，：:；;、 \t":
            return "CONFIRM"
    return "REJECT"