# L1 旁路复现

范围：本机 kafka-server `:8095` 使用已安装的 `joypaas-access-layer-starter:1.0.0-alpha.4-SNAPSHOT`。下游 OpenAPI 在 `:8081`。时间：2026-10-22 00:16–00:28 +08:00。

## 红

00:16:48 启动的进程，启动日志没有 `GatewayFilter registered`。

```
curl -sS -D - http://127.0.0.1:8095/v1/task?pageNumber=1&pageSize=10
HTTP/1.1 404
{"timestamp":"2026-10-21T16:23:38.971+00:00","status":404,"error":"Not Found","path":"/v1/task"}
```

同进程 `/v1/instances`、`/v1/overview` 同样是 Spring 默认 404。

```
curl -sS -D - http://127.0.0.1:8081/v1/task?pageNumber=1&pageSize=10
HTTP/1.1 200
```

响应体含任务列表。

`mvn -pl kafka-server dependency:tree` 警告：

```
The POM for com.jdt.joypaas:joypaas-access-layer-starter:jar:1.0.0-alpha.4-SNAPSHOT is invalid
'dependencies.dependency.version' for com.jd.jr.component:component-cache-r2m:jar is missing
```

运行 classpath 只有 starter 自身 jar，没有 `springdoc`。

## 绿

在 joypaas 仓执行 `mvn -pl joypaas-access-layer-starter -am install -DskipTests -Pex` 之后，同一条 `dependency:tree` 不再报 invalid，树中出现 `org.springdoc:springdoc-openapi-ui:1.7.0`。

用新 classpath 于 00:27:53 重启 `:8095`。日志：

```
GatewayAutoConfiguration - JoyPaas GatewayFilter registered (order=LOWEST_PRECEDENCE, hooks=1, approval=true)
```

未带登录态再打同一路径：

```
HTTP/1.1 401
x-jdcloud-request-id: gw5453d69405e74b55afeb2691956c74e8
```

日志：`Gateway auth unauthenticated (401) GET /v1/task: Not authenticated`。

浏览器里变更列表恢复后，人确认问题已解决。
