# 整仓提交并推送（执行说明）

配方：`workflows/repo-commit-push.yaml`。场景 **S8**。

## 触发

`代码提交` / `整仓提交` / `提交并推送` / `repo-commit-push` + **工程根目录**（或已约定的 product 映射到 `*-project`）。

## 参数

| 名 | 必填 | 说明 |
|----|------|------|
| `project_root` | 是 | 整仓根（含 `.git`），由人给出 |
| `commit_message` | 是 | 人给；无则 `human.gate` 停问 |
| `skip_tests` | 否 | 默认 `true`：Java `-DskipTests`；`false` 跑单元测试 |
| `remote` | 否 | 默认 `origin` |
| `branch` | 否 | 默认当前分支 |

## 步骤顺序（硬）

```
replace_check → lint_fix → java.build → sensitive_shield → human.gate → commit_push → sensitive_restore
```

任一步 FAIL → 停。若已 `sensitive_shield` 尚未 restore：立刻 `sensitive_restore` 再报错（finally 语义）。

## 1. `git.replace_check`（Go 本地 replace）

在 `project_root` 下找所有 `go.mod`：

- **拒过（FAIL）**：存在**未注释**行，且 `replace … =>` 右侧为
  - 相对路径 `./` `../`
  - 绝对路径 `/` 或 `C:\` 等
  - 指向本机目录的路径（含 `$HOME`、`/Users/`）
- **允许**：整行注释 `// replace … => ../…`；或 replace 到模块版本号 / 伪版本（非本地路径）
- 版本钉扎类 `replace k8s.io/api => k8s.io/api v0.18.6` **放行**

输出命中文件:行到 evidence；有命中不准继续。

## 2. `frontend.lint_fix`

执行扩展根 `.idev/workflow-defaults.yaml` 的 `commands.lint_fix`。工作目录用 `coding_root` 与 `products.<product>.dir`。没有这个键就问人，不猜 `npm` 命令。

非 0 退出 = FAIL。人确认这条产线没有前端检查时，本步 `SKIPPED` 并写明。

## 3. `java.build`

若存在 `pom.xml`（优先仓根，否则常见 `*-web/pom.xml`）：

```bash
# skip_tests=true（默认）
mvn -f <pom> clean package -Pex -DskipTests

# skip_tests=false
mvn -f <pom> clean package -Pex
```

- 多模块：在约定聚合 pom 上跑；产品仓常见 `*-web/pom.xml`。
- 无 Java → `SKIPPED`。
- 用户说「跳过测试代码和单元测试」→ `skip_tests=true`（可再加 `-Dmaven.test.skip=true` 跳过测试编译，仅当人明确要求）。

## 4. `git.sensitive_shield` / `git.sensitive_restore`

**屏蔽（提交前）**

1. 备份目录：`project_root/.idev-sensitive-backup/<timestamp>/`（须在 `.gitignore`；若不在则只放系统临时目录并记 path）
2. 扫描并处理**已跟踪或将要提交**的文件（不碰 `node_modules` / `target` / `.git`）：
   - 名匹配：`application*.yml` / `application*.yaml` / `*.env` / `*secret*` / `*credential*`
   - 或内容键名（大小写不敏感）：`password`、`secret`、`access_key`、`accessKey`、`jwt`、`token`、`private_key`、`client.secret`
3. 对命中值：写入备份原件 → 工作区替换为占位符 `__IDEV_REDACTED__`（保持 YAML 结构）
4. **禁止**把真实 secret 写进 trace / report / 对话

**还原（push 成功或中途失败 finally）**

从备份拷回工作区文件；删备份目录（或保留到人说清）。还原后 `git status` 应再次看到本地敏感差异（通常勿再 add）。

占位符若被 commit 进远程：这是预期的「屏蔽提交」；本地还原后工作区与 HEAD 在敏感行上分叉，属正常。

## 5. `human.gate`

确认：`commit_message`、将推送的 `remote/branch`、`git status` 摘要（文件数，不含 secret 值）。无确认用语不 commit。

## 6. `git.commit_push`

```bash
cd "$project_root"
git add -A
# 确保 .idev-sensitive-backup 未被 add（检查 .gitignore / reset）
git commit -m "$commit_message"
git push "$remote" "$branch"
```

- 整仓：在 `project_root` 一次提交，不拆子模块另策（子模块有独立 `.git` 则对每个 git 根各跑一遍本配方，或人只点一个根）。
- 无变更 → `SKIPPED` 不 push。
- push 失败 → restore 后 `BLOCKED`。

## 不做

- 不 `force push`、不改 git config、不跳过 hooks（除非人明示）
- 不把 `review-commit` Ruby 面板当本配方真源
- 不自动 `promote` / 不改 sealed baseline

## 无变动不提交

`with.only_if_changed: true`：无已跟踪变更则 SKIPPED。
有变更时 message 必须写修复/调整概要。
