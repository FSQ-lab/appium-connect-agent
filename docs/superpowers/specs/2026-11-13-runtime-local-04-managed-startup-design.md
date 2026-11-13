# RT-LOCAL-04 受管 Appium 启动与生命周期设计

## 状态、授权与依据

- 日期：2026-11-13；TaskID：`RT-LOCAL-04-DESIGN-SPEC-01`；关联 Issue：
  [#10](https://github.com/FSQ-lab/appium-connect-agent/issues/10)。
- 用户已于 2026-11-13 正式确认本文、根/Runtime/Automation SPEC delta 及库/系统工具选型；该确认授权 Issue #10 范围内实现，不自动授权真实服务/设备、Doctor、提交、推送或发布。
- 固定设计基线：`master@5f37b8b`；工作分支：
  `issue/10-rt-local-04-managed-start`。
- 产品决定依据：Issue #10
  [`issuecomment-6827679517`](https://github.com/FSQ-lab/appium-connect-agent/issues/10#issuecomment-6827679517)。
  该评论已经确认 Appium `3.x` 大版本策略、driver 兼容责任、Doctor/autofix
  边界和 managed usage 保护；本文不重新打开这些产品决定。
- 上位契约依据：[根 SPEC](../../../SPEC.md)、
  [Runtime SPEC](../../../modules/runtime/SPEC.md)、
  [RT-LOCAL-02 连接设计](2026-10-21-runtime-local-connection-design.md)和
  [RT-LOCAL-03 安装设计](2026-10-23-runtime-local-installation-design.md)。
- 当前源码证据：`RuntimeConnection` 只有 `external` ownership；Automation
  `create_session()` 在建立请求前保存连接，创建 unknown 通过公开错误保留 Session，
  `Session.quit()` 只在确认删除且本地清理完成后释放自身 reservation；安装模块已有
  `Popen(start_new_session=True, shell=False)`、非阻塞双流排空、进程组 TERM/KILL 和
  cleanup-pending 模式。本文深化这些现有接缝，不建立第二套约定。

## 问题与目标

RT-LOCAL-03 能在固定账号根准备受管 Appium 和 driver，但没有服务生命周期。
RT-LOCAL-02 只能复用 external 服务，并明确不取得进程或 Session 所有权。调用方当前
无法通过一个受管范围安全地启动已准备的 Appium、证明本次进程 ownership、等待可靠
就绪、保护正在创建或关闭的 Session，并在零 usage 后有界清理。

本 feature 的用户可观察结果是：调用方以明确 numeric loopback 地址和端口进入一次
同步 managed scope，得到现有 `RuntimeConnection` 形状；进入成功时，本次真实持有的
Appium 进程仍存活、`/status` 为 `ready=true` 且可靠版本为 `3.x`；退出只在 usage 为零时
终止本次 owned 进程组。任何 ownership、就绪、usage 或清理事实不确定时均明确失败并
保留资源，不冒充 idle/ready。

## Minimum sufficient design

推荐一个新入口、扩展一个现有连接视图、增加一个跨模块 usage lease 和一个只处理本实例
未完成清理的恢复入口：

```python
Runtime.start_managed(
    *,
    host: Literal["127.0.0.1", "::1"],
    port: int,
    base_path: str = "",
    control: OperationControl | None = None,
) -> AbstractContextManager[RuntimeConnection]

Runtime.cleanup_managed(
    *, control: OperationControl | None = None
) -> None

RuntimeConnection.ownership: Literal["external", "managed"]
RuntimeConnection.acquire_usage() -> RuntimeUsage
RuntimeUsage.release() -> None
```

`start_managed()` 只构造一次性上下文，零 I/O；进入时才取得账号锁、核对受管根、写入
启动意图、创建进程并检查就绪。`cleanup_managed()` 只能重试同一 `Runtime` 实例仍持有
真实进程句柄的 `cleanup_pending`；无待清理资源时幂等返回。它不能停止 active 服务、
不能依据磁盘记录/PID/端口接管进程，也不是 RT-LOCAL-06 的 `stop()`。

复用 `RuntimeConnection`，而不是建立 managed 子类或第二种 Automation 连接类型：
Automation 已经只依赖 `RuntimeConnection.server_url`，ownership 是运行时属性而不是
替换 Liskov 行为。`create_session(connection, ...)` 的现有签名不变；唯一新增衔接是它
通过公开 `acquire_usage()` 保留 lease。这样 external 调用方零迁移，managed 生命周期
获得必要深度，且 Runtime 仍不依赖 Automation。

`RuntimeUsage` 是 Runtime 拥有的不透明一次性 lease。它不暴露 Session、设备、PID、
计数或停止能力。有效未释放 lease 的 `release()` 只在 Runtime 内原子递减计数并标记
released，O(1)、零进程/网络/文件 I/O，绝不发送信号、终止服务或抛清理异常；第二次
调用才以 `InvalidStateError/usage_released` 拒绝，避免静默掩盖计数错误。external
connection 的 lease 只验证取得时连接 active，之后不参与 external scope 退出或服务
管理；managed lease 参与下述计数。调用方不应自行伪造 Session 终态；产品内唯一使用者
是 Automation 生命周期。

### 地址与命令边界

- `host` 必须显式为 `127.0.0.1` 或 `::1`，不接受 `localhost`、其他 loopback 表示、
  wildcard、主机名或远程地址。`port` 必须是排除 bool 的 `1..65535` 整数，没有默认值、
  自动选择、扫描或冲突后换端口。
- `base_path=""` 表示根路径；非空值必须以 `/` 开头，使用 RT-LOCAL-02 已确认的 ASCII
  segment 规则，拒绝重复分隔、`.`/`..`、百分号、查询、fragment、反斜线和尾斜线。
  规范 URL 不带根路径尾斜线；状态地址始终为 `<base_path>/status`。
- 在 spawn 前用 Python `socket` 对目标 numeric loopback/port 做一次短暂独占 bind
  预检；`EADDRINUSE` 映射 `service_port_in_use`。该检查只改善已存在冲突分类，不声称
  消除关闭预检 socket 到 Appium bind 之间的 TOCTOU；确定性 owned-listener 证明来自
  下文固定 macOS `/usr/sbin/lsof -F` 对本次 owned PID 的内核 TCP LISTEN FD 核验。
- 只从固定 `~/.appium-connect-agent/` 内经验证的 Appium entrypoint、专用
  `APPIUM_HOME` 及调用方已解析的 Node 工具链构造固定参数数组；
  `shell=False`、`start_new_session=True`、`stdin=DEVNULL`、双流 `PIPE`。argv 只包含
  Appium 本体、显式 address/port/base-path，以及固定 `--log-level info`、
  `--log-no-colors`、`--log-format text` 等非交互/可确定输出参数；不接受任意额外 CLI
  参数、日志文件/webhook、配置路径、插件、driver、shell 或环境注入。
- 子进程环境沿 RT-LOCAL-03 的隔离环境：固定受管 bin、`APPIUM_HOME`、tmp/cache，
  明确传递已解析 Java/Android 路径和必要系统变量；不读取新的产品配置源，不修改
  shell、全局 PATH、npmrc 或默认 `~/.appium`。
- 普通 startup 不执行 Doctor、driver install/update、npm、ADB、Session 或设备命令。
  driver 加载或后续 Session 创建失败按真实 Appium/driver 错误边界暴露，不触发修复、
  降级、替代 driver、重试或 fallback。

### RT-LOCAL-03 兼容重基线

`Runtime.install(InstallRequest())` 与 `supported_combinations()` 保持其已验收目的：它们
描述并准备**初始指定清单**，当前仍是精确 Appium `3.7.0` + UiAutomator2 `8.7.0`。
安装调用继续按该精确请求判断 installed/reused/conflict，不改 03A/03B 的组件顺序、
组件版本或恢复安全意图；现有 828 项已验收测试无需因 lifecycle 放宽为浮动安装。

已确认契约对 RT-LOCAL-03 记录命名空间做一个必要、精确的兼容窄 delta：固定服务记录只能是
`~/.appium-connect-agent/records/service.json`，根目录 `_ALLOWED_ROOT` 的六个顶层项保持
不变。`records/` 只允许必需的 `installation.json` 与可选 `service.json`；任何其他项，
包括既有测试中的 `records/other.json`，继续严格报 `installation_recovery_required`。

`service.json` 最大 64 KiB、当前账号拥有、0600、普通非链接文件，schema=1，字段精确为
`schema/state/operation_id/host/port/base_path`；operation_id 为非空有界字符串，host、
port、base_path 必须满足本次公开参数规则。状态只取 `starting | active | stopping |
cleanup_pending | recovery_required | stopped`。不存在，或 schema 合法且 state=`stopped`
是唯一 idle 形状；`Runtime.install()` 可正常复查 reuse 或执行 03B 继续。任何非终态、
截断、额外/缺失字段、非法类型/值，都使 `Runtime.install()` 在写入/组件命令前以
`installation_recovery_required` 拒绝，`start_managed()` 在 intent/spawn 前以
`managed_recovery_required` 拒绝；两者都不覆盖现场。03 安装代码因此必须把可选且合法
terminal service 记录纳入白名单，而不是放宽未知记录。

managed lifecycle 是另一项资格：当前 RT-LOCAL-03 complete 记录证明该根源自已批准
初始清单；未来 #13 只能通过 Appium 公开 CLI 在同一锁和根内维护 Appium/driver，并原子
更新 Runtime 拥有的 managed-root 事实。启动不重新执行 `Runtime.install()` 的精确版本
判定；实际 owned 服务的可靠 status 版本必须为 SemVer `3.x`，minor/patch 可与初始
`3.7.0` 不同，Runtime 不检查 Appium minor/patch 与 driver 版本矩阵。受管根仍须有
Appium 公开 CLI 可识别的已安装 driver 事实，但 #10 不要求 driver 等于初始 `8.7.0`，
也不把“已安装”解释为设备可用。#13 若改变维护记录 schema，必须保留上述根身份、
service 互斥、原子状态和 lifecycle 消费语义并另经 SPEC gate。

因此重基线扩展的是“已完成安装之后能启动什么”，不是把 `install()` 改成浮动安装，
也不撤销已有精确组合的资格证据。

### 启动、就绪与防假阳性链

进入 managed scope 的固定顺序：

1. 纯值校验后建立单一 monotonic 启动 deadline；`control=None` 使用 60 秒。取得现有
   macOS 登录账号非阻塞 `runtime.lock`，并检查同实例无 diagnose/install/external/
   managed/cleanup 操作。
2. 核对固定根身份、`installation.json` 与可选 `service.json`、受管 entrypoint、专用
   driver home 和 Node 路径；任何冲突/未知在 spawn 前失败。原子写入固定
   `records/service.json`，state=`starting`，不保存命令输出、环境、凭据或可供跨进程
   kill 的 ownership 声明。
3. 执行端口预检后立即 `Popen`。保存真实 process object 和 `pgid=process.pid`；只有
   该内存句柄授权本实例发送信号。启动 owned drain/supervisor 线程，用 selector 持续
   排空 stdout/stderr，每流最多保留 64 KiB，超限后继续丢弃式排空并记录 truncated。
4. Runtime 内部 ownership probe 只执行固定绝对路径 `/usr/sbin/lsof`，启动前须确认它是
   root 拥有、group/other 不可写的普通可执行文件；缺失或不可信时在 Appium spawn 前以
   `service_ownership_unverified` 失败。IPv4 固定 argv 为
   `lsof -nP -a -p <owned_pid> -iTCP@127.0.0.1:<port> -sTCP:LISTEN -F pfnT`；IPv6 只把
   selector 换为 `-i6TCP@[::1]:<port>`。固定 `shell=False`、`stdin=DEVNULL`、
   `LC_ALL=C`，stdout/stderr 各最多读取 16 KiB，每次调用受启动总 deadline 内最多 1 秒
   子预算约束；不执行 PATH 查找、shell、系统进程扫描或模糊端口查询。
5. 每次 probe 前后检查取消/deadline及 `proc.poll() is None`。`lsof` exit 1 且空 stdout
   表示当前尚无匹配 listener，可在同一预算内继续；exit 0 只有在 ASCII `-F` 记录同时
   包含精确 `p<owned_pid>`、一个 FD record、精确 `n127.0.0.1:<port>` 或
   `n[::1]:<port>`、`TST=LISTEN` 时才形成 ownership proof。超限、超时、执行异常、
   非 ASCII、畸形/矛盾字段、其他非零退出或非空错误结果均立即
   `service_ownership_unverified`；stderr 和原始输出不进入产品结果或持久记录。
6. **必须先取得 ownership proof，之后才允许首个 `/status`**。若 external 服务在
   bind-close 窗口抢先监听，owned PID 不可能取得目标 endpoint 的 TCP LISTEN FD；即使
   external `/status` ready 且 owned child 延迟退出也保持零 status、零 managed success。
   该证明查询内核 socket 表，不依赖 Appium 日志、extension 输出、minor/patch 或内部源码。
7. proof 后复用现有 HTTPX/AnyIO `get_status` 接缝及其代理、重定向、响应大小、清理和
   错误语义，只检查声明 URL 的 `/status`；必须 HTTP 200、对象形 `value`、
   `ready is True`，且 `value.build.version` 为既有严格规则识别的完整 ASCII SemVer
   `3.x`。managed 不允许 external 的 `unverified` 版本成功路径。
8. status 成功后再次执行同一 ownership probe，并在 probe 后再次要求
   `proc.poll() is None`；第二次 proof、可靠 SemVer `3.x` 和 child 存活全部成立，才原子
   写 state=`active` 并返回。等待片不超过 100 ms；只有 listener 尚未出现、连接尚未建立
   或 ready=false 可在同一预算内继续。401/403、重定向、协议错误、可靠非 3 版本、版本
   无法识别、child 退出、ownership probe 异常和取消立即失败；不自动重发
   Session/driver 命令。

连接报告保留 host/service/declared_compatibility/qualified_support/device 形状；service
和主版本成功可为 pass，qualified_support/device 仍为 unknown。成功只表示 owned
Appium 服务就绪，不表示 driver、Doctor、设备或 Session 可用。

F-03 在本机 macOS 只读实测了系统 `/usr/sbin/lsof` revision 4.91；`stat` 结果为 regular
file、owner root、uid 0、mode 0755。没有执行 Node/Appium。测试进程 PID 62244 同时创建
loopback TCP socket、由内核分配端口并 `listen(1)`。固定 `shell=False` argv 和原始 stdout
bytes 为：

```text
/usr/sbin/lsof -nP -a -p 62244 -iTCP@127.0.0.1:59761 -sTCP:LISTEN -F pfnT
b'p62244\nf9\nn127.0.0.1:59761\nTST=LISTEN\nTQR=0\nTQS=0\n'

/usr/sbin/lsof -nP -a -p 62244 -i6TCP@[::1]:59762 -sTCP:LISTEN -F pfnT
b'p62244\nf10\nn[::1]:59762\nTST=LISTEN\nTQR=0\nTQS=0\n'
```

两次 returncode 均为 0、stderr bytes 均为空；socket 在采样后立即关闭。`p` 是精确
owned PID，`f` 是该进程实际 FD，`n` 是 numeric endpoint，`TST=LISTEN` 是内核 TCP
状态。生产 parser 只依赖这些机器字段并忽略 `TQR/TQS` 等附加字段；因此 Appium 3.x
日志文案变化或 driver/plugin 输出同字节都不能伪造 proof。

### Usage lease 与 Automation 接缝

Automation 在完成纯值校验和 active URL 读取后、取得 device/systemPort reservation 或
发送任何 Session 创建请求前调用 `connection.acquire_usage()`：

- `connection_closing`/`connection_closed` 的 `InvalidStateError` 在 Automation 请求发送前
  映射为既有 `InvalidSessionStateError/session_invalid/not_sent`，不向 Automation 暴露
  Runtime 私有状态机。external lease 不改变现有 external 退出语义。
- managed lease 将 usage 从零增加到一。connection 已 close-requested、失效或 owned
  child 已退出时，任何创建请求前拒绝。
- 创建请求可证明未发送，或 Appium 明确证明 Session 未创建，且 client/transport 本地
  清理完成时，Automation 纯内存释放 lease。清理本身失败则 Session 保持可达/uncertain，
  lease 不释放。
- 创建成功时 lease 存入 Session；`ResourceStateError/session_create_unknown` 继续通过
  公开 `session` 字段让调用方可达同一 Session 和 lease。不能由异常映射器丢弃 lease。
- `Session.quit()` 只有在 Appium 删除响应已确认、client cleanup 完成、Session 标为
  closed 且 device/systemPort reservation 已释放后才调用纯内存 `usage.release()`。
  `not_sent`、`response_unknown`、cleanup error、KeyboardInterrupt 或其他不确定结果均
  保留 lease。release 不发送进程信号、不终止 Appium，也不抛 Runtime 清理异常；因此
  既有 quit 的返回/异常与 closed 契约不受 managed lifecycle 污染。
- managed usage 不按线程、设备或 sessionId 推断；每次 create attempt 至多一份 lease，
  由其最终 Session 或失败路径唯一拥有。Runtime 只计 lease，不读取 Automation 状态，
  因而依赖方向保持 `automation -> runtime + contracts`。

正常顺序保持既有根 SPEC：进入 Runtime connection，创建一个或多个 Session，逐个
`quit()` 使 usage 归零，再退出 managed scope；此时 `__exit__` 自己执行自然清理。

异常顺序下，任一 usage 存在时 `__exit__` **不得发 TERM/KILL**：它将 connection 标为
close-requested、将 `service.json` 原子推进为 `cleanup_pending`，保留真实 Popen/PGID
句柄和账号锁。无主体异常时抛 `ServiceLifecycleError/service_in_use`；有主体异常时保留
同一主体异常，只在 `runtime_managed_cleanup_error` 附加该错误。已有 Session 可继续完成
`quit()` 以纯内存归零 usage，但不允许新 `acquire_usage()`。

usage 归零本身不触发 I/O。调用方随后必须显式调用同一实例的
`runtime.cleanup_managed(control=...)`；该入口再次原子核对 usage，仍大于零时立即
`ServiceLifecycleError/service_in_use` 且零信号，等于零才执行下述有界清理。若 usage
永远 unknown，则进程和锁按设计保留，不以超时强杀可能仍承载未知设备命令的 Appium。
Integrations 当前 `McpApplication` 仍只使用 external connection，不受本契约影响；MCP
切换 managed connection 属于后续 Integrations Issue，不在 #10 预改。

### 正常退出、失败清理与崩溃边界

零 usage 的正常 `__exit__`、进入失败，以及 close-requested 后显式
`cleanup_managed()` 共用 Runtime 清理实现；每次调用使用一个额外 30 秒 cleanup deadline，
不重置给每个阶段：

1. 先原子核对 usage；大于零立即 `service_in_use` 且零信号。将
   `records/service.json` 推进为 `stopping` 后，只对本实例 `Popen` 建立且仍持有的 pgid
   发送一次 `SIGTERM`，持续排空双流并等待 process、进程组和 drain thread。
2. 温和阶段最多 2 秒；仍确认 alive 且 deadline 尚有余量时发送一次 `SIGKILL`。
3. 继续排空/关闭 stdout、stderr、selector，`wait()` 回收组长并 join drain thread。
   只有 `killpg(pgid, 0)` 为 gone、`proc.poll()` 非 None、selector 无注册、管道关闭且
   thread 已结束，才证明清理完成。
4. 原子写入 `service.json` terminal state=`stopped` 后使 connection 失效并释放账号锁。
   正常停止不删除 Appium/driver、`installation.json`、cache 或未知文件。

若组状态 unknown、信号/等待/排空/记录/线程 join 在预算内不能证明完成，状态为
`cleanup_pending`；原实例保留真实句柄和账号锁，只允许 `cleanup_managed()` 重试。主错误
保持同一对象，清理错误独立附 `runtime_managed_cleanup_error`；无主错误则
`ServiceLifecycleError/managed_cleanup_pending` 为主。协调锁释放错误仍使用独立
`runtime_cleanup_error`，不覆盖 HTTP、installation、Automation 或 managed 清理字段。

Python 父进程崩溃后真实句柄消失。下次看到 service state 为
`starting/active/stopping/cleanup_pending/recovery_required`、截断/非法 schema、未知根
事实或无法证明 idle 时返回 `managed_recovery_required`，不连接、启动、删除记录、发送
信号或释放为 idle。磁盘 PID/PGID、端口、进程名、目录、锁空闲、EOF 或 status 都不
重新授予 ownership。跨进程恢复/人工确认属于后续明确设计和授权；RT-LOCAL-06 也不能
仅凭旧 PID 文件杀进程。

owned child 在 active scope 中意外退出时立即使新 usage 获取失败；现有 connection 报
`connection_closed`，不自动重启。若进程组、管道和记录可确认终态，仍需 usage 归零后
由 scope exit 或显式 cleanup 完成 terminal 清理；未知 usage 不被运行时死亡伪造成已
关闭 Session。

### 状态与错误

内部状态最少为：

```text
idle -> preparing -> active -> terminating -> closed
                    |             |
                    |             +-> cleanup_pending
                    +-> close_requested/service_in_use -> cleanup_pending
                                      | usage=0 + cleanup_managed()
                                      +----------------------------> terminating
                    +-> recovery_required
```

`cleanup_pending` 表示当前实例仍持有句柄，正在等待 usage 归零后的显式 cleanup，或已尝试
清理但未完成；`recovery_required` 表示 ownership 或终态证据不足，不提供自动接管。公开
稳定错误最少包括：

| 情况 | 类型 / code |
| --- | --- |
| 受管根未完成、冲突或状态未知 | `ServiceLifecycleError / managed_installation_not_ready`、`managed_root_conflict`、`managed_recovery_required` |
| 明确端口已占用 | `ServiceLifecycleError / service_port_in_use` |
| ownership probe 缺失、不可信、超时或结果异常 | `ServiceLifecycleError / service_ownership_unverified` |
| child 在 ready 前退出 | `ServiceLifecycleError / managed_service_exited` |
| status 不可用/协议错误/not ready 超时 | 复用既有 `ServiceConnectionError` 或 `OperationTimeoutError` code |
| status 版本非可靠 SemVer 3.x | `UnsupportedVersionError / unsupported_server_version`；无法识别也失败，不返回 unverified |
| close-requested 时新 usage | `InvalidStateError / connection_closing` |
| scope 退出仍有 usage | `ServiceLifecycleError / service_in_use` |
| 当前实例清理未完成 | `ServiceLifecycleError / managed_cleanup_pending` |
| lease 重复释放 | `InvalidStateError / usage_released` |

非法 host/port/base_path/control 是零 I/O `ValueError`。已定义产品失败附有界
`partial_report`；未知程序缺陷保持原对象并执行保守清理，不宽泛映射成 ready/idle。

### Doctor 与相邻 Issue 边界

Doctor **不属于普通 managed startup，也不在 #10 新增入口**。它属于 #13
RT-LOCAL-05 的显式环境准备/维护流程，目标 driver 名只能是
`uiautomator2 | xcuitest | mac2`。#13 必须：

- 在取得同一账号锁、确认 managed service idle 后，使用实际受管 Appium entrypoint 和
  `APPIUM_HOME` 执行 `appium driver doctor <driver>`；
- 在执行前取得修改环境的明确授权，因为 Appium 3.7.0 对 `hasAutofix()==true` 的失败项
  即使 `--json` 也会执行 `fix()`；
- 将必需项失败视为准备失败，可选项只沿 Appium 自身语义，不复制 Android SDK、Xcode、
  签名或 Accessibility 规则；管理预算、进程/输出、有界脱敏和错误来源；
- 与 driver install/update 一样原子更新 managed-root 事实，不能在 #10 启动时静默执行。

#10 交付 scope-managed start、ready、usage 和自然退出；#13 交付 Appium CLI driver
维护及 Doctor；#4/RT-LOCAL-06 才能设计 active 服务的显式 `stop/restart`。任何一方都
不能通过 private 记录、fallback 或自动重试越过另一方边界。

## Deferred by design

- active 服务的显式 `stop()`、`restart()`、跨实例 attach、后台 daemon 或开机启动；
- 自动选端口、共享未知服务、远程/TLS/认证、非 numeric loopback 或多账号协调；
- Doctor、driver 安装/升级/降级/修复、Appium minor/patch 选择和兼容矩阵；
- 崩溃后按 PID/PGID 接管或自动清除 recovery record；
- iOS/macOS 的启动验收、多个 managed 服务、插件和任意 Appium CLI 参数；
- 自动创建/关闭 Session、设备选择、ADB 或设备恢复；
- 持久原始日志、遥测、凭据/环境快照及日志上传。

这些是明确非目标，不预建 Adapter、factory、registry、配置字段或占位 API。

## 库复用评估

查询日期：2026-11-13。目标解释器为本地锁定 CPython 3.11.16；本次只读核对当前
发行环境，并执行 macOS `/usr/sbin/lsof` 4.91 的临时 loopback socket 查询；没有执行 Appium、Doctor、ADB 或设备命令。

| 能力 | 推荐与证据 | 限制和适配 |
| --- | --- | --- |
| 进程创建/组清理 | CPython 3.11 `subprocess.Popen` 公开签名确认有 `shell=False`、`start_new_session=True`；`os.killpg` + `signal.SIGTERM/SIGKILL`；现有 `_installation._ProcessHandle` 已验证同一模式。官方：[subprocess](https://docs.python.org/3.11/library/subprocess.html)、[os.killpg](https://docs.python.org/3.11/library/os.html#os.killpg)。PSF 许可，无传递依赖。 | 标准库不保证逃逸进程组或父崩溃后 ownership；因此只管理本次句柄，未知转 recovery，不按 PID 接管。 |
| 持续双流排空 | `selectors.DefaultSelector` 在本机为 KqueueSelector；配合非阻塞 `os.read`、`threading.Thread` 和有界 buffer。现有安装实现提供 16 KiB 分块、每流 64 KiB 和 drain/close 模式。官方：[selectors](https://docs.python.org/3.11/library/selectors.html)。 | active 服务需要一个 owned drain thread；必须 join 后才能释放锁。`communicate()` 会累计输出，不用于长期服务。 |
| 端口预检/owned-listener 证明 | CPython `socket` numeric bind 只分类明确已有冲突；权威证明调用 macOS 固定系统工具 `/usr/sbin/lsof` 4.91，以 `-nP -a -p <owned_pid> -i... -sTCP:LISTEN -F pfnT` 查询内核 socket 表。IPv4/IPv6 临时 socket 实测分别返回精确 PID、FD、numeric endpoint 和 `TST=LISTEN`。固定绝对路径、`shell=False`，无包安装或传递依赖。 | bind-close 有 TOCTOU；只有 owned PID 的精确 LISTEN FD proof 后才允许 status，status 成功后还要再次 proof。工具缺失、不可信、超时、异常或畸形结果保守 `service_ownership_unverified`。不依赖 Appium 日志文案、psutil 或私有 Node API。 |
| status HTTP | 复用已批准 `httpx==0.28.1`、`anyio==4.15.1`、`httpcore==1.0.9` 和现有 `_http.get_status`。本地实际签名确认 HTTPX 0.28.1 AsyncClient、AnyIO 4.15.1 blocking portal；当前实现已固定无代理、无重定向、有界流和 join-before-return。MIT/BSD-3-Clause 许可沿既有批准用途。 | HTTP 只在 listener proof 后验证 ready/version，不单独证明进程 ownership；managed 收紧版本未知为失败并持续检查 child。 |
| SemVer | 复用已批准 `node-semver==0.9.1` 的 `valid(..., loose=False)` 薄适配及 Runtime 现有 128 字符 ASCII 规则。 | 只提取 Appium major=3；不解析 driver peer range、不维护 minor/patch 矩阵。 |
| 记录/同步 | CPython `json`、`pathlib`、`dataclasses`、原子 `os.replace` 和现有 account lock/安全文件规则。 | 记录是崩溃阻断证据，不是 ownership/kill 授权；未知或非法保守失败。 |

标准库、macOS 固定系统工具和已批准依赖完整覆盖本 feature；不新增或升级产品/开发
依赖，不扩大 AnyIO 到子进程管理，也不引入 psutil、AppiumService 或自研
HTTP/SemVer/Doctor。若 `/usr/sbin/lsof` 或实现资格无法满足本契约，必须停止并重新完成
平台/选型批准，不能用日志匹配、status 成功或 PID 文件降低 ownership 保证。

## 验收矩阵与验证入口

| ID | 必须证明的行为 |
| --- | --- |
| C01 | `Runtime`、managed context、地址值和 usage 构造零 I/O；非法 host/port/base_path 在锁、文件、socket 和 spawn 前拒绝。 |
| C02 | 只接受固定受管根；`records/` 精确允许 installation.json + 可选 service.json，其他文件仍 recovery；service absent/stopped 放行 install，非终态/非法同时阻断 install/start；03 精确组件版本语义不变。 |
| C03 | 固定 argv/env、`shell=False`、新进程组、持续双流洪泛/截断仍不阻塞；stdout/stderr 仅排空和有界证据，不参与 ownership proof、不写持久原始日志。 |
| C04 | 已占端口稳定 `service_port_in_use`；真实临时 IPv4/IPv6 listener 证明 `/usr/sbin/lsof -F` 只把精确 endpoint LISTEN FD 归属到指定 PID。构造“bind 预检后 external 抢先监听、owned child 挂起不退出且 external status ready”竞态，证明 owned PID 无 LISTEN FD 时零 status/零成功。 |
| C05 | 首次 ownership proof 后才允许 ready=false→true 轮询；严格 ready/JSON/大小/HTTP 清理、可靠 SemVer 3.x；status 成功后第二次 ownership proof 和 child 存活才 active。工具缺失/不可信/超时/异常、版本未知或非 3、child 早退、总预算/取消均失败并清理。 |
| C06 | 返回前后 owned child 存活且两次均持有目标 LISTEN FD；connection ownership=managed，报告不宣称 driver/device qualified；external connection 行为和 unverified 规则保持。 |
| C07 | Automation 在 create 前取得 usage并映射 closing/closed；not-created+clean 纯内存释放，active/unknown/cleanup error 保留；公开错误中的 retained Session 可最终 quit/release。 |
| C08 | `RuntimeUsage.release()` 对有效 lease 为 O(1) 零 I/O且不抛 Runtime cleanup；`Session.quit()` 不触发进程信号或 Runtime 异常，既有 closed/错误契约保持。 |
| C09 | usage>0 的 scope exit 零 TERM/KILL，写 cleanup_pending、保留主体异常/句柄/锁并拒绝新 usage；quit 归零后仍不自动清理，显式 cleanup_managed 才终止；usage>0 cleanup 调用零信号拒绝。 |
| C10 | usage=0 正常 exit、进入失败及显式 cleanup 执行 TERM→等待→必要 KILL、排空、wait、close、join；仅全部终态证据和 service.json stopped 完成后释放锁；清理错误字段彼此独立。 |
| C11 | 父进程 crash、截断/active/cleanup service 记录、旧 PID/端口/空闲锁不触发接管、kill 或新启动，稳定 `managed_recovery_required`。 |
| C12 | active child 意外退出使 connection 失效、不重启；unknown Session usage 不被伪造释放。 |
| C13 | 普通 startup 子进程 allowlist 只含 fixed Appium 和 ownership `/usr/sbin/lsof`；证明无 Doctor、npm、driver install/update、ADB 或 Session，依赖和模块导入方向不变。 |

默认永久测试使用临时账号根、fake Node/Appium 受控进程、临时 numeric loopback HTTP
端点和协议替身；覆盖真实 process group、pipe、线程、端口和跨进程锁，不用纯 mock
冒充生命周期。实现后的聚焦入口应为现有 Runtime/Automation 测试目录中新增的精确
managed/usage 用例，再执行 touched-scope Ruff/mypy/import-linter、Runtime+Automation
模块测试、构建和发行物检查。

Feature Done 另需用户明确授权，在固定真实受管组合上完成：启动 → owned listener proof →
可靠 ready → 创建一个安全 Session → 正常 quit → usage 归零 → scope 自然退出 → owned
进程组和管道终态确认 → `service.json=stopped` → 同一账号锁可复用。Doctor、driver 维护和
设备数据范围分别授权。没有真实服务/设备权限时只能报告
implementation-and-non-device-pass、device-validation-blocked、Feature non-Done；受控
协议替身不能替代该链。

实现阶段的聚焦测试必须把账号 home、`runtime.lock`、受管根、端口和 fake Appium 全部隔离
到 `tmp_path`；不得取得真实用户目录锁或干扰并行真机验收。

## 已确认 SPEC delta

根 SPEC 已增加 managed lifecycle 项目级边界，并明确初始精确安装清单与后续 `3.x`
lifecycle 资格分离。Runtime SPEC 已增加完整 Interface、usage、启动、清理、错误、
`service.json` 与 03 互操作、owned-listener proof 及 Doctor/#13/#4 边界。Automation SPEC
已增加 create/quit 的 RuntimeUsage 获取、保留、纯内存释放及错误映射；Contracts、
Configuration、Integrations 本轮 no-delta。MCP 从 external 切换 managed 不属于 #10。

设计不存在待用户继续拍板的二选一。真实服务/设备、Doctor 副作用、commit/push 等仍按
各自权限门槛另行授权；SPEC 确认和实现/非设备测试通过均不能替代 Feature Done 的真实链、
发行物与独立实现审查。
