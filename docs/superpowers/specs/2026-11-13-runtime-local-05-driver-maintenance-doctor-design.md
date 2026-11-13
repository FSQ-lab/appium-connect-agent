# RT-LOCAL-05 受管官方 Driver 维护与 Doctor 详细设计

## 状态、授权与依据

- 日期：2026-11-13；设计 TaskID：`RT-LOCAL-05-DESIGN-SPEC-GATE-01`；实现 TaskID：`RT-LOCAL-05-IMPLEMENTATION-01`；关联 Issue：[#13](https://github.com/FSQ-lab/appium-connect-agent/issues/13)，父目标 #14。
- 状态：正式详细设计与已确认 SPEC delta。用户已确认该合同与 implementation-only 授权；本实现仍不授权真实 npm/Appium/Doctor/服务/设备命令、真实受管根写入、commit、push、merge 或 release。
- 固定实现基线：`master@564384a`；工作分支：`issue/13-rt-local-05-driver-doctor`。已确认 module/root SPEC delta 均已合入当前 worktree；文末保留精确根 delta 供审查。
- 上位依据：[根 SPEC](../../../SPEC.md)、[Runtime SPEC](../../../modules/runtime/SPEC.md)、
  [RT-LOCAL-03 安装设计](2026-10-23-runtime-local-installation-design.md)、
  [RT-LOCAL-04 managed lifecycle 设计](2026-11-13-runtime-local-04-managed-startup-design.md)、
  Issue #10 已确认的 Appium `3.x`/`service.json` 合同，以及 Issue #13
  `issuecomment-6841920143` 预备设计。
- 设计证据阶段只做静态读取；本地实现验证仅可使用临时账号根与 fake Node/Appium。没有运行真实 npm、Node、Appium、Driver Doctor、服务、ADB 或设备命令。

## 问题、重基线与交付粒度

Issue #13 旧正文只描述“固定组件”和补齐 UiAutomator2。Issue #10 后续已确认的产品合同是：
managed lifecycle 只按可靠 Appium SemVer `3.x` 判定；具体官方 driver 版本及其与 Appium
minor/patch 的兼容选择委托 Appium/driver 生态；Runtime 不维护版本矩阵、不搜索旧版、
不更新 Appium、不重试或 fallback；Doctor 是显式且可能修改环境的准备操作，绝不在
`diagnose()` 或 `start_managed()` 中静默执行。

因此本 Issue 重基线为同一依赖链上的两个独立可验收行为：

- **RT-LOCAL-05A：官方 driver ensure**。已安装且身份可靠时复用；明确缺失时，使用受管
  Appium 公开 CLI 无版本安装一次，并以第二次公开 list 复查。
- **RT-LOCAL-05B：显式官方 Driver Doctor**。仅对已安装且身份可靠的目标运行一次公开
  Doctor；接受 Appium 自身 autofix 语义，返回保守粗粒度结果。

05B 依赖 05A 的公共状态、进程和记录实现，但不会自动调用 05A。两个行为按 05A → 05B
实施、验证和审查；任何一个单独通过都不能关闭 #13。该纵向拆分按可观察行为，而不是按
模型、runner、测试或文件层拆分。

用户可观察结果：调用方只需学习两个同步入口和三个固定 short name；Runtime 隐藏固定根、
Appium CLI、进程组、输出、记录和恢复复杂度。删除该 Module 深度后，这些安全规则会散落到
每个调用方，因此 Interface 有实际 leverage 和 locality。

## Minimum sufficient design

### 公共 Interface

```python
OfficialDriver = Literal["uiautomator2", "xcuitest", "mac2"]

Runtime.ensure_managed_driver(
    driver: OfficialDriver,
    *,
    control: OperationControl | None = None,
) -> DriverMaintenanceResult

Runtime.run_driver_doctor(
    driver: OfficialDriver,
    *,
    control: OperationControl | None = None,
) -> DriverDoctorResult
```

Runtime.cleanup_installation(
    *,
    control: OperationControl | None = None,
) -> InstallationResult | DriverMaintenanceResult | DriverDoctorResult

所有新类型由 `appium_connect_agent.runtime` 拥有并导出。Runtime 构造保持零 I/O。两个入口
先做纯值校验：只接受三个精确、小写、实际 `str` 值；拒绝 bool、其他类型、大小写别名、
平台名、AutomationName、npm package 名、任意第三方名、`@version`、tag、URL、本地路径及
含参数文本。非法值在锁、受管根读取、记录写入和子进程前抛 `ValueError`。

唯一 short name 与 npm identity：

| `OfficialDriver` | 唯一官方 npm package | 当前平台目标 |
| --- | --- | --- |
| `uiautomator2` | `appium-uiautomator2-driver` | Android |
| `xcuitest` | `appium-xcuitest-driver` | iOS；不据此承诺 tvOS/watchOS |
| `mac2` | `appium-mac2-driver` | macOS |

不增加 `DriverManager`、Adapter registry、factory、任意 command runner、版本 resolver、
配置字段或 plugin seam。两个真实行为共用现有 Runtime seam、账号锁、安全根、
`_ProcessHandle`/`_Installer` 生命周期和原子记录；不建立第二套浅层 supervisor。

`Runtime.cleanup_installation()` 扩展为唯一 installation/maintenance 清理入口，公开返回
`InstallationResult | DriverMaintenanceResult | DriverDoctorResult`：installation pending 返回
`InstallationResult`，ensure pending 返回 `DriverMaintenanceResult`，Doctor pending 返回
`DriverDoctorResult`；无 pending 保留现有幂等 `InstallationResult` 复查语义。默认 30 秒。
同一 Runtime 实例任何时刻最多一个 installation/maintenance pending owner；现有私有
`_installation_cleanup` clean cutover 为带 operation-kind 的 installation/ensure/Doctor owner
联合，`_installing` 忙态覆盖整个 installation/maintenance writer family。入口只处理该 owner
仍持有且可证明归属的真实句柄，不能启动安装/Doctor、停止 active service、根据磁盘
PID/PGID 接管崩溃遗留或清理其他实例资源；不新增 `cleanup_driver()`。

### 结果与错误

```python
@dataclass(frozen=True)
class DriverComponent:
    name: OfficialDriver
    observed_version: str | None
    status: Literal["missing", "verified", "damaged", "unknown"]
    reason_code: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriverMaintenanceResult:
    operation_id: str
    observed_at: datetime
    driver: OfficialDriver
    appium_version: str
    before: DriverComponent
    after: DriverComponent
    outcome: Literal[
        "installed",
        "reused",
        "failed",
        "cancelled",
        "timed_out",
        "cleanup_pending",
        "recovery_required",
        "cleanup_completed",
    ]
    changed: bool
    warnings: tuple[str, ...]
    observer_errors: tuple[str, ...]


@dataclass(frozen=True)
class DriverDoctorResult:
    operation_id: str
    observed_at: datetime
    driver: OfficialDriver
    appium_version: str
    outcome: Literal[
        "accepted",
        "failed",
        "cancelled",
        "timed_out",
        "cleanup_pending",
        "recovery_required",
        "cleanup_completed",
    ]
    executed_check_count: int | None
    may_have_modified_environment: bool
    warnings: tuple[str, ...]
    observer_errors: tuple[str, ...]
```

结果是不可变纯值，不含根路径、package path、环境、命令、原始流或异常 repr。
`DriverComponent.verified` 只表示目标 list 项的 allowlist identity 和版本可靠；`reused` /
`installed` 不表示 Doctor、服务、设备、Session 或平台资格。`changed` 对 ensure 只在 install
子进程成功 spawn 后为 true；失败后也不能被复写为 false。

Doctor 的 `accepted` 只表示公开 CLI exit 0 且 stdout 是合法 check-count integer；不命名为
`passed` 或 `zero_findings`。`executed_check_count` 必须是 JSON 中排除 bool 的非负整数，
上限 1,000,000；失败为 None。Doctor 子进程一旦成功 spawn，
`may_have_modified_environment=True`，包括取消、超时、非零和输出非法，因为 `--json`
不能关闭 autofix，且 Runtime 无法证明 fix 是否运行或写了什么。spawn 前失败为 false。

新增：

- `DriverMaintenanceError(RuntimeOperationError)`，附
  `driver_result: DriverMaintenanceResult | None`；
- `DriverDoctorError(RuntimeOperationError)`，附
  `doctor_result: DriverDoctorResult | None`。

稳定 code 至少包含：`managed_installation_not_ready`、`driver_not_installed`、
`driver_state_unknown`、`driver_damaged`、`driver_install_failed`、
`driver_verification_failed`、`driver_doctor_failed`、`driver_doctor_output_invalid`、
`maintenance_recovery_required`、`maintenance_cleanup_pending`；继续复用
`environment_busy`、`operation_timeout`、`operation_cancelled`、
`coordination_unavailable`、`tool_not_found`、`tool_not_executable` 和
`unsupported_server_version`。非零 Doctor 统一为 `DriverDoctorError/driver_doctor_failed`，
不通过 error 文本猜 required/optional/import/check 分类。

未知 Python 缺陷保留原对象；主错误对象不被清理错误覆盖。进程/流清理问题继续独立附
`runtime_installation_cleanup_error`，协调锁清理仍附 `runtime_cleanup_error`。
KeyboardInterrupt 原样传播并附可用的相应 partial result。

maintenance cleanup 的正常返回与 pending operation 保持同形；取消、超时、再次
cleanup_pending、recovery_required 及 KeyboardInterrupt 分别更新该 operation 的
`installation_result`、`driver_result` 或 `doctor_result`。cleanup 自身未知缺陷也附同形最新
partial result；调用方由返回联合或异常附件可靠区分 owner，不从磁盘记录猜测。无 pending
路径不制造 maintenance 结果。

## 前置安全 gate 与记录互操作

两个入口在任何 maintenance 写入或 driver/Doctor CLI 前依次执行：

1. 完成 driver/control 纯值校验并建立一个 monotonic 总 deadline。
2. 拒绝同实例 diagnose/connect/install/start_managed/cleanup/maintenance 重入或并发；取得
   当前 macOS 登录账号既有非阻塞 `runtime.lock`，并持有到正常终态或可证明清理结束。
3. 校验固定 `~/.appium-connect-agent/` 为当前 UID、精确 0700、marker/允许项合法；受管目录、
   Appium package/metadata/entrypoint 均拒绝 group/other 可写及不可信链接/路径。
4. `installation.json` 必须是 schema 合法、`state="complete"`、初始组合 identity 合法；
   `failed`、`incomplete`、`cleanup_pending`、`recovery_required`、缺失或非法都零写入阻断。
5. 受管 Appium package identity、entrypoint 和路径必须可靠，观测版本须满足既有最多 128
   ASCII strict SemVer 且 `major == 3`。这项 managed 资格与 RT-LOCAL-03 初始精确
   `3.7.0 + 8.7.0` 清单分离；本 feature 不更新 Appium，也不把 3.x 主版本理解为 driver
   或平台 qualified。版本未知或非 3 在 maintenance 写入/目标 CLI 前失败。
6. `service.json` 只允许 absent 或完整合法的 `state="stopped"`；`starting`、`active`、
   `stopping`、`cleanup_pending`、`recovery_required` 或 schema/owner/mode/link 非法，均零写入、
   零 list/install/Doctor 阻断。端口无监听、旧 PID 不存在、锁可取得或 mtime 不能改变该结论。
7. `maintenance.json` 只允许 absent 或完整合法的 terminal `complete | failed`；
   `incomplete | cleanup_pending | recovery_required` 或非法 schema 零写入阻断
   `install()`、`start_managed()`、`ensure_managed_driver()`、`run_driver_doctor()`。
8. gate 全部通过后，才执行一次固定 `driver list --installed --json` 建立目标 before 事实。

### `records/` 窄兼容 delta

`records/` 精确允许：必需 `installation.json`、可选 `service.json`、可选
`maintenance.json`。任何其他项继续 recovery。新记录固定为：

```json
{
  "schema": 1,
  "state": "incomplete|complete|failed|cleanup_pending|recovery_required",
  "operation_id": "bounded-ascii-id",
  "operation": "driver_install|driver_doctor",
  "driver": "uiautomator2|xcuitest|mac2",
  "may_have_changed": true
}
```

文件最大 64 KiB、0600、当前 UID、普通非链接、link count 1；字段集合精确，schema 是排除
bool 的整数 1，operation_id 为 1..128 非空白可打印 ASCII，operation/driver 只取上述值，
`may_have_changed` 是保守风险 bool，不能单独用于状态晋级、恢复或资格判断。沿现有
`_atomic_json` 的安全临时文件、fsync/replace 和重新核验规则。

`incomplete` 在 install/Doctor spawn 前原子写入。两个 writer intent 都将
`may_have_changed=true`：它表示即将进入不可事务化外部 writer 的保守风险，不声称 Popen
已经成功或实际文件已改变；即使 spawn 失败也保持安全但不冒充实际修改事实。公开 ensure
result 的 `changed` 仍只在 install 子进程成功 spawn 后为 true；Doctor 公开结果仍以
`may_have_modified_environment` 区分 spawn 前后。`complete` 只表示该次公开 CLI 合同完成；
`failed` 只在进程组、流、最终事实和原子写入都可证明终态时使用。两者允许未来操作继续，
但不能替代 `installation.json=complete`、`service.json` idle、Appium 3.x identity 或目标
list 事实。

`cleanup_pending` 只表示同一 Runtime 实例仍持有真实 `_ProcessHandle` 且本轮收尾未完成；
保留账号锁，只允许 `cleanup_installation()`。`recovery_required` 表示 ownership、记录或最终
事实未知；磁盘 PID/PGID、进程名、目录、EOF、空闲锁都不授权接管、kill、删除或修复。

RT-LOCAL-03 `install()` 与 RT-LOCAL-04 `start_managed()` 必须消费该精确记录：maintenance
absent/complete/failed 只表示没有活动维护，继续各自原资格核对；其他状态或非法文件在各自
任何写入/组件命令/spawn 前分别以现有 installation/managed recovery 错误阻断。

## Appium 3.7.0 公开 CLI 忠实模型

### 固定证据身份

2026-11-13 静态核对受管发行文件：

- `appium/package.json`：Appium `3.7.0`，gitHead
  `b67de03966155ff052076c11c1c8f20cc2ba9134`，Apache-2.0；Node range
  `^20.19.0 || ^22.12.0 || >=24.0.0`，npm `>=10`。
- `build/lib/constants.js` 的 `KNOWN_DRIVERS` 把 `uiautomator2`、`xcuitest`、`mac2`
  分别映射到本文唯一三个 npm package；Runtime 收紧为这三个，不开放 registry 其他项。
- `appium-uiautomator2-driver/package.json`：`8.7.0`、peer Appium
  `^3.0.0-rc.2`，manifest 声明 required/optional Doctor scripts。该本机 driver 事实不推广
  为 XCUITest/Mac2 行为或未来版本保证。

### list

唯一命令：

```text
<verified-node> <managed-appium-entry> driver list --installed --json
```

Appium `ExtensionCliCommand.list()` 先从 installed extension manifest 构造 map；未传
`--updates` 时 `_checkForUpdates()` 立即返回，不做 update metadata 查询；JSON 模式还可能从
本地 installed package.json 补 repository URL。Runtime 允许 Appium 3.x 增加未知字段，但
只读取目标 map key 下的 `installed`、`pkgName`、`version`、`installType`、`appiumVersion`
和 `installPath`；不返回这些原始字段。Appium 3.7.0 安装时的 `receiptToManifest()` 会显式
删除 `driverName`，installed list 不会恢复该字段，因此不得要求 list item 含
`driverName`。short-name identity 由 JSON map key 精确等于请求值证明。

目标 key absent 是明确 missing。present 必须同时满足：map key 等于请求值、`pkgName` 等于
固定映射、`installed is True`、`version` 是有界严格 ASCII SemVer、`installType` 与
`appiumVersion` 若存在则类型/值不矛盾，且解析后的 `installPath` 位于已验证 driver home 并
指向对应官方 package identity。缺少必需字段、错误类型、identity/path 冲突、非法版本、
CLI 非零、UTF-8/JSON 非法或超限是 damaged/unknown；绝不能当 missing 后覆盖。若实施还需
核对 package 内 `appium.driverName`，只能对上述受管 `installPath/package.json` 做安全、
有界静态读取，不得声称该值来自 list。

### ensure install

唯一写命令：

```text
<verified-node> <managed-appium-entry> driver install <driver> --json
```

`<driver>` 直接来自 Literal；禁止 `@version`、tag、npm package、URL、本地路径、`--source`、
`--package`、`--updates`、update、unsafe、uninstall 或任意附加 argv。Appium 3.7.0 将 known
short name 映射到官方 npm package；不带版本时由 npm 解析默认结果；
`_checkInstallCompatibility()` 对解析包的 `peerDependencies.appium` 与当前 Appium 做 SemVer
检查，随后验证 package name/version/appium/driver 必填 metadata 并写 extension manifest。

该流程不保证寻找“仍兼容 Appium 3.x 的旧版”。若 registry 默认版本要求 Appium 4 或其他
不兼容版本，Runtime 原样 `driver_install_failed`：不追加版本、不查询旧版、不更新 Appium、
不调用 update、不重试或 fallback。install exit 0 也不单独成功；必须再次运行固定 list 并
重新通过完整 allowlist identity/version/path 校验，之后才写 complete 并返回 installed。

05A 固定顺序：

1. gate + before list；
2. verified → `reused/changed=false`，不写 maintenance intent、不运行 install；
3. missing → 写 incomplete → spawn 唯一 install；
4. exit 0 → 第二次 list；目标 verified → 写 complete → installed；
5. damaged/unknown、非零、取消、超时或复查失败停止，不换版、不补命令。

### Doctor/autofix

唯一命令：

```text
<verified-node> <managed-appium-entry> driver doctor <driver> --json
```

Appium 3.7.0 `_doctor()` 要求 driver 已安装，从目标 package manifest 的
`appium.doctor.checks` 加载位于 module root 内的脚本，动态 import，只保留同时提供
`diagnose/fix/hasAutofix/isOptional` 的对象，再顺序运行 `Doctor(checks).run()`。

`Doctor.run()` 的公开源码语义：先 diagnose；对无 autofix 的失败调用 `fix()` 获取人工
remediation 文本；required 且无 autofix 的失败返回内部 127；否则对所有 hasAutofix 的
失败（包括 optional）调用 `fix()` 并再次 diagnose；任一 autofix 后仍失败也返回 127。
仅无-autofix optional finding 可以最终返回内部 0。`--json` 只改变 wrapper 输出，不关闭
上述 fix 调用。

公开进程层：success exit 0，stdout 只是 JSON integer check count；内部 127 被包装为
`Treatment required`，与 manifest/import/check 等异常一样经 `errAndQuit()` 输出 JSON error
对象并 exit 1。公开 JSON 不含 per-check required/optional/fixed/message。因此：

- Doctor 前先以 list 确认目标 verified；missing 直接 `driver_not_installed`，不自动 ensure；
- spawn 前写 Doctor incomplete，且 `changed=true`；spawn 后
  `may_have_modified_environment=True`；
- exit 0 + 合法 integer → complete + `accepted`；0 checks 仍只按 Appium accepted；
- 任意非零统一 `DriverDoctorError/driver_doctor_failed`；非法/超限 success stdout 为
  `driver_doctor_output_invalid`；不解析 error object/human log 猜原因；
- 不自动 rerun、不回滚 fix、不追加 SDK/Xcode/signing/Accessibility/设备命令。

Doctor 动态执行当前已安装 driver 代码。官方 allowlist 不是 OS sandbox；autofix 可能写当前
账号可写环境、工具设置或平台状态。每次真实 Doctor 必须另获明确 driver、环境、可接受
修改、数据保留和恢复边界授权；Issue Ready 或实现授权均不自动授予。

## 命令、环境、预算与资源

- 所有命令均为固定 argv、`shell=False`、`stdin=DEVNULL`、双流 `PIPE`、
  `start_new_session=True`；cwd、受管 Appium entrypoint、`APPIUM_HOME`、tmp/cache/PATH 和
  Node/npm 配对复用 RT-LOCAL-03/04 已验证规则。
- 沿用户已有 registry/proxy/certificate/auth 网络配置，但不读取、记录、返回或修改其值；
  不修改 npmrc、shell、全局 PATH/prefix 或默认 `~/.appium`。Doctor 使用 managed startup
  可见的 Java/SDK/Xcode 环境，不自建平台规则。
- 两入口 `control=None` 均使用 600 秒默认总预算；显式 `OperationControl` 使用其有限正数
  timeout/Event。预算从入口开始，覆盖锁、gate、list/install/Doctor/final list、回调、记录
  和结果，不按阶段重置。
- 失败、取消、超时或 KeyboardInterrupt 后停止新业务命令，进入单一额外最多 30 秒 cleanup
  deadline：TERM、最多 2 秒温和等待、必要 KILL、wait、双流持续排空、pipe/selector close、
  最终事实读取和 terminal 记录共享该预算。
- 深化现有 `_installation._ProcessHandle`，不复制 supervisor。每流持续排空；非结构化内部
  诊断保留最多 64 KiB，超限后继续丢弃式排空并只保留 truncated 标记。需要解析的 list /
  install / Doctor stdout 使用独立完整结构化通道，最多 1 MiB；超过 1 MiB 即失败，不解析
  截断前缀。实现不得同时保留第二份完整 stdout：结构化 buffer 是该流唯一完整副本，公开
  evidence 仍只允许固定事实；stderr 最多内部保留 64 KiB。
- 只有 process group gone、`poll()` 非 None、selector 无注册、双管道关闭且句柄终态可证明
  才释放锁。清理不能证明完成时 maintenance=`cleanup_pending` 并由同实例
  `cleanup_installation()` 重试；父崩溃后句柄丢失则 recovery，不按旧 PID/PGID 接管。

## 安全、隐私与副作用边界

公开 result、DiagnosticReport evidence、ProgressEvent、记录与受控异常 message 的严格
allowlist 只有：固定 driver short name、已验证 Appium/driver SemVer、稳定 status/reason/
error code、合法 check count、changed/may-have-modified/truncated 布尔事实和固定 warning。
ProgressEvent 只使用固定 phase/check_id/message，如 `driver_preflight`、`driver_listing`、
`driver_installing`、`driver_verifying`、`driver_doctor_running`、`maintenance_cleanup`。

禁止返回或持久化：原始 stdout/stderr、Doctor diagnosis/fix/error message、argv、完整环境变量
名称/值集合、PATH/JAVA_HOME/ANDROID_HOME/Xcode/package/install 路径、用户名/home、npmrc、
registry/proxy/certificate/auth/token、package.json/manifest 全文、PID/PGID、端口、设备 ID、
UI/Session 数据、异常 repr/stack trace。上游文本即使看似无敏感信息也不能进入产品结果。

05A 的网络/npm/install 副作用只允许受管 driver home/cache/tmp 及 Appium CLI 自身受管
manifest；但 npm/安装脚本是外部代码，真实执行仍需网络、受管根和 npm 配置授权。05B
autofix 无法被 `--json` 禁用，也无法由 Runtime 证明写集；一旦 spawn 就保守标记可能修改
环境。Runtime 不宣称 sandbox、事务性、回滚、exactly-once 或“只改受管根”。

普通 `diagnose()` 保持静态只读；`start_managed()` 保持不运行 maintenance/Doctor；external
Appium、用户全局 npm/Appium 和默认 `~/.appium` 永不成为写入目标。active/unknown service
期间没有“先 stop 再维护”的隐式编排。

## 库复用评估与源码级证据

查询日期：2026-11-13。零新增或升级产品/开发依赖。

| 能力 | 采用方案与证据 | 限制与不选理由 |
| --- | --- | --- |
| 进程组、信号、双流、deadline | CPython 3.11 `subprocess.Popen`、`os.killpg`、`signal`、`selectors`、`time.monotonic`、`threading.Event`，深化现有 `_ProcessHandle`。官方：[subprocess](https://docs.python.org/3.11/library/subprocess.html)、[os.killpg](https://docs.python.org/3.11/library/os.html#os.killpg)、[selectors](https://docs.python.org/3.11/library/selectors.html)。项目 `requires-python >=3.11`。 | 标准库不保证逃逸进程树、强杀父进程后的 ownership 或不可中断 OS 调用；故只管理真实句柄，unknown 保守 recovery。不引入 psutil/daemon/supervisor 库。 |
| 状态文件与锁 | CPython 3.11 `json/pathlib/stat/os.replace/fsync` 与现有 account lock、`_atomic_json`、owner/mode/no-symlink 检查。 | 记录只做崩溃阻断，不授予 kill ownership；不引入数据库/registry。 |
| Appium/driver SemVer | 既有批准 `node-semver==0.9.1`，实际 `_semver.version()` 通过公开 `nodesemver.valid(..., loose=False)` 执行 128 ASCII strict policy。发行物和 `uv.lock` 均精确固定 0.9.1。 | 只验证观测版本和 Appium major；不解析/选择 driver peer matrix，不自研 npm SemVer。 |
| list/install/Doctor | 受管 Appium 3.7.0 公开 extension CLI。源码证据：package gitHead `b67de...`; `constants.js`; `cli/driver-command.js`; `cli/extension-command.js`; `doctor/doctor.js`; `cli/extension.js`; `cli/utils.js`。官方参考：[Extension CLI](https://appium.io/docs/en/3.2/reference/cli/extensions/)、[Managing Extensions/APPIUM_HOME](https://appium.io/docs/en/3.2/guides/managing-exts/)。 | 不导入私有 JS、不复制 Doctor framework；公开 Doctor JSON 只够粗粒度结果。若需要 per-check DTO、禁 autofix、sandbox 或兼容版 resolver，返回上游能力/依赖/SPEC gate。 |
| HTTPX/AnyIO/HTTPcore | 不使用，不扩大现有 HTTP 用途。 | 本 feature 没有 HTTP；已有依赖不构成第二套进程管理理由。 |
| npm Python SDK/CLI framework | 不选。 | Appium 已拥有 package 选择、peer check、manifest 写入和 Doctor；额外库增加分歧而不能消除动态副作用。 |

CPython 标准库足以复用现有受控生命周期；node-semver 足以验证观测事实；Appium CLI 是生态
规则的唯一权威 Adapter。若实现需要新依赖、私有 JS、human-log parser、特定版本安装、
更新 Appium、sandbox 或扩大 AnyIO 用途，立即停止并返回选型/SPEC gate。

## 验收与验证入口

### 05A 聚焦矩阵

1. 三个 Literal 和 package 映射；其他值、注入文本、version/source/package 参数零 I/O 拒绝。
2. installation 非 complete、Appium 非可靠 3.x、service 非 absent/stopped、maintenance 非
   absent/complete/failed 或任一非法 schema：零 maintenance 写入、零 list/install。
3. present verified → reused，无 intent、无 install、无 registry update 请求。
4. missing → intent → 无版本 install → final list verified → installed。
5. registry 默认 driver 与 Appium 3.x 不兼容：明确失败，无旧版搜索、Appium update/retry/fallback。
6. damaged/unknown/list 非零/非法/超限：零 install；install exit 0 但 final identity 错仍失败。
7. 600 秒共享预算、取消、KeyboardInterrupt、双流洪泛、1 MiB structured 上限、继承 pipe、
   进程组 TERM/KILL、同实例 cleanup；主错和 cleanup 错独立。
8. crash/incomplete/recovery/旧 PID 不接管、不 kill、不删除记录；terminal maintenance 不替代
   installation/service/Appium/driver 事实。
9. external/default Appium、全局 npm、`~/.appium`、服务、ADB、Session、设备均无 Runtime 写入/调用。

### 05B 聚焦矩阵

1. 未安装、damaged/unknown driver 零 Doctor且不自动 ensure。
2. 固定命令/environment；不调用私有 JS 或项目自研平台检查。
3. exit 0 + integer（含 0）→ accepted/check count；结果不声称 zero findings/platform ready。
4. 受控 Appium 3.7.0 语义替身覆盖 required/optional、autofix success/failure 与 optional
   no-autofix exit 0；产品只观察公开 exit/integer。
5. 所有非零统一 DriverDoctorError；非法 UTF-8/JSON/bool/negative/过大/超限成功 stdout 明确失败。
6. spawn 后 accepted/非零/取消/超时/KeyboardInterrupt 均 may-have-modified=true；无自动 rerun/rollback。
7. stderr/上游 error/fix 文本含路径、env、npmrc、token-like 内容时，result/report/progress/record/
   exception message 全部不泄漏。
8. Doctor 后 Runtime 不启动 service、不追加 ADB/Session/设备请求。

默认永久测试使用临时账号根、fake Node/Appium、真实临时进程组/pipe/锁/记录；不能触碰真实
`~/.appium-connect-agent`、真实 npm 网络、Doctor 或设备。公开 Interface、结果、错误和
`cleanup_installation()` 通过正式 wheel/sdist 隔离安装 consumer 验证。

### Implementation-only 验证证据

2026-11-13 在当前 worktree、CPython 3.11.16 上完成以下无真实环境副作用验证：

- `uv run pytest -q tests/runtime/test_maintenance.py`：72 passed；
- `uv run pytest -q tests/runtime`：658 passed；
- `uv run pytest -q tests/test_package_import.py`：3 passed；
- `uv run ruff format --check .`：146 files already formatted；
- `uv run ruff check .`、`uv run mypy src tests tools/diagnose.py`、`uv run lint-imports`：通过；
- `uv build` 生成 wheel/sdist，`.github/scripts/check_distributions.py` 对两种发行物隔离安装、
  metadata、`uv pip check`、包导入与 `py.typed` 验证通过；正式 wheel 的 maintenance 公共导出和
  两个 Runtime 方法签名 smoke 通过。
- 独立 `quality-engineer`：首轮 7 findings；第 2 轮剩余 1 minor；最终 repair-only 复审
  `PASS — 0 open findings`。

上述测试仅使用临时账号根、fake Node/Appium 和受控本地进程；没有执行真实 npm、Node、Appium、
Driver Doctor、服务、ADB 或设备命令，也不构成下述 Feature Done 真实环境证据。

实现后规模复查：产品代码 churn 为 1,257 行，触发约 1,200 行复查。保留本次完整交付：05A 与
05B 已分别由公开入口和聚焦行为测试验收，但 05B 复用 05A 的同一资格、记录、进程与 cleanup
状态机，且 #13 的已确认验收要求两者共同交付；再按模型/runner/测试文件拆分会留下不可用的技术层
半成品。该决定不把任一单项通过提升为 #13 Done。

Feature Done 还需分别授权并记录三个 driver 的真实无版本 install 解析版本与 peer 结果，以及
每个平台明确环境中的 Doctor/autofix 修改和恢复边界。Android 证据不替代 iOS/macOS；缺少
任一平台授权/环境时对应平台及 #13 保持 blocked/non-Done。实现与真实证据均需适用独立完整
安全/正确性审查 0 open findings。

## Deferred by design

- Appium minor/patch 安装、升级、降级或选择；
- driver `@version`、tag、update、unsafe、uninstall、rollback 或兼容版本 resolver；
- 第三方 driver、plugin、任意 package/source/path/CLI 参数；
- 自动 Doctor、startup 前 Doctor、scheduler/cache、重试、fallback；
- Doctor per-check required/optional/fixed/message DTO 或 human-log parser；
- sandbox、事务回滚、环境 diff、平台工具安装、自研 SDK/Xcode/signing/Accessibility 修复；
- active service stop/restart 编排；
- external Appium、用户 npm/global/default Appium 环境维护；
- 跨进程恢复、按磁盘 PID/PGID 接管、自动删除 recovery record；
- Session、ADB、设备/UI 操作或平台 qualified 推断；
- 持久原始日志、环境快照、遥测或上传。

这些是当前明确非目标，不预建 Interface、Adapter、配置、状态或占位实现。

## 已确认 SPEC delta

Runtime 模块 delta 已由用户确认并写入 `modules/runtime/SPEC.md`；根 `SPEC.md` delta 已在当前授权实现轨合入。Contracts、Configuration、Automation、Integrations、依赖/lock 均 no-delta。

已确认事项：

1. Issue #13 重基线为 05A ensure + 05B explicit Doctor，以及三个官方 short name；
2. 无版本 install、peer 不兼容即失败，不旧版搜索、不更新 Appium、不 retry/fallback；
3. Doctor 结果仅 coarse `accepted/failed + success check count`，且 spawn 后 `may_have_modified_environment=true`；
4. `maintenance.json` schema 与 install/start/maintenance 四入口 gate；
5. `cleanup_installation()` 复用同实例 maintenance pending 句柄；
6. 零新增依赖的 CPython 3.11 + node-semver 0.9.1 + 受管 Appium 公开 CLI 方案。

真实 npm 网络/受管根写入、每次 Doctor autofix、平台工具/权限、服务/设备、commit/push/
merge/release 仍是独立授权，不随 SPEC Gate 自动获得。

### 已合入根 `SPEC.md` delta 全文

以下保留已确认并合入根 SPEC 的精确 delta，供审查核对：

```markdown
第 7 行替换为：
本项目已确认 Python 工程基线，以及 Runtime 本地静态诊断、已有本地 Appium 连接、受管初始安装、scope-managed Appium 生命周期、受管官方 driver ensure 与显式 Driver Doctor 契约；实现与兼容性以实际验收证据为准。当前 Integrations 产品接入包含本地 stdio MCP 与面向 FSQ 的进程内 Python ToolCall 表面；这不自动承诺其他 Agent、CLI、HTTP、设备平台或具体 Host 兼容。

第 25 行替换为：
模块级 Python 包名与逻辑模块对应，内部文件不要求镜像文档目录。Runtime 当前公开契约为本地静态诊断、已有本地 Appium 的同步连接、固定受管根初始安装、scope-managed Appium 启动/usage/自然清理、三个 allowlist 官方 driver 的显式 ensure 与显式 Driver Doctor；Automation 当前公开契约为只读 Android ADB 设备发现、明确 Session 生命周期及 managed Runtime usage lease 接缝、Android Native 结构观测与 Element 接缝、Element 单击/双击/长按和必要等待、Element 文本输入/清空/替换，以及 Element 滑动、滚动、受限官方滚动查找和拖放。显式服务 stop/restart 与其他后续能力仍须逐 feature 确认。合同确认不等于实现、真实三平台资格、模块或平台 Done；团队角色不属于产品运行时架构。

第 31 行替换为：
Runtime、Contracts、Configuration及Automation的当前公开契约由对应模块SPEC维护；Runtime 的受管初始安装清单与后续官方 driver maintenance/Doctor 是不同资格层，均不自动声明服务、设备、Session或三平台验收。Integrations当前公开契约包含Host中立的本地stdio MCP，以及与其同源、前期只面向FSQ的进程内Python ToolCall表面。契约确认或feature限定Done均不等于模块、平台、FSQ Host资格或设备链路已验收。
```

再在现有 `## Local Managed Appium Startup And Scope Lifecycle` 章节精确替换 records bullet：

```markdown
- RT-LOCAL-03 的 `supported_combinations()` 与 `Runtime.install()` 继续拥有精确初始安装清单，当前仍为 Appium 3.7.0 + UiAutomator2 8.7.0；RT-LOCAL-04/05 不改变其初始组件版本 installed/reused/conflict 语义。记录命名空间仅做窄兼容 delta：`records/` 精确允许必需 `installation.json`、可选 `service.json` 与可选 `maintenance.json`，任何其他文件继续 recovery；service 不存在或合法 `stopped`，且 maintenance 不存在或合法 terminal `complete | failed` 时 install 才可继续原资格核对；service/maintenance 非终态、recovery 或非法 schema 时 install/start/maintenance 均在各自写入或组件命令前阻断。
```

随后紧接该 managed lifecycle 章节追加：

```markdown
## Local Managed Driver Maintenance And Official Driver Doctor

- Runtime 在已验收固定受管根上新增两个显式同步准备入口：`ensure_managed_driver()` 只确保一个允许的官方 driver 已安装，`run_driver_doctor()` 只运行该已安装 driver 的公开 Doctor；唯一 short name 为 `uiautomator2 | xcuitest | mac2`，并分别固定映射官方 npm package `appium-uiautomator2-driver | appium-xcuitest-driver | appium-mac2-driver`。不接受第三方名、版本、source/package/path 或任意附加 CLI 参数。
- RT-LOCAL-03 的 Appium 3.7.0 + UiAutomator2 8.7.0 仍是精确初始安装清单；维护资格要求 `installation.json` 合法 complete、受管 Appium identity/entrypoint 可靠且实际 SemVer 为 `3.x`、service absent 或合法 stopped、maintenance absent 或合法 terminal complete/failed。`incomplete | cleanup_pending | recovery_required` 或任一非法记录在 install/start/ensure/Doctor 的写入和目标 CLI 前保守阻断。
- 缺失 driver 只通过受管 Appium 公开 `driver install <short-name> --json` 无版本委托一次；Runtime 不维护 Appium minor/patch 与 driver 版本矩阵，不搜索兼容旧版、不更新 Appium、不 retry/fallback/update/uninstall。安装前后均以 `driver list --installed --json` 白名单复查官方 package identity、可靠版本和受管路径；非零或最终事实不符明确失败。
- Driver Doctor 是显式、可能修改当前账号环境的准备操作，不属于静态 `diagnose()` 或普通 `start_managed()`。Appium 3.7.0 的 `--json` 不关闭 autofix，成功 stdout 仅为整数 check count，且无-autofix optional finding 仍可能 exit 0；因此产品成功语义仅为保守 `accepted`，子进程一旦启动固定报告 `may_have_modified_environment=true`，任何非零统一 Doctor 错误，不声称 zero findings、平台 ready 或设备/Session qualified。
- 两入口默认共享 600 秒总预算，失败/取消/超时后最多额外 30 秒进程组与双流收尾；持续排空、非结构化流内部最多 64 KiB，结构化 stdout 最大 1 MiB且必须完整解析。结果、记录、progress 和受控错误只允许固定 driver、已验证 SemVer、稳定代码/count/布尔事实，不泄漏路径、环境、npmrc、凭据或 stdout/stderr 原文。
- 复用 CPython 3.11 标准库、现有 Runtime 账号锁/安全根/进程组/原子记录，以及既有批准的 `node-semver==0.9.1` 和受管 Appium 3.x 公开 extension CLI；零新增或升级产品/开发依赖。`Runtime.cleanup_installation()` 返回 `InstallationResult | DriverMaintenanceResult | DriverDoctorResult`，按同实例唯一 installation/ensure/Doctor cleanup-pending owner 返回同形结果；无 pending 保留既有幂等 InstallationResult，且不按磁盘 PID/PGID 接管崩溃遗留。
- 本契约不授权真实 npm 网络、受管根写入或 Doctor autofix；每个 driver/平台的真实 install 与 Doctor 都需单独明确环境、允许副作用、数据保留和恢复授权。Android 证据不替代 iOS/macOS；CLI accepted 不等于服务、设备、Session、平台或 Runtime 模块整体验收。
```
