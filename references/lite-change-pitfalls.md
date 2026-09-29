# lite-change 踩坑（通用）

配方：`workflows/lite-change.yaml`。速查只留入口。产线专属的 mock/组件细节留在该仓 `.idev/pack/`，本页只放对所有产线成立的通用坑。

1. **不要**在进业务页前 mock 会决定请求前缀的全局配置（会弄坏后续请求路由）。
2. missing 配置：先真配置进页，再 mock 缺字段后 **reload**。
3. error 态：优先调组件自身的错误回调，别依赖"早 mock 挂子应用"来触发。
4. 文案对齐 i18n；改配置 body 时按该产线约定的结构写（扁平顶层 vs 嵌套，见该仓 `.idev/pack/`），别凭空造形状。
5. lite-change **禁止**自动 promote / 改 sealed；人没说提测就停在 gate-next。
6. 烟测：`bash ~/.cursor/skills/idev/scripts/lite-change-smoke.sh`
