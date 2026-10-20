# Module: Runtime

## Purpose

本模块维护 Appium 运行环境相关职责的边界。

当前确认本地静态诊断Interface及边界；设备发现/就绪由Automation或调用方负责，服务/组件管理的后续细节按feature确认。

## Responsibilities

- 维护后续确认的 Appium 运行环境管理与检查职责。
- 为运行时能力提供唯一的模块归属。

## Non-Responsibilities

- 不负责具体设备操作、观测能力或 Agent 接入协议。
- 不定义配置的来源与静态校验规则。

## Module Relationships

本模块可依赖 `configuration` 和 `contracts` 中后续确认的能力，不依赖 `automation` 或 `integrations`。

## Current Status

静态诊断契约已确认，实际实现与验证以交付证据为准；本模块首批整体验收仍需后续服务/组件能力与真实Android链路。

## Static Local Diagnostics

以下为已确认的静态诊断Interface与约束；不提前承诺后续服务/安装方法。

### Python Architecture And Dependencies

- `appium_connect_agent.runtime` 为本模块公开入口；唯一共享 `LocalSettings` 定义在 `appium_connect_agent.contracts`，Runtime重导出。诊断报告、操作控制、进度和执行异常由Runtime拥有。
- 当前feature不依赖Configuration/Automation/Integrations、不新增运行依赖。不得导入Appium内部JS实现或将模块文件当可执行插件。

### Public Interface

- `Runtime(settings: LocalSettings, *, on_progress: Callable[[ProgressEvent], None] | None = None)` 构造仅进行纯值检查，零I/O。
- `diagnose(*, control: OperationControl | None = None) -> DiagnosticReport` 是本feature唯一业务方法；不提供connect/install/update/uninstall/stop/restart的未实现占位入口。
- `DiagnosticReport` 含operation_id、UTC aware observed_at、固定host/target/driver、不可变checks和observer_errors，无总体ready布尔值。
- `DiagnosticCheck` 含check_id、status（pass/fail/unknown/not_applicable）、稳定reason_code、有界脱敏evidence和可选remediation。缺失/确定不兼容为fail，不明/权限/解析失败/未检查为unknown；not_applicable仅用于实际不适用。
- `OperationControl` 默认总预算10秒，有限正数timeout_seconds，可选跨线程Event取消令牌；ProgressEvent只含operation_id/phase/check_id/message，不伪造百分比。

### Static Diagnostic Behavior

- 首批固定macOS/Android/UiAutomator2，只检查已识别Appium/driver包元数据、Node/npm候选及显式Java/SDK文件布局。存在不表示可执行/服务就绪/设备可用。Node实际版本、service/device检查本feature为unknown/not_checked。
- 显式路径优先，失败不回退；PATH在操作开始后快照，最多64个绝对非空项目；重复真实路径去重，无法唯一选择为歧义，不静默挑版本。appium_home未提供时，~/.appium仅为来源明确的候选，关联未能证明时不得宣称当前driver环境。
- 不读取APPIUM_HOME/ANDROID_HOME/ANDROID_SDK_ROOT/JAVA_HOME作为产品设置，不扫描全盘；未指定Java/SDK不能据默认目录缺失宣称机器不存在它们。
- 只读普通文件，单份最多1MiB、每操作最多64份；元数据祖先查找最多8层且需包名/bin映射证明身份。不能依据cache YAML或dependencies单项取代实际包证据。
- 最多32条检查，每项8段证据，每段512字符；截短显式标记。证据只提取白名单字段与规范化路径，不返回整份配置、完整PATH、敏感凭证或任意异常repr。
- 不执行任何子进程、HTTP、Appium/driver/doctor/ADB命令，不导入执行JS；不写安装目录/缓存，不创建服务/Session。声明兼容性与实测支持分别报告：能可靠判定版本违反声明约束时declared_compatibility=fail；信息不足/约束不可可靠解析时为unknown。静态声明匹配不等于已验证支持；精确组合未经资格实测时qualified_support=unknown，不建立默认支持条目，也不覆盖声明兼容性已知失败。

### Coordination And Errors

- 诊断操作持统一非阻塞协调锁至结果/异常完成；同实例、不同实例及不同进程并发均明确报忙，独立诊断完成释放。构造不获取锁。
- 当前macOS登录账号所有项目使用固定 `~/Library/Application Support/appium-connect-agent/runtime.lock`；不随项目/端口/安装路径变化。flock加同进程互斥，父目录0700、文件0600、拒绝符号链接及非本人拥有目标，释放关闭不unlink锁文件。不承诺跨登录账号互斥；未来整机多账号需求须先另定共享权限设计。
- 允许且仅允许本库协调资源的必要写入，诊断组件/服务/设备保持只读。锁资源失败为执行错误，不能混入组件缺失。
- RuntimeOperationError携带稳定code/operation_id/partial_report；EnvironmentBusyError、OperationTimeoutError、OperationCancelledError为具体子类。预期诊断发现进报告；取消/超时/锁失败抛操作异常，附部分报告。
- 取消、KeyboardInterrupt或异常均finally释放协调资源。进度回调同步执行且计入总预算；首次普通回调错误后停用并记录脱敏observer错误，继续实际检查；不吞掉取消/KeyboardInterrupt。

### Verification Boundary

- 必须验证构造零I/O、静态事实/缺失/未知区分、显式路径优先/歧义、有界文件读取与证据、实际跨进程锁互斥、取消/预算/观察者失败及资源释放。
- 真实本机静态读取应验证不写组件目录、不发起服务或设备请求。无需设备才能验收该feature，但不能把静态检查通过代替首批真实Android Session创建关闭整体验收。
