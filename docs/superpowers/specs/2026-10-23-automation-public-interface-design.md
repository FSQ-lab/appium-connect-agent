# Automation 对外公共 Interface 重设计

日期：2026-10-23（Asia/Shanghai）。TaskID：`AUTO-IF-DESIGN-01`。

状态：**v0.1 设计草案；by/value及首版parent+XPath边界增量已独审，F02修复复审通过；系统/应用接口增量独审通过，构造全参数/版本选型/异常恢复及新增产品取舍仍未完成，不是实现 Ready。**

## 1. 授权、依据与文档关系

本会话用户原始授权：

> $requirements-to-design 重新设计 Automation 对外公共 Interface，按本会话已确认方案推进：先形成接口总表，再收敛公共规则、场景推演和近期 feature 设计；沿用现有需求基线，排除 evidence，不修改 SPEC 或实现。

本文是该授权下的新设计入口，保留[原需求稿](2026-10-22-automation-requirements-design.md)及[原交接台账](../../tasks/automation-delivery-ledger.md)的历史原文与确认记录。本文不将原稿标为已废弃，不把旧 AUTO-01–09 地图当作已批准实施顺序。原稿中称为“已确认”的需求按其记录沿用；原稿最终文稿确认状态与本设计最终确认分开记录。

固定起点：仓库 `/Users/qunmi/Documents/FSQ_LAB/Appium_connect_agent`，分支 `master`，HEAD `fa0eb4bddae0f61379833ae4d2f5a8d18d62be00`。本任务唯一文档负责人为主会话 Tech Lead。开始时已有六处角色/配置修改及未跟踪的 `2026-10-23-runtime-local-installation-design.md`，均属任务外改动，不改写、不纳入本次交付。该 Runtime 草稿不作为当前契约。

读取依据：根 [AGENTS](../../../AGENTS.md)、[SPEC](../../../SPEC.md)、[设计工作流](../../../.github/skills/requirements-to-design/SKILL.md)，以及 [Automation](../../../modules/automation/SPEC.md)、[Runtime](../../../modules/runtime/SPEC.md)、[Contracts](../../../modules/contracts/SPEC.md)、[Integrations](../../../modules/integrations/SPEC.md) SPEC。固定文件哈希和初始工作区保存在本地审查材料 `/tmp/aca-auto-interface-design-20261023/baseline.json`；临时材料不是产品 evidence，也不是持久设计依赖。审查结论另记本节状态，不以临时路径代替本文内容。

**本批 SPEC 决策：no-delta。** 只写设计，根和模块 SPEC 仍是当前契约；未来需要的契约增量见第 10 节。没有产品代码、测试、依赖、设备、Appium 服务操作或提交/推送授权。

## 2. 目标、非目标与确认状态

目标用户是直接 Python 调用方，以及未来 MCP/CLI/SDK Adapter 的实现者。Automation 的 Interface 包括参数、前置条件、执行保证、顺序要求、结果、失败及资源生命周期，不止方法名。调用方应能只依赖公共 Interface 使用一个完整设备操作。

当前一个平台组合：**macOS 宿主 / Android 真机或已启动模拟器 / UiAutomator2**；一个设计模块：Automation。研究 iOS 项目只用于比较，不形成 iOS/macOS 目标或其他宿主交付承诺。过滤浏览器、DOM、CSS、WebView context；含 WebView 的应用只处理 Android Native 实际暴露结构。

本轮不设计 evidence、截图和图像识别；不交付实际 MCP/CLI、远程云、自管 Appium、设备调度器或业务任务规划。只对近期 feature 补详细契约，远期保留目标和依赖，不同时展开全模块实现。

状态标记：`沿用`＝原需求最终确认记录；`本轮确认`＝本会话明确回答；`建议待确认`＝设计建议；`待技术核验`＝须官方版本资料/资格验证；`后续候选`＝不进入首批。表中英文名和参数名均为**语义草名**，不是已批准 Python 签名、发布承诺或安装占位。

### 2.1 本会话已确认原则

用户对以下五项的原文确认：“你说的5个都很正确。”

1. 统一目标表达，区分定位条件、元素 ID 和快照引用。
2. 一个操作内部的必要组合与调用方批量/流程执行分开。
3. 按动作定义必要前置条件，不能统一套“可见且可点击”。
4. 命令完成、状态核对、预期条件满足和用户任务完成分别表达。
5. 不同接入复用同一执行语义，Integrations 不各自实现设备步骤。

2026-10-23 本会话提问：“Session 公共规则建议：每次设备操作都明确归属一个 Session，Automation 不维护‘当前活动 Session’；MCP/CLI 可以在接入层为用户保存选择，但调用核心时仍须明确 Session。是否采用这个方向？”用户回答：**“采用明确 Session（推荐）”**。这只确认归属规则，未批准 Session 对象形态、持久化、Registry、daemon、并发或 Runtime 锁变更。设备发现发生在 Session 创建前，不要求先有 Session。

随后本会话提问：“下一项执行规则：同一个 Session 正在执行操作时，另一个调用到来，建议立即返回‘忙’，不自动排队，以免排到执行时界面已经变化。是否采用？这只决定单个 Session 的重叠调用，不限制不同设备。”用户回答：**“立即返回忙，不排队（推荐）”**。由此确认同一 Session 操作重叠时，后来调用在发送其设备命令前返回忙，不等待执行槽位、不隐式排队；不打断前一操作。这不是不同设备并行已实现的声明，不改变 Runtime 锁。关闭与取消的具体竞态和收尾机制仍待设计。

对“创建得到 Session 对象、通过对象执行操作并显式关闭，接入层将可见 Session ID 映射到对象，核心不要求全局 Session 注册表”的建议，用户原文：**“这个方向没有问题，但是命名方面请按照 appium的方式走，不要按照selenniums的方式走”**。确认显式 Session 对象方向及 Appium 优先的命名原则；不是具体类名、全部方法、客户端版本、Selenium 依赖或实现方案的批准。

命名规则：以 Appium 官方移动能力及其 Python 客户端公开用语为第一依据，Python 方法采用对应的 snake_case；核对动作语义和对象层级后再确定名称，不从 Selenium 浏览器工具或其他项目借用 fill/check 等名称。Appium 也使用 WebDriver 及部分共用的元素术语，不能仅因名字共用就擅自发明替代词。项目增强能力（设备发现、范围化结构观测、条件等待等）没有同义官方入口时明确标为项目能力；同名却不同参数或保证的映射必须说明，不将 driver 的元素到元素 scroll 冒充容器滚动。表内尚未核对的草名不因本次原则确认自动转为定案。

随后本会话提问：“生命周期建议：同一 active Runtime 连接供多个 Session 使用，每个 Session 绑定明确设备和独立客户端；正常使用时先分别 quit，再退出 Runtime。是否采用这个模型？创建/quit 结果未知时的恢复细节下一步单独设计。”用户回答：**“采用单连接、多 Session（推荐）”**。确认正常使用模型，不表示 D02 中异常恢复、跨进程占用、退出竞态、并发资格、具体类型或库版本已经获批。

关于客户端异常消失后的回收，用户提出复用 Appium Session timeout；在明确 newCommandTimeout 的空闲语义、正常 quit 与超时兜底、以及原默认 0 需要调整后，用户指定：**“我们直接 500秒？”**。按该具体选择，将本轮设计默认更新为 **`appium:newCommandTimeout=500` 秒（8 分 20 秒）**，替代原稿默认 0；沿用调用方可显式覆盖的规则。正常无命令间隔超过该预算可能使 Session 自动失效，不自动重建或重放；该确认不批准自动心跳、持久恢复记录或仅凭计时就释放未知占用。

在本轮说明不增加后台心跳/自动重建、回收不可仅凭计时认定以及定位映射仍为草案后，用户答复：**“没有问题，请继续”**。该答复允许继续收敛文档，不等于确认每个定位类型、前置条件、跨进程恢复保证或第三方选型。对输入特殊结尾的单项提问“UiAutomator2 的文本命令会把末尾字面量‘反斜线+n’（两个字符，非真实换行）识别为 Enter。为保持输入/替换不隐式提交，建议首批在发送前拒绝这种特殊结尾；正常换行的支持另行验证。是否采用？”用户明确回答：**“拒绝特殊结尾（推荐）”**。因此 send_keys/replace_element_value 在任何设备请求（含定位/聚焦）前检查该结尾，拒绝时不改写文字、不发 Enter，也不增加自研编码回退；真实换行及其他控制字符处理仍待目标版本资格核验。

点击类前置条件单项提问：“点击、双击、长按的默认前置条件，建议是‘唯一匹配、已显示、已启用’；不强制要求 clickable=true，因为部分实际可操作控件不会暴露该属性。条件满足后执行一次，不自动滚动或处理弹窗。是否采用？”用户回答：**“采用这组前置条件（推荐）”**。此确认只覆盖点击/双击/长按的默认前置及一次执行，不自动确认文本/clear/replace/属性读取、坐标目标的状态检测或全面可点击性保证。

文本前置单项提问：“输入、清空、替换均要求唯一匹配、已显示、已启用，由 Appium 执行元素文本命令；不强制要求原本已有焦点，不额外点击或隐藏键盘。是否采用这组规则？”用户要求举例；以唯一用户名输入框在加载期间暂被禁用为例，说明等待启用后执行相应操作一次，未显示时只等待、不自动滚动或切换页面，超出等待预算返回等待失败，不额外点击聚焦。明确说明这些基本条件不证明目标可编辑，可编辑性检查仍待讨论后，用户回答：**“确认”**。本轮据此确认 IF-13/14/15 的基本准入和无额外聚焦/滚动/隐藏键盘，不扩大为编辑性检查规则、读回验证、文本完整写入保证或所有输入参数批准。

属性读取单项提问：“读取控件属性。建议只要求唯一匹配，不要求已显示、已启用或已有焦点。例如，可以读取禁用输入框的文字和 enabled=false；实际不可读取时明确报告失败或未知。是否采用这条读取规则？”用户回答：**“确认”**。此确认覆盖 IF-06 的读取准入；不要求通过操作先启用/显示/聚焦控件，不自动滚动，不把 driver 无法返回的属性捏造为 false 或空串。它不保证 driver 能定位未显示控件，也不批准为此隐式改变采集设置；属性列表、返回结构和缺失/未知分类仍待设计。

文本可编辑性取舍：说明所查 UiAutomator2 无通用公开 editable 属性、不能靠 focusable/className 可靠判断，建议“不增加自研可编辑性判断，完成已确认基本检查后直接交 Appium 文本命令”，并明确“误选非输入框时不保证报错，某些进度控件可能把输入解释为数值设置”后，提问是否接受沿用 Appium 行为，用户回答：**“好的”**。本轮据此采用第 5.1 节方向 A；不增加 editable 必须为 true 或 className 白名单，不承诺误选控件一定失败，也不扩展为独立滑块/数值控件产品能力。该确认是使用官方行为的产品取舍，不批准具体第三方库/版本或自研例外。

坐标基准单项提问：“相对坐标基准。建议统一以本次操作时的设备当前显示区域为基准，例如 (0.5, 0.5) 表示中心；容器范围通过定位条件另行指定，不混用屏幕坐标与容器局部坐标。是否采用这个方向？”用户原文：**“是的，这个版本坚决不用绝对坐标”**。本版所有公开操作的点、起终点、区域及偏移坐标只接受按宽高分别归一化的 [0,1] 表达，统一基于本次操作时设备当前显示区域；不提供绝对像素坐标模式、参数、便利别名或透传例外。容器通过定位条件指定，不把输入的同一组坐标改按容器局部解释。Automation 内部按官方入口转换为原生坐标，不将底层需要像素坐标泄漏为调用方要求。该确认不改变原稿保留观测几何信息的需求，也不等于已批准修改所有速度单位或观测 schema；几何采样、旋转/多窗口/键盘影响和精度边界仍待技术核验。

对“区域滑动/滚动显式指定容器定位或相对区域”的提问，用户修订为：**“是的，更简单一点描述，我们操作的这些都应该是一个element。需要传入一个element 对象，这样就能确定区域了。”** 本轮据此统一控件与区域相关操作的公开目标输入为 Element 对象，由目标对象确定操作区域；不再让各操作重复接收容器定位或独立区域两套入口。此修订覆盖界面目标，不把设备发现、Session 生命周期、应用管理或硬件按键强制改成 Element 操作。Element 是否为本项目定位对象或官方原生元素、如何构造及绑定 Session 尚未确认；不能仅凭“对象”认定已批准缓存 Appium elementId 或推翻每次重定位规则。相对区域如何表示为 Element 仍待设计，绝对坐标禁令保持。

随后明确提问：“Element 建议保存定位条件，每次操作重新定位并获取当前区域，不缓存旧的 Appium 元素句柄。这样延续此前的重定位规则。是否按这个方式定义 Element？”用户回答：**“确认”**。由此确定 Element 为本项目定位描述对象，普通控件操作传此对象，内部每次解析当前唯一官方元素及所需当次几何，不接受裸 Appium WebElement 或跨调用 elementId 作为同义目标，不把历史 bounds/观测节点当活句柄。前段关于项目对象/原生对象的未决状态已由本条收敛；具体创建入口、父关系结构、Session归属、相对区域表示及类型字段仍未确认。

随后提问：“Element 由所属 Session 创建并绑定；传给其他 Session 时直接报错。创建对象只保存条件，实际定位在操作时进行。是否采用？”用户回答：**“没有问题，”**。本轮据此确认创建入口归属 Session，Element 在创建时绑定该 Session 对象，创建只保存条件、进行必要纯值校验，不查询设备；真正定位发生在操作中。跨 Session 使用时在发送设备请求前报错，不按相同设备 ID、Appium sessionId 或相同定位条件自动改绑，也不自动复制为另一个 Session 的目标。具体工厂名、定位字段、父关系及相对区域构造未由此确认。

用户追加：“好的，请继续。 另外，这些都是appium相关的问题，请 找 appium 专家协助”。Tech Lead 明确委派独立新上下文 `/root/appium_element_expert`、任务 `AUTO-ELEMENT-EXPERT-01`，只读研究 Element 构造、父子查询、定位复用与滚动限制；无文件写入/设备/安装/测试/子委派授权。该专家完成实际原文首读、哈希和官方来源核对；建议用于下文草案，不作为用户确认、依赖批准或独立设计审查。

工厂形态具体提问给出关键字方案（resource_id/text/content_desc 可 AND、xpath 独立、parent 为同 Session Element），用户明确选择：**“希望用 Appium 的 by/value”**。据此采用 by/value 的公开构造方向，不采用多个属性关键字工厂；父 Element 输入、package/短ID及具体签名仍待确认。该选择不撤销原先精确文本/属性组合需求，不批准新造 AppiumBy.TEXT/COMPOSITE、任意可执行 UiAutomator 字符串或关键字到表达式自研方案。专家补充核对 Appium 标准策略与调用方原样 XPath 组合表达。

父 XPath 单项提问：“首版是否采用这条边界：parent 暂用于 ID/accessibility id 等可确认范围的子查询；不支持 parent＋XPath，根级 XPath 仍可用？这样不需要解析或改写 XPath 来猜测它是否越出父范围。”用户回答：**“首版不支持该组合（推荐）”**。本轮据此确认：子目标 by=XPATH 且 parent 非空的组合在创建 Element 的纯值校验阶段拒绝，不查询设备、不丢 parent 退回根查询；根级 XPath 保留且本库不改写。该限制不自动禁止根 XPath 创建的 Element 作为父，再以 ID/accessibility id 查询其子元素；此路径仍需官方能力与版本资格验证，不从当前决定推断全面支持。parent 的详细参数/其他策略集合和属性AND表达通道仍未全量确认。

### 2.2 必须沿用的需求

- 操作及单控件查询唯一匹配；多匹配报歧义，不自动选第一个。属性组合、父容器、包名参数化；文本精确匹配，不隐式清洗。XPath 交 Appium，不自研解析/改写。每次操作重定位，单次可用官方元素对象，不建立跨次自有 ref/缓存体系。
- 输入、清空、替换是三个意图。普通输入沿官方行为，不额外清空；是否严格追加到末尾不能从“输入”一词推断。聚焦与其他前置步骤逐操作设计。
- 条件等待 5/15/60 秒，默认 15 秒，允许具体时长，满足即继续；与命令响应超时和 Session 空闲期分开。默认条件满足后动作执行一次，有效命令成功响应即命令完成，不自动等页面变化或判断业务成功；超时/失效不自动重放、重建。
- 设备显式指定；不启动模拟器、不提供任意 ADB。Session 跨调用复用；默认保留数据、`autoLaunch=false`、`noReset=true`、`shouldTerminateApp=false`。空闲超时按本轮具体修订为 `appium:newCommandTimeout=500` 秒，调用方可显式覆盖；旧稿默认 0 只保留为历史。参数组合与例外以官方核验为准，不创造 restart 等模式。
- 同设备本库 Session 互斥，创建前占用，确认关闭后释放；关闭未知不误判空闲。不新增全局单 Session 限制，不承诺当前 Runtime 已支持多设备并行。
- 控件树为 JSON，范围内保留节点、层级、完整文字、属性/必要状态/几何；上限 65,536 UTF-8 字节。超限转当前可见内容与必要祖先，明确范围；仍超限报范围过大，不截文字或静默丢尾部。原始结构补取同样受上限约束；不跨页遍历、分页、游标或差异续读。`enableMultiWindows=true` 的实际来源与可见性待核验。
- 单控件字段精简与短名可还原规则完整引用原稿“单控件字段精简规则”；未知/不适用/有意义空值保持区别，不因本表省略而撤销。
- 本版公开操作坐标只接受当前显示区域基准的 [0,1] 相对表达；不新增绝对像素坐标输入，内部转换由 Automation 承担。点/区域及已选手势适用同一原则，定位条件本身不变。

## 3. 接口总表 v0.1

下列除设备发现外，所有设备能力都由明确 Session 对象承载归属；接入层可映射外部句柄，不作为核心 Registry 方案。具体类名尚未确定。`Control` 复用 `runtime.OperationControl` 的总预算与取消输入；`control=None` 沿 Appium 默认处理。成功直接返回语义值，受控失败使用第 5.0 节已确认 Automation 异常。

**Element 修订优先规则**：下表原列出的“目标定位、容器、相对区域”对控件/区域操作统一从 Element 对象取得；表中定位策略和相对几何保留为目标描述需求，不再表示操作方法的并列公开参数。普通动作一个 Element，拖动涉及源/目的 Element；滚动查找的容器 Element 与目标条件/Element 如何组合仍须尊重官方策略限制，未完成签名确认。第 4.3、5.1 和 5.2 的 Element 增量覆盖旧 locator 参数草案，旧草案不作为新增别名一并发布。

### 3.1 设备与 Session

| ID / 意图草名 | 调用方输入与意图 | Automation 执行职责 | 成功保证；失败/未知 | 状态与依据 |
| --- | --- | --- | --- | --- |
| IF-01 `list_devices` 查询设备 | 显式 Android 工具配置及 Control，实际字段待核验 | 有界查询已连接真机/已启动模拟器，返回标识、名称、连接状态；不自动选设备 | 查询完成与空列表分开；发现失败不能伪造无设备 | 沿用；原稿设备发现，U02 |
| IF-02 `create_session` 创建设备会话 | connection 使用资格、设备 ID、应用 package/APK、capabilities、Control | 校验范围/冲突，取得设备占用，经批准客户端创建，保存资源身份 | 返回可明确操作的会话；创建失败区分确定未创建、已创建待清理、创建结果未知 | 意图沿用；参数/资源模型待 U01/U02/U03/U06 |
| IF-03 `session_info` 读取会话信息 | 明确 Session；纯本地读取，不发健康查询 | 返回本库身份、已知Appium sessionId、设备、目标应用及 `creating/active/uncertain/closing/closed` 最后状态 | 历史状态不冒充持续健康；busy作为active操作状态另示；不重置500秒空闲计时 | 生命周期模型本轮确认；不引入健康轮询 |
| IF-04 `quit` 关闭会话 | 明确 Session、Control；官方关闭相关设置在创建处固定 | active且不busy时调用客户端终止一次并收尾；closed再次调用为空操作成功 | 确认关闭后释放本进程设备占用；失败/未知转uncertain且不自动重试；主错误和清理错误分别保留 | 意图与Appium `quit` 命名沿用；幂等/未知规则本轮确认，实际异常待资格验证 |

“复用”指调用方保存同一 Session 多次操作，不是附加任意外部 Session。外部 attach、跨进程恢复和全局列举 Session 属后续候选。

### 3.2 观测、定位与等待

| ID / 意图草名 | 调用方输入与意图 | Automation 执行职责 | 成功保证；失败/未知 | 状态与依据 |
| --- | --- | --- | --- | --- |
| IF-05 `observe_tree` 读结构 | Session、可选父容器定位、Control | 采集、保留原始层级、唯一短名转换、按既有大小规则回退范围 | 当前请求范围的结构与覆盖说明；采集失败/缩小后仍超限分别报告 | 沿用；schema、计量及采集限制待 U04 |
| IF-06 `inspect_element` 读唯一控件属性 | Session、定位条件、父容器、所需属性、等待/Control | 重定位、检查唯一性，读取请求属性；不要求已显示/已启用/已有焦点，不额外改变设备状态 | 唯一控件属性；缺失、歧义、读取失败/未知与不适用分别表达，不返回底层 driver | 沿用原稿 Q41；读取前置本轮确认；属性/schema待定 |
| IF-07 `inspect_structure` 补原始定位依据 | Session、目标定位、邻近/容器范围，具体范围参数待设计 | 获取指定控件附近的原始层级/属性依据，适用同一 64 KiB 限制 | 局部范围及定位依据；不推断全局唯一性，不返回快照引用 | 沿用；U04 |
| IF-08 `wait_until` 等条件 | Session、定位及条件、5/15/60 或显式秒数、Control | 仅查询轮询，不反复点击/输入；目标条件集合逐项核验 | 条件满足或等待超时；查询失败与有效观测下不满足有区别 | 等待意图沿用；条件集合待定 |
| IF-09 `check_condition` 单次条件查询 | Session、条件，不含等待预算 | 建议与 wait 共用条件语义，执行一次读取 | true/false 与无法判定区别；不偷偷等待 | 建议待确认；不是已批准 assert 家族 |

定位条件本身是纯值，可重复传递；“已定位父容器”建议解释为父定位条件在同次操作内解析，不能直接据此创建跨调用缓存元素。原始 XML 与精简 JSON 的对应仍须 U04 核验。公开多控件列表查询/候选枚举是否需要另列，尚未确认；歧义诊断不自动形成 `find_all` 承诺。

### 3.3 控件与文本动作

| ID / 意图草名 | 调用方输入与意图 | Automation 执行职责 | 成功保证；失败/未知 | 状态与依据 |
| --- | --- | --- | --- | --- |
| IF-10 `tap` 单击 | Session、唯一目标或当前显示区域基准的 [0,1] 相对位置、等待/Control | 控件目标默认唯一、displayed/enabled后执行一次；坐标路径内部转换，不自动处理挡路弹窗或滚动 | 点击命令完成；不代表页面跳转；未发送/失败/未知可辨别 | 沿用 A1；控件前置、相对坐标与基准已确认，几何技术细节待核验 |
| IF-11 `double_click_gesture` 双击 | Session、目标、等待/Control；无自定义双击间隔 | 控件目标默认唯一、displayed/enabled；官方 mobile: doubleClickGesture 单次请求，避免 Integrations 拼接两次调用 | 双击命令完成；底层局部执行不可推断为未执行 | 沿用 A2；控件前置已确认，名称/映射为 Appium 风格草案 |
| IF-12 `long_click_gesture` 长按 | Session、目标、可选 duration 毫秒、等待/Control | 控件目标默认唯一、displayed/enabled；官方 mobile: longClickGesture，未指定沿所核官方默认 500ms | 命令完成，不保证菜单出现；超时保留未知 | 沿用 A3；控件前置已确认，版本签名/默认值待资格验证 |
| IF-13 `send_keys` 输入 | Session、目标、文字、等待/Control | 唯一、displayed/enabled 后调用普通元素 send_keys；不要求预先聚焦，不额外点击/清空/滚动/隐藏键盘/提交 | 官方输入命令完成；不自动升级为精确值验证或真实键盘事件保证 | 沿用 A4；基本前置、特殊结尾拒绝、不自研editable识别已确认；版本适配待核验 |
| IF-14 `clear` 清空字段 | Session、目标、等待/Control | 唯一、displayed/enabled 后执行官方元素 clear；不要求预先聚焦，不额外点击/滚动/隐藏键盘 | 清空命令完成；不冒充已回读空值 | 沿用 A5；基本前置、不自研editable识别已确认；与应用 clear_app 分开 |
| IF-15 `replace_element_value` 替换 | Session、目标、文字、等待/Control | 唯一、displayed/enabled 后调用一次官方 mobile: replaceElementValue；不要求预先聚焦，不额外点击/滚动/隐藏键盘，不拼 clear+send | 官方替换命令完成；内部 partial/超时仍可能已改变文字，不自动回滚/重放 | 沿用 A6；基本前置/特殊尾缀拒绝、不自研editable识别已确认；不从 input 合并出 replace 参数 |

单次操作内的临时官方元素与跨步骤重定位如何避免目标改变，须在文本近期设计核验；不得简单在 clear 后用原文字 selector 再找目标。精确回读、输入后提交、自动隐藏键盘均不作为本表默认副作用；如建议新增须单列取舍。

### 3.4 滑动、滚动、查找与拖动

| ID / 意图草名 | 调用方输入与意图 | Automation 执行职责 | 成功保证；失败/未知 | 状态与依据 |
| --- | --- | --- | --- | --- |
| IF-16 `swipe` 单次滑动 | Session、方向或当前显示区域基准的相对起终点、适用时长、Control | 校验互斥参数、内部转换、官方执行；不接受绝对坐标 | 手势命令完成；不证明内容移动/到页尾 | 沿用 A8；坐标基准已确认，方向含义与参数变体待核验 |
| IF-17 `scroll` 单次滚动 | Session、目标容器、方向/距离，字段待官方核验 | 容器重定位，映射官方滚动；不暗中循环查找 | 滚动命令完成；若官方返回 canScrollMore 等，保留其准确含义 | 沿用 A9；返回细节待核验 |
| IF-18 `scroll_find` 滚动查找 | Session、明确容器、官方支持的定位策略/selector、maxSwipes 等 | 适配 UiAutomator2 官方 `mobile: scroll`，不另写通用滚动搜索循环 | 按官方支持范围完成搜索；无匹配、策略不支持、错误及执行未知分别处理 | 沿用 A10；U05 |
| IF-19 `drag_and_drop` 拖动 | Session、起终点控件/相对位置、官方支持的按住/移动参数 | 一个操作内完成解析、必要按住/移动/释放；目标组合支持待核验 | 拖动命令完成；不保证业务拖放成功，部分执行须保留 | 沿用 A12；名称按 Appium，复杂轨迹不纳入 |

普通定位的任意属性组合/XPath 不自动适用于 IF-18。本版公开操作只接受当前显示区域基准的 `[0,1]` 相对坐标，不接受截图像素、设备绝对像素或容器局部坐标；底层转换、当前显示区域如何采样及边界舍入仍须明确，不能只做数值范围校验。

### 3.5 Android 键盘、系统交互与应用管理

| ID / 意图草名 | 调用方输入与意图 | Automation 执行职责 | 成功保证；失败/未知 | 状态与依据 |
| --- | --- | --- | --- | --- |
| IF-20 `back` 返回 | Session、Control | 官方返回命令 | 命令完成，不保证回到特定业务页 | 沿用 B1 |
| IF-21 `press_keycode` / `long_press_keycode` Android 系统按键 | Session、整数 keycode、可选 metastate/flags、Control | 校验实际支持，映射官方命令；不另造跨平台键名 | 命令完成；不支持、失败、未知分开 | 沿用 B2/B3；映射已研究，实际 server 类型/组合待资格核验，见 5.3 |
| IF-22 `perform_editor_action` IME 动作 | Session、官方 action、Control | `mobile: performEditorAction` 作用于当前焦点，不用任意换行猜发送行为 | 命令完成，不证明消息已发送 | 沿用 B4；当前焦点语义及是否绑定 Element 见 5.3 |
| IF-23 `hide_keyboard` 隐藏键盘 | Session、Control；Android 不接收 iOS 键名/strategy | 官方能力；失败不自动点击其他区域 | 官方 true＝本次隐藏，false＝原已隐藏；失败与未知不转 false | 沿用 B5；推荐保留 mobile 返回值，见 5.3 |
| IF-24 `get_clipboard_text` 读剪贴板 | Session、Control | 官方纯文本读取及 UTF-8/Base64 薄转换 | 已读取的文本；空字符串与读取失败区别 | 沿用 B6；首版纯文本建议见 5.3 |
| IF-25 `set_clipboard_text` 写剪贴板 | Session、text、可选 label、Control | 官方纯文本写入，不隐式粘贴 | 写命令完成，不代表输入框变化 | 沿用 B6；名称按官方 Python Client |
| IF-26 `accept_alert` / `dismiss_alert` 弹窗 | Session、可选 button_label 映射 buttonLabel、Control | 复用官方接口；不自建按钮识别 | 官方命令完成；错误保留实际原因，不承诺可区分全部识别失败，不自动替代点击 | 沿用 B7；官方识别局限见 5.3 |
| IF-27 `status_bar` 展开通知栏/快捷设置 | Session、command 为 expandNotifications 或 expandSettings、Control | 官方 `mobile: statusBar`；命令白名单 | 官方命令完成，不宣称面板 UI 已核对 | 沿用 B8；建议与 IF-28 合并方法，见 5.3 |
| IF-28 `status_bar` 收起面板 | Session、command=collapse、Control | 官方收起通知及快捷设置面板 | 命令完成；不支持/未知如实报告 | 沿用 B8；不需要猜测原面板类型 |
| IF-29 点击已有磁贴 | Session、Element | 视觉磁贴只复用 IF-10 `tap(element)`；不开放 TileService component `clickTile` | 点击命令完成，不默认为“设置成开/关” | 本轮确认；不新增重复接口，不添加/移除磁贴，见 5.3 |
| IF-30 `activate_app` 激活应用 | Session、package ID、适用官方参数、Control | 官方 activateApp，不隐式 force-stop/重启 | 官方激活结果；不证明特定页面出现 | 沿用应用管理 |
| IF-31 `terminate_app` 终止应用 | Session、app_id、Control；不公开上游 timeout | 官方 terminateApp，具体等待适配受统一操作预算约束，保留其返回语义 | true/false 与 Session 关闭分开，不保证应用持续停止 | 最小选项白名单本轮确认；上游500ms默认不冒充公共预算，见 5.4 |
| IF-32 `query_app_state` 应用状态 | Session、package ID、Control | 官方 queryAppState，保留未知/不支持 | 本次状态，不当作持续健康保证 | 沿用 |
| IF-33 `install_app` 安装 | Session、本地 APK、`replace=True`、`allow_test_packages=False`、Control | 官方 installApp；与创建 Session 必要安装准备分开；不开放其他上游选项 | 官方安装结果；明确数据/升级副作用和部分失败 | 最小选项白名单本轮确认；无设备操作授权 |
| IF-34 `remove_app` 卸载 | Session、package ID、`keep_data=False`、Control | 官方 removeApp，不附带其他应用清理，不开放其他上游选项 | 官方卸载结果；不是 Session 关闭；显式 keep_data=true 才承诺请求保留卸载数据 | 最小选项白名单本轮确认；无设备操作授权 |
| IF-35 `clear_app` 清应用数据 | Session、app_id、Control | 已确认内部检查安装/运行状态、必要终止并核对，再调用官方 clearApp；不得混淆 IF-14 字段清空 | 清数据命令完成；部分完成/未知及后续 Session 不可用分别报告 | 必要组合本轮确认；阶段预算待公共模型，无设备操作授权 |

方法粒度仍可调整：剪贴板读写、弹窗接受/取消可以各为方法或带区分参数；原则是无关必填项不混入同一请求，调用方能明确副作用。框架诊断与 Appium 服务管理仍归 Runtime，不迁入上述 Session 操作。

### 3.6 后续候选与明确排除

| 项 | 当前处理 |
| --- | --- |
| 核心能力查询 `capabilities` | 同业参考，是否提供及静态声明/动态可用性的区别待用户决定，不当成已批准首版 |
| 多控件查询、批量步骤、流程回放、跨页采集 | 后续候选；不由研究过项目自动纳入，特别是跨页采集与原观测不自动遍历范围不同 |
| 当前焦点输入、fling、双指缩放、自定义手势序列 | 原稿未批准首版；本轮未重新批准 |
| 方向、锁屏/解锁；C1–C12 系统环境修改 | 原稿后续范围保持 |
| 外部 Session attach、持久 Session Registry、常驻 daemon | 后续候选；明确 Session 归属不构成这些方案的批准 |
| 自动处理弹窗、自动滚动到任意操作目标、自动重放、业务规划 | 不作为普通动作的默认步骤；如提出新操作另走确认 |
| evidence、截图、图像识别；DOM/CSS/WebView context | 本设计不展开 |

## 4. 公共规则：明确 Session 与目标

### 4.1 Session 使用形态比较

已确认：核心没有当前活动 Session，采用**明确 Session 对象承载设备操作**，接入层把用户可见 ID 映射到这个对象；核心不要求全局 Session 注册表。对象类名及各操作名称按 Appium 用语继续核对，不能把草名示例当成定案。

| 方案 | 调用方式与资源归属 | 取舍与状态 |
| --- | --- | --- |
| A：显式 Session 对象 | 创建得到对象，实例持有本会话资源，所有动作在该对象上，关闭显式 | 本轮方向已确认；不要求核心建全局 Registry；线程/进程使用范围待设计 |
| B：Automation Registry + ID | 每次传入 ID，核心查表执行 | 当前不采用；未来确有持久服务需求时另行设计，不因 MCP JSON 参数提前引入 |
| C：全局当前 Session | 隐式选择活动会话 | 已被本轮明确 Session 决策排除 |

MCP/CLI 的 Session ID 不必就是 Appium 原始 sessionId。独立 CLI 进程不能凭一个字符串自动恢复活对象；需要宿主/执行进程托管或其他经设计的资源方案，属于未来 Integrations 设计，本文不承诺无 daemon 的跨进程复用。禁止用保存底层 driver 或裸 URL 绕过公共 Interface。

### 4.2 Runtime 接缝：当前约束与候选

本节 2026-10-23 增补为 **D02：正常生命周期模型已确认；异常路径及具体机制仍为建议/待决**。先区分现有契约、已有上位设计和本轮建议，避免把多个 Session 误解为多套 Runtime。

**现有契约与代码事实**：`Runtime.connect()` 从准备前到退出持当前账号固定独占锁；connection.server_url 只在 active 范围读取；退出只释放 Runtime 资源，不会替 Automation 关闭 Session。实现为 `runtime/_connection.py` 的 `_ConnectionScope.__enter__/_release`；`_coordination.account_lock` 的同进程互斥加文件锁防止其他连接/实例/进程进入。Runtime 不执行 Session 命令，不构成设备级命令队列。

**已有上位设计**：[Runtime 需求与 Python 调用接口设计](2026-10-19-runtime-python-interface-design.md) R20/P02 及第 7.1 节已经描述一个活跃调用进程、一个活跃 Runtime，同一个 connection 供多个 Session 使用。它没有批准跨进程共享服务或承诺 Session 并发。现行已有本地连接契约也没有要求每个设备各开 connection。因此“按设备各开一套 Runtime 才能多设备”不是现有要求；是否在同一连接内并行发送不同 Session 命令仍须资格验证。上位 managed/UsageHandle 方向不等于当前已经有这些接口。

#### D02-A 推荐的所有权和调用关系

| 所属层 | 持有或管理什么 | 不应混入的职责 |
| --- | --- | --- |
| Runtime | Appium 环境与服务使用资格；当前只有 external 连接范围和账号锁 | 不选择设备，不创建/关闭设备 Session，不为设备命令逐条取得全局锁 |
| Automation 使用方/执行宿主 | 保持一个明确 active connection，为其创建的 Session 安排显式关闭 | 不另外开启“每设备一个 Runtime”，不把缓存 URL 当成已退出连接的使用资格 |
| 每个 Session 对象 | 本会话的客户端、设备身份、设备占用和单次操作准入 | 不维护活动默认值；A 的正常关闭不关闭 B，也不停止 Appium |
| Integrations | 将外部 Session ID 映射到对象、转换参数和结果 | 不实现设备锁、聚焦/清空、重试或 Session 生命周期状态机 |

已确认的正常调用顺序：进入一次 `Runtime.connect()` → 使用该 connection 显式创建设备 A/B 的 Session → 每个 Session 可跨多次调用复用 → 分别 `quit()` → 退出 connection。`quit` 采用 Appium Python 客户端沿用的会话结束术语，不使用浏览器窗口 `close` 的含义；本表 IF-04 的关闭语义不改变，最终签名和实际客户端版本仍待批准。

这里“一个 connection、多个 Session”只复用公开连接使用资格，不共享同一个 WebDriver 实例、原始 Appium sessionId 或设备端口。Session 对象各自绑定客户端和明确设备；不得读取 Runtime 私有 scope/lock 字段实现此关系。建议在正常业务操作准入时读取公开有效性信息；退出连接后拒绝新的业务操作，不偷偷继续使用曾保存的 server_url。退出与正在执行命令并发的原子性仍待生命周期设计，不声称一次有效性读取可以消除竞态。

#### D02-B 三种占用不要混为一把锁

| 约束 | 推荐覆盖区间 | 释放条件 / 不保证的事项 |
| --- | --- | --- |
| Runtime 账号级使用资格 | 当前 connect 准备前至退出；原样保留 | 不放宽到按端口/设备，不允许第二进程绕过 |
| Automation 同设备占用 | 从可能创建 Session 的请求发出前开始，至少覆盖创建不确定、存活、关闭不确定 | 确认未创建或确认终止后释放；外部客户端抢用不在保证内 |
| 同 Session 操作准入 | 操作开始到该操作及必须收尾结束 | 已确认后来调用立即报忙、不排队；超时不等于上游已经结束，不因返回异常提前允许新命令 |

设备占用是既有需求，具体采用进程内状态、系统锁及必要的持久不确定状态记录如何组合仍待 U03/库复用评估。账号锁会在 external 范围退出或进程崩溃后释放；单靠进程内集合或 OS 锁不能证明远端遗留 Session 已终止。若需要跨进程保留“结果未知”，必须另定最小恢复记录、设备身份、权限及核实流程，不能先实现新的全局 Session Registry，也不能静默降低“未知不误释放”。

**U03-P1：进程异常退出后的占用，A/B 比较历史。** 旧需求明确将进程退出恢复列为待设计，不能推断已获批准。候选 A（曾推荐，未获批准）：新进程遇到本库前次遗留且无法确认结束的设备会话时，继续将该设备标为待核实，核实/显式处置前不新建 Session；必须研究最小恢复信息能否覆盖“请求已发出但未收到 sessionId”及崩溃窗口，不先决定存储方式或开放强制解锁。候选 B：保护保证仅在原持有进程存活期间提供，进程退出后明确报告保证终止，遗留会话由调用方核实；这会收窄原本未明确的跨进程保护范围，必须用户具体确认后才可设计。两者都不能将进程退出、账号锁释放或设备断开报告为“已确认远端 Session 关闭”；不涉及自动终止外部 Appium/其他会话。当前优先方向由下文 C 的新决定替代，剩余保证范围待核验。

用户随后提出：“这个能不能直接走 appium 最短 session 时间的一个time out”，并指定 500 秒。因此 C 的服务端空闲回收方向和 **默认 `appium:newCommandTimeout=500` 秒**已作为本轮设计决定；优先复用 Appium，不据此批准自建恢复账本。Appium [3.0 capabilities](https://appium.io/docs/en/3.0/guides/caps/) 定义其为等待客户端下一条命令的秒数，上游默认 60，0 禁用；本项目的 500 是用户选定值，不是上游推荐。它不是会话固定寿命或单条命令执行期限。固定 [appium@3.0.0 BaseDriver](https://github.com/appium/appium/blob/appium%403.0.0/packages/base-driver/lib/basedriver/driver.ts) 的 executeCommand 清除执行期间的空闲计时，命令收尾后通常重新启动；startNewCommandTimeout 到期触发会话关闭。它可作为客户端消失后的正常回收机制，却不能保证卡住的命令/创建/清理在 500 秒内结束，也不能仅凭本地等过 500 秒证明设备已空闲。Agent 思考、等用户或处理其他设备同样可能触发空闲回收；空闲失效后明确报错，由上层决定是否重新创建，不自动续命、重建或重放。正常路径仍显式 quit；A/B 作为比较历史，不把候选 C 等同于已批准跨进程保护或放弃未知占用规则。目标实际 Appium/driver 版本、回收副作用及回收后核实入口仍须验证，不引用该源码快照冒充已验收环境。

**回收核实研究增量（2026-10-23，尚未独审）**：[Appium 3.0 getAppiumSessions](https://appium.io/docs/en/3.0/reference/api/appium/#getappiumsessions) 的 `GET /appium/sessions` 需要启用 `session_discovery`；不自动要求用户打开此特性，也不默认枚举其他客户端的会话。已知 sessionId 可研究按需查询能力的公开入口；但这类 Session 命令会经过其命令执行路径，可能重置空闲计时，不得靠连续轮询阻止已选择的 500 秒回收。创建响应丢失、尚无 sessionId 时，不能猜测会话 ID、归属或把空列表当作创建已结束。

固定 [appium@3.0.0 AppiumDriver](https://github.com/appium/appium/blob/appium%403.0.0/packages/appium/lib/appium.js) 中，deleteSession 在等待 driver 清理完成前就移除 master session list 条目；unexpected shutdown 监听也会移除条目。因此“旧 sessionId 不存在/不再列出”最多说明该服务不再接受该 ID 的命令，**不单独保证设备端、端口或驱动资源已经清理完成**。这不否定 Appium 的正常超时回收，而是限定本库可以声称的保证。实际目标版本及 UiAutomator2 清理时序仍须资格验证。

首批简化建议（待用户确认）：正常显式 quit，异常空闲回收交 Appium；本库不增加自动心跳、后台存活探测、自动会话恢复或全量 Session 发现。不确定时提供已知设备/会话标识及明确失败/未知，由调用方核实后再显式创建；暂不承诺崩溃后自动恢复原会话或自动证明设备空闲。进程内已知不确定占用继续保留；跨进程保护范围依然是未决项，不能将此建议默认为放弃原有占用需求。若该限制不能接受，需要先补具体恢复机制，AIF-02 仍不能 Ready。

#### D02-C 正常与异常退出候选规则

- 上层显式创建/`quit` 的需求保持。调用方持有 Session 对象直至确认关闭；如果以后提供 `with`，进入该上下文本身是显式选择自动清理的使用范围，不能把普通 Runtime with 结束解释成 Automation 自动删除会话。是否提供此便利入口另定。
- 正常路径先关闭全部本范围 Session，再退出 Runtime。`quit` 只终止其 Appium 会话；应用是否保持运行按既有 `noReset=true`、`shouldTerminateApp=false` 及官方参数交互核验，不因方法名宣称所有应用永不终止。
- 普通操作响应丢失：沿既有规则报告执行未知，不重放；是否允许后续只读核实，以及如何证明前请求已经结束，交 U07，不直接恢复为可执行状态。
- 创建结果未知：没有 sessionId 不表示未创建。保留设备占用与待核实事实；不凭超时自动重建、重启 Appium 或清理其他 Session。
- `quit` 响应丢失：保留该会话身份与设备占用；不把 Appium 无响应、设备断开或进程退出当作已终止；核实与恢复入口待设计。自动重发 quit 也不在本轮批准范围内。
- external Runtime 的退出仍只释放自身资源，可能发生在遗留会话尚未关闭时；Automation 必须先报告自己的清理结果。不能为了设备保护，擅自改变 Runtime 外部连接退出语义或删除 Appium 上的其他会话。恢复清理若在原连接退出后进行，须重新取得公开连接资格、核对原服务/设备/会话身份，具体可行性待定，不能用裸 URL 绕过。
- 用户业务原异常、Session 清理错误、Runtime 清理错误应分别保留；本条仍为设计建议，字段和捕获规则待确认。

#### D02-D 官方可行性依据与适配缺口

UiAutomator2 [v8.7.0 Parallel Tests](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#parallel-tests) 明确单个 Appium 服务可管理多个 Session；每个并行设备须明确 `udid`、独立 `systemPort` 等适用资源，开启 `--session-override` 会关闭已有 Session。本文只依据其 Native 部分，不引入 chromedriver/WebView 或 MJPEG/录屏范围。

Appium Python Client 固定术语参考提交 [WebDriver](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/webdriver.py) 定义客户端对象和 start_session；这只支持按会话分别持有客户端的设计方向，不能证明客户端可跨线程共用、可取消或兼容本项目锁定环境。线程/端口分配策略、新 Session/quit 的错误与传输重试、是否自动回退到直连地址、超时清理必须在选定版本核验，尚无客户端版本批准。

**当前判断**：正常的“单活跃 Runtime/connection 内多个明确 Session”不要求放宽账号锁，也不需要为 external 服务增加自管 UsageHandle。拟议新增在 Automation：会话归属/准入/设备占用/恢复规则。若最终要求第二 Runtime/第二进程同时进入、连接退出被活动会话阻止或额外公共有效性/使用句柄，才需明确 Runtime delta；本稿不作该变更。

方案比较：正常使用采用 D02-A；“每 Session 一个 Runtime”与当前单活跃范围冲突，当前不采用；“移除账号锁，只靠设备锁”会改变全局契约且不能保护环境修改，当前不采用；“首批只准一个 Session”会降低既有需求，也不采用。D02 正常生命周期已确认，U03-P1、关闭/取消竞态、U06/U07 和实际多 Session 资格验证仍阻塞 AIF-02 Ready。

### 4.3 Element：统一界面目标对象

已确认：操作接收 Element，由它确定目标及操作区域；Element 是本项目的定位描述对象，保存 Appium by/value 定位条件，操作时解析到当前唯一官方元素并获取所需当次几何，不缓存跨调用 elementId。它不是原始观测 JSON 节点或裸 Appium WebElement，跨次重复使用的是定位描述，不是以前找到的设备节点。Element 由所属 Session 创建并绑定，创建时只保存条件及必要纯值校验，不做设备查询；传给其他 Session 时在设备请求前报错，不自动改绑或复制。父容器定位需求沿用；工厂名与可选参数、父关系结构、相对区域表示及正式错误模型尚未全量确认，不能从 by/value 方向确认直接推断具体签名。

下述定位表达是 Element 的候选内容，不要求调用方在每次操作再次传 locator；没有官方同义公开构造时注明为项目薄封装，不自建查询语言或通用解析器。

#### 4.3.1 Element 工厂及字段候选

用户已选择 **Appium by/value** 构造方向；专家此前推荐的关键字工厂未被采用。以下为候选具体签名，尚未实现、未作全参数批准；`Element` 为本项目惰性对象，创建零设备 I/O，不冒充 Appium 立即查询的 find_element。

```python
session.element(by, value, *, parent=None, package=None) -> Element
```

上式仅表示参数清单，不是可执行 Python 定义；下述示例使用调用语法，均未执行。by/value 构造方向及首版 parent+XPath 拒绝已确认；parent其余细节、package精确规则、正式类型/空值/长度限制仍待确认。定位参数不并行增加 resource_id/text/content_desc/xpath 关键字入口。

| 候选参数 | 含义与组合规则建议 | 批准状态 / 依据 |
| --- | --- | --- |
| by | 采用 Appium 公开策略名，如 AppiumBy.ID、ACCESSIBILITY_ID、XPATH；具体允许集合待确认 | by/value 方向已确认；不自造 TEXT/COMPOSITE 策略 |
| value | 与 by 对应的原始定位字符串；ID 对应 resource-id，ACCESSIBILITY_ID 对应 content-desc，XPATH 对应原始 XPath | 原始策略和值表达沿 Appium；短 ID 格式和校验待定，不默默清洗文字 |
| 精确文本与属性组合 | 推荐通过调用方显式给出的 XPath 精确谓词/AND 表达，使用真实 XML 属性名；不要求库自动生成表达式 | 原需求保留；只用 XPath 作为组合通道是待确认方案，不因 by/value 选择默认批准或缩减范围 |
| parent | 可选同 Session 父 Element，先解析唯一父，再执行官方子查询；首版不与子目标 XPATH 组合 | 父容器需求沿用；parent+XPath 拒绝本轮确认，其余参数细节候选，跨 Session 拒绝沿已确认规则 |
| package | 只参与短 resource_id 的项目规范化，缺省沿 Session 目标应用；不能改变 Session 或选应用 | 默认/覆盖需求沿用；无默认包名及与完整 ID 冲突的行为待确认 |

建议 by/value 必填，不将仅 parent、空条件或任意附加 kwargs 当成默认整屏。属性组合的语义仍是明确精确条件；原样 XPath 可表达 and 及调用方显式其他匹配方式，但本库不解析、清洗、重写或自行取第一个。具体支持字段及普通定位/滚动搜索差异仍需版本依据，不在实现时静默丢弃条件。父链如何避免循环/过深、对象是否不可变、关闭 Session 后是否还允许纯值构造仍待设计，不从例子推断默认值。

比较历史：关键字工厂可方便表达常用属性组合，但用户已选择 by/value，不继续作为推荐或新增同义入口。by/value 的 value 可直接承载原样 XPath，无需仅为组合另造 grammar；是否只提供该组合通道须明确取舍。受限 UiSelector 仍是官方滚动等用途的候选适配，而非默认对外开放任意字符串。所有候选字段先写 Interface，不批准自研通用 locator grammar/解析器或额外依赖。

#### 4.3.2 官方查询调用链与父作用域限制

专家核对的公开复用路径：根 `find_elements(by, value)` → `POST /session/{sid}/elements`；父官方元素 `find_elements(by, value)` → `POST /session/{sid}/element/{parentId}/elements`。每层都查询完整匹配集合并检查唯一性，不用 find_element 的第一个匹配冒充唯一；同一操作内使用临时父/子句柄，下一操作重新解析父链。Appium 客户端采用底层公共 WebDriver 查询实现不等于产品命名改为浏览器/Selenium风格。最终所选客户端依赖版本的签名、响应上限及异常仍须核验。

来源：[Appium Client 固定 WebDriver](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/webdriver.py)、[locator_converter](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/locator_converter.py)、专家比较使用的 [Selenium 4.51.0 WebElement 子查询](https://github.com/SeleniumHQ/selenium/blob/selenium-4.51.0/py/selenium/webdriver/remote/webelement.py)与[公开路由](https://github.com/SeleniumHQ/selenium/blob/selenium-4.51.0/py/selenium/webdriver/remote/remote_connection.py)。后两个是独立版本源码参考，不是批准或实际安装的传递版本，不能直接构成兼容组合声明。

**parent + 原样 XPath 首版不支持（本轮已确认）**：UiAutomator2 的 limitXPathContextScope=false 会让部分 XPath 在父查询中访问整页/祖先，不能只凭 `.//` 开头就声称任意表达式被限定在容器。根据用户具体选择，创建子目标 by=XPATH 且 parent 非空时纯值拒绝；根 XPath 继续原样传递，不丢弃父条件进行全页查找。这是对父容器与 XPath 组合的明确首版限制，不使用 grammar 检查或改写 XPath 绕开；未来若扩展须另定官方 context 设置与版本资格验证。父查询还存在 driver 特定 XPath 转换，项目“原样”只保证本库不改写，不承诺上游不做转换。

来源：[v8.7.0 settings](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#settings-api)、[driver find.ts](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/find.ts)、[server v10.6.0 XML 作用域](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/core/AccessibilityNodeInfoDumper.java)。父查找、子查找、状态读取与动作之间没有原子保证；[FindElements](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/handler/FindElements.java)及[ElementsCache](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/model/ElementsCache.java)说明仍可能 stale，不能把项目每次重定位当成永不 stale 的保证。

属性 AND 的公开表达推荐为调用方原样 XPath，通过 AppiumBy.XPATH/value 交上游执行，不新增生成器；该组合通道仍待确认。此前受限 UiSelector 或生成 XPath 的映射保留为比较历史/滚动适配研究，前者有 legacy 弃用风险、后者受 XML 设置/性能影响；如果后续确需生成，字段映射、字符串字面量编码用途及自研范围须先明确批准。不允许任意 UiAutomator 程序串绕过边界，也不解析/改写原始 XPath。[Android UiSelector](https://developer.android.com/reference/androidx/test/uiautomator/UiSelector)、[设备端解析器源码](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/utils/UiSelectorParser.java)仅是能力依据，不作为项目可直接导入的公共 API。

#### 4.3.3 使用示例与待决范围

以下均为未执行的候选签名示例；只展示已绑定 Session 的 Element 作为操作目标，不构成这些方法/字段已批准或已支持的声明。`session` 代表已显式取得的 Session，创建/quit 与 Runtime 范围沿第 4.2 节。

```python
# 创建只保存定位描述；两次动作分别重新定位，不缓存旧节点。
from appium.webdriver.common.appiumby import AppiumBy

save = session.element(AppiumBy.ID, "com.example:id/save")
session.tap(save)
session.tap(save)

# accessibility id 对应精确 content-desc。
submit_by_desc = session.element(AppiumBy.ACCESSIBILITY_ID, "提交订单")
session.tap(submit_by_desc)

# 可选父 Element；parent 具体参数尚待确认。
form = session.element(AppiumBy.ID, "com.example:id/form")
submit = session.element(
    AppiumBy.ID,
    "com.example:id/submit",
    parent=form,
)
session.tap(submit)

# 根 XPath 可表达精确属性 AND；该组合通道为待确认建议。
submit_by_attributes = session.element(
    AppiumBy.XPATH,
    '//*[@resource-id="com.example:id/submit" and @text="提交"'
    ' and @content-desc="提交订单"]',
)
session.tap(submit_by_attributes)

# 读取不要求显示、启用或焦点。
name = session.element(
    AppiumBy.XPATH,
    '//*[@resource-id="com.example:id/name" and @enabled="false"]',
)
session.inspect_element(name, attributes=["text", "enabled"])

# 实际容器元素确定滚动区域，调用方不传绝对坐标或独立矩形。
items = session.element(AppiumBy.ID, "com.example:id/list")
session.scroll_gesture(items, direction="down", percent=0.75)

# 已确认：其他 Session 在任何设备请求前拒绝，不自动改绑。
other_session.tap(items)
```

不从上述例子增加区域 Element 构造器、默认整屏 Element、Element 自带动作方法或外部序列化句柄。这些都尚未决定；当前真实控件 Element 已能表达按钮、输入框与列表容器，几何专用目标继续单列为待决，不假装矩形具有文字/属性/可编辑能力。

#### 4.3.4 parent 的调用规则草案

下述规则除已明确的 Session归属、每次重定位和 parent+XPath 首版拒绝外，其余细节仍为建议待确认；基于两轮专家已读取的官方父子 find_elements 与 XPath 作用域证据，不增加第三套查询框架。

| 环节 | 推荐行为 | 失败/不承诺的事项 |
| --- | --- | --- |
| 创建 `element(by, value, parent=...)` | parent 是同 Session 的项目 Element；保存父描述，不查询是否存在或唯一 | 跨 Session 的父对象在纯值阶段拒绝；不能把创建成功当作父/子已找到 |
| 使用子 Element | 在本次操作准入后，从根开始重新解析整条父链；每层取得完整匹配集并检查数量 | 父不存在沿同一等待预算处理；父或子多匹配报歧义，不取第一个，不分别重置每层15秒 |
| 定位顺序 | 父唯一后通过该临时官方父元素执行子 find_elements；具体操作状态只按已确认的目标前置检查 | 不额外要求父有clickable/focused；父是否还需其他状态按操作/上游支持核验，不把点击规则套满父链 |
| 父范围丢失 | 目标始终在所声明父链下解析 | 不回退到全页/其他同名父；动作发出后失效不自动重放 |
| `parent + ID/ACCESSIBILITY_ID` | 复用官方子元素查询，保留标准策略和值 | 必须验证父/子真实匹配及同名外部控件不被选；不宣称所有 driver/平台相同行为 |
| `parent + XPATH` | 本轮确认首版不支持，创建纯值阶段明确报组合不支持；根 XPath 保留 | 不查询设备、不丢 parent 退回根查找；后续扩展需另定官方 context 设置及范围保证，不凭前缀检查或改写表达式实现 |

“父/子唯一”针对本次定位时的查询范围，不意味着设备节点永久相同。父链纯值约束、防循环/深度、stale只读重试集合与单操作预算的组合仍需设计，不能让恶意父链无限耗时。按本次操作取得的子元素执行动作后不保持跨调用句柄。

#### 4.3.5 ID 与 package：沿用规则与未决边界分开

**已经确认，直接沿用，不重复提问**：resource-id 的 package ID 参数化，短 ID 默认使用 Session 目标应用包名，单次可指定其他包名。原需求稿第 40 行保留该记录；by/value 不改变此规则，不把默认包名交给前台应用猜测，也不删短 ID 能力。

下表只有第三列所列异常边界和自定义 ID 表达仍待收敛，不将整组规则标成未确认。本会话曾将已确认默认/覆盖规则与“无可用包名、冲突时报错”候选混为一组再次询问，用户指出重复；本次修正状态，该反馈不作为异常边界已获批准的证据。技术/API 能回答的事项先核验，必要适配建议集中列明，只为新增产品取舍提问。

| 输入 | 正常规则 / 适配方向 | 仅下列边界待收敛 |
| --- | --- | --- |
| `AppiumBy.ID` + 标准完整 `com.example:id/name` | 原值定位，不再补包名 | 同时指定不同 package 建议报冲突，不静默覆盖 |
| `AppiumBy.ID` + 短值 `name` | 已确认：显式 package 优先，否则使用 Session 目标应用包名 | 仅没有可用包名时的行为待定；建议明确报错，不猜前台app或instrumentation包名 |
| 自定义原样ID（不按标准格式） | 与短ID不能仅靠“没有冒号”猜测；需要明确表达与官方设置核验 | 不先引入 raw_id 新策略或全局改设置；参数/用途待用户取舍 |
| 其他 by 策略 | package 不参与 XPath/accessibility value，不改写定位字符串 | 带无关 package 建议纯值拒绝，避免调用方误以为生效 |

对象的 package 只说明该 Element 的定位值，不切换应用，不重设整个 Session，也不默默传播给不相关 Element。正常默认/覆盖规则已确认；未决异常边界及自定义 ID 表达仍为草案，不批准生成器、范围外客户端用途或安装依赖。

本轮公开定位表达按 by/value 收敛；属性组合推荐通过调用方的原样 XPath 表达，尚待具体确认，不另建关键字AND模型。resource-id 的包名沿 Session 默认应用并允许显式覆盖的需求保持。每次操作重定位，范围内唯一，精简 JSON 短名转换由 Automation 统一维护，不当 XPath 属性名。

已确认本版公开操作只用 `[0,1]` 相对坐标，以本次操作时设备当前显示区域为统一基准，不提供绝对像素模式或容器局部坐标。Element 如何表达相对区域、区域对象是否与可执行控件对象同类、哪些方法允许区域目标尚未确认；不能把相对矩形当作已定位的可编辑控件。调用方观测所得节点不是自动有效的操作对象；官方元素只在单次操作内部解析使用，公开操作目标为项目 Element。

#### 定位到 Appium 的映射草案

本表细化已有需求，不是新增 locator 语法或已批准类型签名；Appium 名称来自 [AppiumBy 固定提交](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/common/appiumby.py)，Native 策略事实来自 [UiAutomator2 v8.7.0 Element Location](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#element-location)。

| 调用意图 | 对外输入草案 | Appium 映射与尚待核验项 |
| --- | --- | --- |
| 按 resource-id | 完整 ID，或短 ID 加显式/Session 默认包名 | 官方 ID 定位；本项目包名规范化不得被 driver 当前前台应用静默改变 |
| 按 content-desc | 完整原文 | Appium ACCESSIBILITY_ID 精确匹配，不做文本清洗 |
| 按文本/多个属性组合 | 建议 `by=AppiumBy.XPATH`，value为调用方显式精确条件及AND表达式 | 不新造TEXT策略，不自动生成或改写XPath；该组合入口建议待确认，不悄悄删除原组合需求 |
| 原样 XPath | 原始 XPath 字符串 | Appium XPATH；不解析、重写或把短字段名当 XML 属性名 |
| 限定父容器 | 父定位条件加子目标条件 | 同次操作内先定位唯一父容器，再在其范围执行官方查询；子 XPath 的相对/绝对语义须明确，不能悄悄改写 |
| 相对坐标 | 本次操作时设备当前显示区域基准的归一化位置 | Automation 内部转换为官方触摸坐标；不接受绝对像素；不是元素定位，也不保证命中唯一控件 |

普通操作接受定位纯值并在调用时重新查询；先 observe 再操作不绑定旧节点。公开 Interface 不要求调用方保存 Appium 元素 ID。原生 `-android uiautomator` 不能只因 Appium 支持就作为任意公开原始表达式入口，因为可携带滚动等行为；若仅为适配已批准官方能力内部使用，需要明确受限用途与选型批准。

包名适配注意：[server v10.6.0 ElementLocationHelpers](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/utils/ElementLocationHelpers.java)的短 ID 自动补全依据上游 appPackage，并可能回退 instrumentation 包名，不能冒充本项目明确的 Session 默认应用规则。标准完整 ID 与特殊/自定义原样 ID 应如何区分、无默认包名时短 ID 的错误、disableIdLocatorAutocompletion 的必要设置及实际影响仍须确认；不因“自动补全”省略这些合同，也不静默改写自定义 ID。

`mobile: scroll` 是独立受限接缝：v8.7.0 文档要求其 elementId 对应可滚动容器且由 `-android uiautomator` 定位；目标策略只列 accessibility id、class name、-android uiautomator。普通属性组合和任意 XPath 不可自动承诺可用于滚动查找。容器与目标不兼容时先报告能力缺口，不在 Integrations 写循环补齐。UiSelector 上游弃用提示也须纳入后续版本/适配评估，不靠本稿引用批准自研替代。

## 5. 执行控制与完成/失败语义

本节定义公共调用的执行边界，不引入 evidence 字段。**本轮已确认异常式公共接口**：成功直接返回语义值，受控失败抛 Automation 异常；具体预算/取消和生命周期恢复仍按下文状态收敛。

| 需要分开的事实 | 设计要求 | 确认状态 |
| --- | --- | --- |
| 调用完成 / 执行失败 / 取消或超时 | 普通错误、取消/中断与未知程序缺陷不宽泛混为同类；成功值与失败异常分开 | 异常式公共接口本轮确认；预算/取消细节待下文确认 |
| 设备命令未发送 / 有已完成步骤 / 命令完成 / 执行未知 | `request_state` 与 `completed_steps` 分开表达；响应丢失不能断言未执行，不自动重放 | 本轮确认；可可靠分类的实际上游异常仍待版本资格验证 |
| 命令完成 / 状态核对 / 预期条件 / 业务目标 | 单动作成功沿原稿只保证有效命令响应；观测不自动升级保证 | 沿用并本轮确认 |
| 条件等待 / 响应预算 / 操作总预算 / 清理 / 空闲超时 | 四层分别定义；取消采用检查点语义，命令阻塞期间不提前返回或释放准入 | 等待、500秒空闲及检查点取消已确认；操作分类默认总预算待确认，响应边界待版本资格验证 |
| 主错误 / 清理错误 | `cleanup_errors` 按顺序保留，不覆盖主错误；无主错误时必要清理失败使操作失败 | 本轮确认；实际清理错误类型待版本资格验证 |
| 同 Session 并发 | 操作重叠时，后来调用在发送其设备命令前立即报忙；不等待执行槽位、不隐式排队、不打断前一操作 | 本轮确认；只限制同一 Session，不证明不同设备并行可用；关闭/取消竞态待设计 |

“未知”不是保证未执行，“部分完成”不是事务回滚承诺。是否可重试需要结合具体操作和已知状态；不照搬别库 `retry_safe` 布尔值，不用一个通用“可重试”驱动自动重放。超时不能自动解锁仍在执行的设备资源，取消后如何结束上游请求必须有官方和实际版本依据；无法兑现硬返回预算时应如实设计限制。

受控错误采用第 5.0 节已确认模型；未知程序缺陷不伪装为稳定 Automation 错误。稳定 code 的具体上游映射、预算/取消和生命周期恢复仍须按锁定版本核验。

### 5.0 公共错误模型（本轮确认）

采用“**成功返回意图本身的值，失败抛稳定 Automation 异常**”，不让每个方法都返回通用 `ActionResult` 包装。读取方法直接返回其不可变值，命令无业务返回时返回 `None`，官方有稳定语义的布尔/状态值原样进入项目类型；仅失败路径携带执行事实。直接 Python 调用和未来 Integrations 复用同一失败语义，Adapter 只做协议映射，不自行推断设备状态。

最小异常层级由 Automation 拥有，不放入 Contracts，也不继承 Runtime 的 `partial_report` 结构：

| 类型方向 | 适用范围 | 必须携带 / 不承诺 |
| --- | --- | --- |
| `AutomationError` | 所有受控公共失败的根类型 | 稳定 `code`；人类消息不是机器协议，未知程序缺陷不包成此类型 |
| `InvalidRequestError` | 纯值、参数组合、跨 Session Element、首版不支持的 parent+XPath 等在设备请求前可判定的问题 | `request_state=not_sent`；创建纯值对象没有 operation_id 时不得伪造一个操作 |
| `InvalidSessionStateError` / `SessionBusyError` | Session 未 active、已关闭/失效/状态未知，或同 Session 重叠调用 | 忙保证后来调用未发送其设备命令；状态未知不自动恢复为 active |
| `TargetError` | 目标缺失、歧义、前置条件无法满足或属性无法判定 | 用稳定 code 区分 not_found/ambiguous/precondition/unknown；不取第一个、不把读取失败当不存在 |
| `OperationTimeoutError` / `OperationCancelledError` | 操作总预算耗尽或调用方请求取消 | 已确认检查点取消；取消请求与实际上游停止分开，必要收尾结束前不释放 Session 准入 |
| `CommandError` | 收到有效上游失败响应，或项目能可靠分类的明确协议/命令失败 | 保留稳定项目 code 和原始异常链；不能由“收到错误”推断设备绝无副作用 |
| `ExecutionUnknownError` | 状态改变请求可能已发送但没有可验证终态响应，或无法证明上游已结束 | 明确禁止自动重放；上层只能基于后续显式核实决定下一步 |
| `ResourceStateError` | 设备占用、Session 创建/关闭及必要清理失败 | 不能因本地锁释放或 Appium sessionId 不可见就宣称设备端已清理 |

受控操作异常统一携带 `operation_id`、稳定 `code`、`request_state`、`completed_steps` 和 `cleanup_errors`：

- `request_state` 只取 `not_sent`、`response_received`、`response_unknown`。`not_sent` 仅用于本库能证明本次待执行设备请求尚未发出的情况；连接库无法证明请求字节是否送达时必须用 `response_unknown`。`response_received` 只说明取得有效终态响应，不把失败响应解释为“无副作用”。
- `completed_steps` 是有序稳定步骤名，只列已由成功响应或其他明确状态确认完成的 Automation 组合步骤。例如 `clear_app` 可在 clear 失败时列出 `state_checked`、`app_terminated`；它不是日志、evidence 或事务补偿记录。
- `cleanup_errors` 是按发生顺序保存的原始清理异常 tuple。主错误对象和稳定 code 保持，不被清理错误覆盖；没有主错误而必要清理失败时，以 ResourceStateError 使操作失败。底层原始异常通过异常链保留，不把任意 `repr` 写入稳定字段。
- 不提供通用 `retryable` 标志。是否可再次调用取决于具体操作、`request_state`、已完成步骤和显式核实结果；任何接入不得仅按异常类自动重放。

稳定 code 至少覆盖：`invalid_argument`、`unsupported_operation`、`session_invalid`、`session_closed`、`session_busy`、`target_not_found`、`target_ambiguous`、`precondition_not_met`、`condition_timeout`、`operation_timeout`、`operation_cancelled`、`command_failed`、`execution_unknown`、`device_busy`、`session_create_unknown`、`session_quit_unknown`、`cleanup_failed`。最终按实际可可靠分类的上游异常收敛，不能为凑表宽泛猜测；Appium/Selenium 原始类名不直接成为稳定跨版本 code。

#### 5.0.1 预算与取消模型（本轮确认；响应实现待资格验证）

时间语义分为四层，禁止用同一个 `timeout` 名称混淆：

| 层级 | 作用与起止 | 到期结果 / 与其他层关系 |
| --- | --- | --- |
| 目标等待 `wait_timeout_seconds` | 只覆盖首次至条件满足前的只读重定位/状态轮询；默认15秒，保留5/15/60及有限正数 | 先于操作总预算耗尽则 `condition_timeout`；不限制随后动作响应，不重置总预算 |
| 操作总预算 `OperationControl.timeout_seconds` | 仅调用方显式传入时存在；从公共方法通过纯值校验、准备取得 Session 准入前开始，到业务步骤停止并进入必要收尾；使用单调时钟 | 到期后不启动新定位、动作或补偿步骤；抛 `operation_timeout`。它是停止业务推进的 deadline，不承诺不可中断清理已在同一时刻完成 |
| 单次上游响应处理 | `control=None` 时沿锁定 Appium Python Client / Selenium / Appium 命令本身的默认处理，Automation 不附加统一响应时限；显式 Control 时，尝试将每个请求限制在操作剩余预算内，具体能力须资格验证 | 默认可能无有限上限；响应丢失或传输超时按请求是否可能发送映射 `response_unknown`，不得自动重发。应用管理已确认不公开各自上游 timeout |
| Session 空闲回收 | `appium:newCommandTimeout=500`，由 Appium 在命令间空闲时计时 | 与以上三层无包含关系；不是命令时限、操作预算或客户端取消机制 |

Automation **复用现有公开 `runtime.OperationControl` 的 `timeout_seconds` 与 `threading.Event` cancellation 形态**，不再造第二个同义控制类型；Automation 只解释自己的操作结果，不复用 Runtime 的报告异常。**本轮已确认 `control=None` 默认沿 Appium 处理，不设置 Automation 操作总预算，并接受所选官方客户端默认可能没有有限响应上限。** 目标等待自己的15秒默认仍有效，但它不会中止已经发送的命令。调用方需要有界调用时显式传 `OperationControl`；`OperationControl()` 的10秒就是明确总预算，必要等待由剩余预算截断。

取消采用检查点语义：开始前、每轮等待、每个组合步骤前、每个上游响应后及进入/退出收尾时检查 Event。取消后不发送新的设备命令、不自动 `quit`、回滚或重放；已知完成步骤仍写入 `completed_steps`。若取消在状态改变请求阻塞期间到来，只有在该请求结束或传输层可靠中止并完成资源收尾后才释放同 Session 准入；不能让后来调用与仍运行的前请求重叠。

固定研究事实限定首版可承诺范围：所查 Appium Python Client 只扩展 Selenium 同步 `RemoteConnection`；Selenium 4.51.0 `ClientConfig.timeout` 为连接请求 timeout，`RemoteConnection.execute` 同步阻塞在 urllib3 请求，公开接口没有按命令取消原语，`close()` 只清连接池。**本轮已确认检查点取消**：等待/步骤间及时取消；单个阻塞命令受资格验证后的响应上限约束，取消期间仍等待该请求终止和必要收尾，不能让后来调用与仍运行的前请求重叠。首版不声称 Event 会立即抢占任意正在执行的 Appium 命令，不把同步请求遗留在线程中提前返回或释放准入。未来若要求命令中即时返回，须重新选型或批准不同传输/隔离机制，不能在 Integrations 伪造。

预算竞争优先级：在发送前同时发现取消与deadline到期，取消优先；已有有效上游失败响应保持该命令失败为主，随后发生的取消/超时不覆盖它；无终态响应时，根据最先可证明的调用方取消或deadline分别抛 cancelled/timeout，但 `request_state=response_unknown` 仍保留可能已执行事实。必要清理错误按已确认 `cleanup_errors` 追加，不改变主错误对象。

本轮不采用按操作分类的10/30/120秒隐式默认，也不强制每次传 Control。该产品决定不等于已证明上游默认安全：锁定 Appium Python Client/Selenium/driver 版本前，必须验证其默认请求行为、显式 timeout 映射、慢连接/慢响应及清理；若实际版本无法在显式 Control 下提供所需有界行为，AIF-02及相关操作仍不 Ready，不能以“Appium 默认”掩盖阻塞。

#### 5.0.2 Session 生命周期与恢复（本轮确认；Runtime竞态待接缝核验）

首批不把 Session 简化为 active/closed 两态。公开 `session_info` 返回本地不可变快照，至少区分 `creating`、`active`、`uncertain`、`closing`、`closed`；`busy` 是 active 上的一次操作准入状态，不作为另一个可复用 Session。快照含本库 Session 身份、Appium sessionId（仅已知时）、设备身份、目标包和最后已知状态；不做后台健康轮询，不把历史 active 冒充持续健康。

| 状态 / 事件 | Automation 行为 | 设备占用与可继续动作 |
| --- | --- | --- |
| create 准备 | 在任何可能创建 Session 的请求前取得同设备占用，校验 active Runtime connection、设备/资源参数和已确认 capabilities | 校验或可证明未发送的失败释放占用；不同设备不受此占用限制 |
| create 成功 | 只有收到有效创建响应、sessionId和所需协商事实才返回 Session；客户端保持该会话独立资源 | 转 active；`appium:newCommandTimeout=500` 已进入 capabilities；不自动启动目标应用 |
| create 响应未知 | 不猜“没有创建”，不自动重发；异常含 device、operation_id及已知身份 | 转 uncertain并保留本进程设备占用；无sessionId时不得猜ID、attach或枚举认领其他会话 |
| active 操作 | 每次先核对 connection仍active并取得非阻塞Session准入；同Session后来调用立即忙 | 有效响应后恢复active；状态改变命令响应未知时转uncertain，禁止普通后续命令和自动重放 |
| 正常 `quit()` | active且不busy才发一次Appium DELETE；进入closing后拒绝其他操作 | 只有有效成功响应且客户端必要收尾完成才closed并释放设备；closed再次quit为空操作成功的幂等便利 |
| quit失败/响应未知 | 不以本地连接关闭、Appium sessionId不可见或500秒经过推断清理完成 | 转uncertain，保留已知身份和本进程设备占用；不自动再次DELETE、重建或释放 |
| Runtime connection退出/失效 | 正常契约要求所有Session先quit；退出后任何新Automation操作在设备请求前拒绝，不用缓存URL继续 | 当前Runtime不知道Automation Session，无法从现有接口强制退出顺序；并发退出属于待接缝解决的竞态，必要时另提Runtime delta |

恢复遵循“核实而非重放”。首批不 attach 外部 Session、不后台探活、不自动开启 `session_discovery`、不自动心跳，也不以 `GET /appium/sessions` 空列表证明设备资源清理。固定 Appium 3.0.0 源码显示，`GET /appium/sessions` 需启用不安全特性 `session_discovery`；DELETE 会在等待实际 driver `deleteSession` 前先从 master list 移除条目。因此 sessionId 不可见只说明该服务不再接受该ID，不能单独解除设备占用。500秒 newCommandTimeout 在命令完成后计时并触发 unexpected shutdown，是回收机制而非本地清理证明。

同进程可达恢复规则已确认：uncertain Session 只允许读取本地 `session_info`，不再执行普通设备命令。普通查询也可能重置500秒或与未知命令重叠，首批不把“发一个只读命令试试”作为自动恢复。已知 sessionId 的显式再次quit也可能只得到“session不存在”，仍不能证明driver清理完成，故不承诺为通用恢复。调用方停止后续设备操作并对外报告需人工核实；Automation不清理其他客户端Session或重启外部Appium。

**本轮已确认进程边界**：同设备占用保证限于当前 Automation 宿主进程。进程正常存活时，creating、active、closing、uncertain 均保留占用，只有可证明未创建或确认成功关闭并完成本地收尾才释放。进程崩溃后本地保证终止；依赖Appium 500秒空闲回收，但新进程必须明确知道无法证明旧资源已清理。本库不写持久账本，不宣称跨进程Session互斥、自动恢复或自动证明设备空闲。

未采用方案保留为比较历史：跨进程持久记录会新增状态权限、损坏、崩溃窗口和人工解除契约；强制 `session_discovery` 会扩大服务配置与会话可见范围，且条目消失仍不证明driver清理。二者未来若需要必须重新设计，不从当前进程内保证增量实现。

无论选择哪种范围，Appium Python Client 新Session请求的 idempotency key 只能减少同一请求重复处理风险，不提供创建响应丢失后的Session身份恢复，也不批准自动重试。客户端 `direct_connection` 默认保持关闭，避免创建响应让每个Session悄悄切换到未经Runtime验证的其他端点；若未来需要须单独走连接边界设计。

### 5.1 定位、等待与基本操作的详细契约草案

本节落实 IF-06/08/10–15 的行为，新增参数形态、前置规则及映射除单项已确认外均是**建议待确认**。直接 Python 使用本项目 Session 对象，不返回底层客户端/元素对象；方法名参考 Appium，但目标参数和返回形式为本项目封装，不声称与原客户端签名兼容。

本轮 Element 修订后，下表旧 `locator` 草参统一改由 `element` 目标对象提供，其定位和父容器信息不在操作中重复传。已确认由该对象保存定位描述并在每次操作重新解析。Session 负责创建并绑定 Element，创建不查询设备；所有接受 Element 的调用在定位/属性读取/坐标采样等设备请求前验证所属 Session。公开 Element 与内部官方 WebElement 分开，不返回底层句柄供跨次调用；重复传入相同 Element 不表示复用以前解析的节点。工厂名称和具体参数仍待定，不提前发布与 Appium 立即查询同名却行为不同的入口。

#### 5.1.1 共用输入与执行过程

| 输入/阶段 | 推荐语义 | 当前状态 |
| --- | --- | --- |
| `element` | 所属 Session 创建并绑定的定位描述对象；创建不查询设备，操作时重新定位获取区域；跨 Session 在设备请求前报错，不缓存底层句柄 | 创建归属、定位描述和每次重定位已确认；工厂名/定位参数/父关系/相对区域构造及错误模型待定 |
| `wait_timeout_seconds` | 仅覆盖目标与必要条件等待；缺省 15 秒，可用 5/15/60 档或具体有限正数；不把此值当 HTTP/命令响应期限 | 时长沿用，字段/纯值校验细节待确认；本轮不增加 0 秒快捷模式 |
| `control` | 操作总预算/取消输入；响应预算另与所选客户端能力核对 | 尚未确认模型、默认值或硬返回时限 |
| 动作特有参数 | 文本 `text: str`；长按可选 `duration` 毫秒；双击不暴露官方没有的间隔参数 | 参数形态建议；官方时长与边界见下表 |
| 纯值校验 | 先检查互斥/必填、预算、文本特殊尾缀；纯值拒绝不向设备发送请求 | 特殊尾缀拒绝已确认；其他验证属于必要适配，具体规则待核验 |
| 操作准入 | 明确 Session/连接有效，取得同 Session 非阻塞准入；重叠调用立即报忙 | 报忙规则已确认，连接退出竞态与字段待设计 |
| 条件等待 | 同一操作预算内重定位父/子，唯一性检查及本操作所需状态读取；等待中不发送触摸/写入命令 | 行为沿用；0匹配或暂未满足条件可继续，歧义建议立即失败，不等页面自行消歧 |
| 执行动作 | 条件满足后，使用此次解析的官方元素发送一个相应上游动作请求；相对坐标路径另明确几何转换 | 一次执行沿用；“一次请求”不保证 driver 内部只有一个设备步骤 |
| 返回与清理 | 记录本次可证明完成程度；上游请求与必要收尾结束后释放准入；不追加页面变化等待、字段回读或业务推断 | 基本成功语义沿用，正式结果/异常模型待 D04 |

定位/状态检查后元素仍可能改变；不保证检查与执行原子。stale、响应丢失或失败发生在动作发送后时，不自动重定位重放。只读定位阶段哪些官方错误可轮询重试，须在实际客户端错误类型与版本核验后限定，不能捕获一切异常当成“再等一下”。隐式等待、UiAutomator waitForIdle/Selector 与客户端响应预算会影响真实耗时，必须资格验证，不能仅设置本库 15 秒就宣称端到端 15 秒返回。

#### 5.1.2 各操作的输入、前置及官方映射

| 对外操作草案 | 动作特有输入 | 推荐前置与 Automation 步骤 | 对应官方入口 / 不承诺的结果 |
| --- | --- | --- | --- |
| `tap(element, ...)` | 无；相对坐标使用明确变体，后续确认 | 已确认：重定位唯一目标，等待 displayed=true、enabled=true，然后执行一次；不要求 clickable=true，不自动滚动/处理弹窗 | Appium WebElement.click / UiAutomator2 click；不证明未遮挡、事件确实到达或页面变化；不在失败后自动换 clickGesture 再点一次 |
| `double_click_gesture(element, ...)` | 无双击间隔/次数参数 | 已确认：重定位唯一目标，等待 displayed/enabled，调用一次；不自动滚动/处理弹窗 | mobile: doubleClickGesture；官方时序由 driver 承担，不用两次 tap 组装；不证明菜单/缩放等业务效果 |
| `long_click_gesture(element, duration?, ...)` | duration：毫秒，未提供沿官方默认 500；所核官方接受非负值，其他上限不凭空增加 | 已确认：唯一目标与 displayed/enabled后执行一次；不自动滚动/处理弹窗 | mobile: longClickGesture；不自行设默认 2秒、不承诺长按菜单出现；0 的实际效果及目标版本边界须验证 |
| `send_keys(element, text, ...)` | text 字符串；字面反斜线+n结尾拒绝；不暴露自动清空/submit 参数 | 已确认：唯一元素、displayed/enabled 后执行一次，不要求预先 focused，不额外点击/滚动/隐藏键盘/clear，不增加editable识别或class白名单；不调用当前焦点 mobile:type | Appium WebElement.send_keys；保留原有内容的官方行为，不证明光标位置、真实逐键事件、Unicode全量组合或精确回读；误选控件可能设为其他值 |
| `clear(element, ...)` | 无 text 参数 | 已确认：唯一元素、displayed/enabled 后执行一次，不要求预先 focused，不额外点击/滚动/隐藏键盘，不增加editable识别或class白名单 | Appium WebElement.clear；无隐式补退格/剪贴板回退，不将命令成功冒充读回空串或目标类型已验证 |
| `replace_element_value(element, text, ...)` | text 字符串，空串建议允许以表达官方替换为空；特殊结尾拒绝 | 已确认：唯一元素、displayed/enabled 后执行一次，不要求预先 focused，不额外点击/滚动/隐藏键盘；向同一解析元素发 replace，不先单独 clear，不用变化后的文字重找目标，不增加editable识别或class白名单 | mobile: replaceElementValue；上游失败可能已部分写入，误选控件可能设为其他值；不自动拆成 clear+send，不做自动回滚 |
| `inspect_element(element, attributes, ...)` | 明确属性列表，默认列表待定 | 已确认：只要求唯一匹配，不要求 displayed/enabled/focused=true；读取请求属性，不通过点击/滚动等先改变状态 | 官方 text/get_attribute/rect 等公开读取；失败/未知/缺失/不适用分开，不返回元素句柄；不保证隐藏节点一定能被driver发现 |

上述 displayed/enabled 对点击/双击/长按和输入/清空/替换是已确认产品准入条件；属性读取已明确只要求唯一匹配，不要求这些状态，也不要求已有焦点。它们不是 Appium 保证完整可操作性或可编辑性的证据，不借浏览器 actionability 承诺 Android 遮挡/动画稳定检测。非编辑控件在所核 UiAutomator2 server 还能有其他 set value 语义（如进度）；本项目文本操作只限文本调用意图，不意味着底层强制识别为输入框。已选择不自研可编辑性识别或固定 className 白名单，不自行限制密码/不可回读字段；官方对这些字段的实际支持和错误仍须按最终版本核验。

**等待条件集合草案**：先评估 present、displayed、enabled、focused，以及所需 text/attribute 精确值；统一条件类型和独立 check_condition 是否公开待确认。not_present 必须在本次可完成的有效查询范围内无匹配，查询失败/范围不完整不等于不存在；多匹配的属性检查不能随便取第一个。等待不自动执行键盘/滚动/弹窗处置；可用的前置条件和错误分别验证。

**文本可编辑性研究与取舍（2026-10-23，方向 A 已确认；版本适配待核验）**：UiAutomator2 [v8.7.0 Element Attributes](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#element-attributes)没有列出通用 editable 属性；已研究设备端 [v10.6.0 Attribute.java](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/utils/Attribute.java)也未暴露同名属性。focusable/focused/className 均不能直接当作 editable：可聚焦不等于可写文字，固定 EditText 白名单又不能代表自定义/Compose 目标的完整能力。input-type、multiline、max-text-length、actions 等作为研究比较线索保留，不新增强制检查，不因文档列出就断言所有查询路径都可可靠返回；未知不能自动当 false。

设备端 [SendKeysToElement](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/handler/SendKeysToElement.java)会先检查是否可设置进度；若可则将文字解析为数值并 setProgress，否则进入文本设置。[ElementHelpers](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/utils/ElementHelpers.java)的普通文本路径使用 Android ACTION_SET_TEXT；driver 返回成功只代表该命令路径完成，不等于回读文字吻合、目标一定被认定为文本字段或未被 max length 截断。clear 的底层也依赖具体元素实现，不能从命令名推断有一致的编辑性校验。研究标签尚非本项目精确锁定组合。

采用方向 A（本轮确认）：只执行已确认的唯一/displayed/enabled 前置，不加自研 editable 识别/类名白名单，调用方明确选择文本目标后直接交官方元素命令；公开契约声明这不是“仅文本输入框可执行”的强类型保证，误选其他官方支持 set value 的控件可能改变其值，不承诺必报错，也不静默新增为 slider 功能。方向 B（比较历史，未采用）：必须在发送前证明为文本可编辑目标，证据不足拒绝操作，可能限制自定义控件。本项目“文本意图”只限制公开操作意图，不伪造底层强制识别保证；协议/解析器/识别器仍不得未经选型批准自研。

#### 5.1.3 版本化实现依据与关键缺口

研究日期 2026-10-23。UiAutomator2 [v8.7.0 gestures 文档](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/docs/android-mobile-gestures.md)及[execute-method-map](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/execute-method-map.ts)确认 doubleClickGesture(elementId/x/y)、longClickGesture(elementId/x/y/duration)，映射表没有文档所提 locator 参数，**不能凭文档宣称该额外参数可用**；项目当前只采用单次解析出的 elementId 或已批准坐标转换路径，不扩展原始动态 locator 参数。该标签的[gestures 实现](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/gestures.ts)代理到官方设备端手势入口。

文本入口：[v8.7.0 element.ts](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/element.ts)中 click、clear 分别发送对应元素命令，mobileReplaceElementValue 向同一 /value 发送 replace=true；[Appium Python Client 固定 webelement.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/webelement.py)公开 clear、send_keys，后者发送文字和值数组。这里使用其名称不意味着改为 Selenium 浏览器封装。

该 driver [package.json](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/package.json)只声明 appium-android-driver ^14.0.8、appium-uiautomator2-server ^10.6.0，未固定传递实际版本；下列是**独立标签研究，非已验证运行组合**。Android driver [v14.0.8 setValue](https://github.com/appium/appium-android-driver/blob/v14.0.8/lib/commands/element.ts)以 replace=false 转入 doSetElementValue；设备端 [server v10.6.0 SendKeysToElement](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/handler/SendKeysToElement.java)在 replace=false 时可能读取原文字、内部 clear 后 setText；replace=true 也会进入同一个文本设置过程。因此原需求“不隐式清空”只能准确保持为 **本库不额外发送 clear，不主动要求替换，沿官方普通输入语义**，不能扩张为 driver 内部绝不 clear、绝不移动焦点或绝不引起界面事件。

同一设备端标签会将文本末尾的字面反斜线+n识别为 Enter；该特殊结尾已由用户明确批准拒绝。真实 LF/CR、空串、emoji/组合字符、长文本/输入长度上限、hint/密码字段、底层行为差异及输入超时后的实际内容仍需按最终客户端/driver/server 精确组合核验；不因单个源码片段就宣布全部文字支持。普通文本后不得由 Adapter 拼 Enter；明确提交意图走已批准 IME/按键操作。

#### 5.1.4 行为验收入口（待实施，不是已运行结果）

- 唯一性：0匹配到出现、父/子歧义、状态从未就绪到满足、定位阶段 stale 与发送后 stale 分开；歧义立即失败的规则需确认。
- 一次执行：双击/长按各仅一个官方手势请求，失去响应时不自动发第二次；检查和定位可以多次，不把请求次数偷换为设备内部步骤数。
- 文本：input/clear/replace 三种意图独立；替换不先 clear；目标文字变化不导致定位到别的控件；特殊尾缀在任何设备请求前拒绝；空串/真实换行及上游内部 clear 的语义如实验证。
- 完成保证：收到有效命令成功响应可报命令完成；不自动读回或等页面；失败不伪造未发送，读取/写入/清理错误不宽泛吞掉。
- 预算：5/15/60 等待、响应超时、操作取消、500秒Session空闲分别测试；取消/超时后只有上游结束及必要收尾完成才释放同 Session 准入。
- 真实验证：专用测试应用与明确设备授权后覆盖普通/自定义输入、键盘布局变化、失效与错误；本轮没有设备授权，不执行这些动作。

### 5.2 已选手势的详细契约草案

本节只展开已选 A8/A9/A10/A12，不新增 fling、缩放、任意多点轨迹或原始 W3C Actions 公共入口。目标输入已修订为 Element 对象，由它确定区域；旧表容器/区域的并列形态不再是公开接口方案。其余名称、参数形态、前置和返回模型为建议待确认；不把点击类 displayed/enabled 规则自动套用到所有手势。研究依据是 [UiAutomator2 v8.7.0 手势文档](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/docs/android-mobile-gestures.md)、[gestures.ts](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/gestures.ts)及[mobile: scroll](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#mobile-scroll)，尚未进行实际组合资格验证。

#### 5.2.1 四个意图与官方入口

| 已选意图 / 名称方向 | 调用方主要输入草案 | Automation 内部过程 | 命令完成及适配限制 |
| --- | --- | --- | --- |
| 单次起终点滑动 `swipe`；区域方向滑动 `swipe_gesture` 为不同官方表达，近期公共形态待取舍 | 起终点相对位置与 duration，或互斥的目标/区域、direction、percent、可选 speed | 按明确变体解析目标/区域并转换坐标；选择对应 Appium 官方 swipe 或 mobile: swipeGesture，一次请求，不失败后换另一种重试 | 两种官方入口参数不相同，不用统一模糊 distance/duration 猜转换；方向和路径语义逐变体明确，不因保留比较而批准两个独立方法 |
| 单次滚动 `scroll_gesture`（对应 IF-17 原 scroll 意图） | 明确容器定位或相对区域、direction、percent、可选 speed、等待/Control | 容器在本次操作重定位，或将区域转换成官方几何；调用一次 mobile: scrollGesture | 保留官方 canScrollMore 布尔结果及限定含义；false 不等于页面业务完整，也不触发自动继续滚动 |
| 滚动查找 `scroll`（对应 IF-18 原 scroll_find 意图） | 明确容器、受支持的 strategy/selector、可选 max_swipes、等待/Control | 解析合适的官方容器元素，调用 mobile: scroll；需要后续操作目标时按已批准的普通定位再次唯一解析，不将搜索结果当长期句柄 | 官方搜索可能先回容器起点再逐步搜索，方向由官方自动检测；不暴露无对应保证的 direction/speed，不承诺任意 XPath/属性组合 |
| 拖动 `drag_and_drop`；mobile: dragGesture 作为实际能力备选映射 | 明确源、目的控件或相对位置，官方适用 pause/speed/时长参数由选定入口决定 | 解析源和目的几何或元素，调用官方 drag_and_drop 或 dragGesture；不自研触摸时序，不混用 pause秒、duration毫秒、speed像素每秒 | Python helper 是元素到元素，dragGesture 是元素/点到坐标；能力不同，选定映射前不宣称任意混合组合都支持，也不把动作完成当业务放置成功 |

命名取舍建议：移动区域滚动采用 Appium `scrollGesture` 对应的 scroll_gesture；官方滚动查找采用 mobile: scroll 对应的 scroll；这样避免将 Appium Python helper 的“元素到元素 scroll”与本项目滚动容器意图混用。此建议尚未确认，接口总表 IF-17/18 的旧草名保留为意图索引，不同时发布别名或自行扩大支持。

**Element 与滚动查找的兼容矩阵（专家核验，适配仍待批准）**：

| Element/目标类型 | 普通单控件动作 | mobile: scroll 滚动查找 |
| --- | --- | --- |
| 明确 resource-id/text/content-desc 属性条件 | 经批准映射后可查询，必须唯一 | 容器需映射为官方 UiAutomator 可滚动对象；目标需官方允许策略，不能以普通查询可用推断搜索必可用 |
| 原样 XPath | 根XPath查询保留；子目标XPATH且parent非空首版纯值拒绝。根XPath创建的父Element配ID/accessibility子查询不被本条一并禁止，实际支持仍须资格验证 | 不承诺可作为滚动搜索容器或目标；不转换/解析任意 XPath 补齐 |
| 有父链的 Element | 操作时逐级唯一查询 | 独立父链未必能无损转成官方 scroll 的容器/目标条件；不能映射时明确报不支持，不能丢 parent 扩大范围 |
| 相对几何目标 | 构造/允许动作未确认，不是已经定位的控件 | 无法凭矩形构造官方 UiScrollable 容器，不作为默认搜索回退 |

固定设备端 [ScrollTo](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/handler/gestures/ScrollTo.java)要求容器可转换为 UiScrollable 的 UiObject；[Device](https://github.com/appium/appium-uiautomator2-server/blob/v10.6.0/app/src/main/java/io/appium/uiautomator2/utils/Device.java)使用官方 scrollIntoView。成功仅表示搜索命令完成，不返回目标句柄，也不证明目标唯一；随后实际操作依然对目标 Element 重新唯一定位。不得由 Integrations 拼滚动循环补齐，也不得在范围不兼容时静默转为全屏搜索。

#### 5.2.2 参数和范围不能混用

- 官方 swipeGesture 的 percent 为区域尺寸比例，范围 0..1；scrollGesture 的 percent 大于 0，可大于 1。**相对坐标 [0,1] 约束不等于滚动行程比例必须小于等于 1**。不把官方可接受值擅自截断到另一种手势范围。
- 官方 speed 是像素每秒，不是持续时间；swipeGesture/scrollGesture 文档默认 5000 × displayDensity，dragGesture 默认 2500 × displayDensity。是否公开 speed、以何单位展示须确认；未给时优先保留官方默认，不根据模型猜测速度或承诺固定移动时长。
- 源码注释曾将 percent 描述成 0–100，而固定同标签使用文档明确为比例且给出 0.75/1.0/3.0 示例；不得按注释乘除100。实际传递与设备端校验边界须资格验证，当前不声称本库已接入。
- 对外统一传 Element，不同时接收容器和区域两套参数。内部将当次 Element 转换为官方元素/区域参数，避免同时发两者后依赖上游静默取优先项。相对区域 Element 的表示及整屏目标构造未确认，不在本文自行增加默认整屏操作。
- 相对点/区域的基准已确认统一为**本次操作时的 Android 当前显示区域**，由 Automation 转换为官方原生坐标；公开点/起终点/区域/偏移不提供绝对像素或元素局部坐标输入，也不沿用历史截图尺寸。官方入口以元素局部偏移接收参数时，内部须先按统一基准完成换算与校验；不能换一个参数名就直接接收绝对值。旋转、多窗口、键盘及当前 display 采样的一致性仍须核验，本确认不代表窗口几何事实已经验证。
- 容器定位、源定位、目的定位都须在要求单目标的路径中唯一；需要哪些 displayed/enabled/scrollable 状态，官方如何对自定义滚动容器工作，分别核对，不为了统一接口强制所有对象可点击。
- 不因目标不在屏幕上而自动滚动；只有明确的滚动查找意图可以触发官方搜索。搜索失败也不改用自建“滚动+查找”循环。

#### 5.2.3 验收轮廓

覆盖相对点/区域转换、统一显示区域基准、绝对像素模式/参数拒绝、容器/区域冲突、目标唯一性、方向语义、不同手势 percent 边界、速度单位、官方搜索起点/定位策略限制，以及超时/断线后不重放。验证内部官方坐标转换不成为对外透传入口，观测像素几何不能未经转换直接作为操作输入；滚动返回 false、未观察到变化和列表业务完整不是同义词。拖动中任一环节不确定都不得自动重做整段。实际设备与测试应用仍需对应实施授权；本节只写设计，不调用设备或安装依赖。

### 5.3 Android 系统交互：公开意图与官方映射

本节仅覆盖已确认 B1–B8。下表为**项目接口建议，尚未批准具体签名/结果 schema**；不是逐项照抄 Appium 的全部能力。调用均属于明确 Session，沿用同 Session 立即报忙和发送后不自动重放。系统按键、剪贴板、面板和应用包操作不依赖某个界面区域；真正点击界面控件仍传 Element。已确认的包名默认和覆盖逻辑属于用户需求，官方行为只决定如何适配，不重新表决需求。

| 调用意图 / 候选方法 | 调用方输入 | Automation 执行职责 / 官方入口 | 完成、失败与副作用 |
| --- | --- | --- | --- |
| 返回 `back()` | 无业务目标参数 | 调用官方 WebDriver back 一次；不判断当前页面再补导航 | 有效命令响应；可能先关闭键盘或改变页面，不保证到指定业务页 |
| 系统按键 `press_keycode` / `long_press_keycode` | `keycode: int`，可选 `metastate`、`flags` 整数 | 官方 Python 同名 helper → `mobile: pressKey` → UiAutomator2 按键端点；长按由官方 isLongPress 表达 | 按键命令完成，不证明应用响应；不虚构长按 duration。source 是官方扩展，首版是否公开另定，当前不扩大参数面 |
| IME `perform_editor_action` | 官方 `action` 名或整数码；目标形态见下文 | `mobile: performEditorAction` → Settings helper 的 editor action；不追加换行，不复用输入文字接口暗中提交 | 仅表示 editor action 命令完成，不保证搜索/发送成功；它作用于当前焦点，可能改变焦点/触发业务动作 |
| 隐藏键盘 `hide_keyboard()` | 无 Android 键名、strategy 参数 | 用 `mobile: hideKeyboard` 保留官方布尔结果；不靠另点空白处回退 | true 表示本次隐藏，false 表示原已隐藏；无法隐藏为失败。Python 同名 helper 返回 self，不能拿它伪造上述布尔 |
| 读剪贴板 `get_clipboard_text()` | 无格式参数，首版建议只纯文本 | 官方纯文本 getter 的 UTF-8/Base64 转换；driver 按 Android API 版本选择 UiAutomator2/Settings 路径 | 返回文本，合法空串保持为空；读取/解码失败不是空串。读取的是设备剪贴板，不是当前输入框 |
| 写剪贴板 `set_clipboard_text(text, *, label=None)` | `text: str`，可选 `label: str` | 复用官方 Python 文本 helper；线上编码由官方封装处理；执行映射的参数是 label | 命令完成，改变设备剪贴板；不粘贴、不聚焦、不承诺系统会永久保留内容 |
| 弹窗 `accept_alert` / `dismiss_alert` | 可选 `button_label`，映射 buttonLabel | `mobile: acceptAlert` / `dismissAlert` → 官方 alert 端点；未指定标签时由官方识别 | 官方识别/按钮点击命令完成；不存在、不支持或按钮不符按实际错误报告，不承诺已核实分类；Android 识别可能失败，不自建识别器或替代点击 |
| 展开/收起面板 `status_bar(command)` | 已确认首版白名单 expandNotifications / expandSettings / collapse | `mobile: statusBar` → driver 的固定 statusbar 命令；本库不公开任意 shell/command 透传 | 下游命令完成，可能返回空输出；不伪造 visible=true。Android 8+ 为该官方能力条件，厂商实际表现待验证 |
| 点击已有磁贴 `tap(element)` | 已确认：同 Session 的目标 Element | 重用 IF-10 的唯一、显示、启用检查后点击，不另造 tile 定位系统或 TileService component 入口 | 点击完成，不等于设置为某个开关状态；不存在/歧义/未知沿普通点击。面板展开由调用方显式选择 |

IME 的真实断点：官方不接收 Element。建议先保留明确的“对当前焦点执行 editor action”语义，且不把它当作“对指定输入框发送”。若公共意图要绑定 Element，应由 Automation 内部定位并核对 focused，或在明确批准后负责必要聚焦；不能要求 Integrations 自己拼点击/检查。**当前焦点版本、Element 版本及是否允许自动聚焦均未确认**，不是重新询问已确认的文本输入前置条件。可用 action 名为 normal、unspecified、none、go、search、send、next、done、previous；不自造跨平台键名语法。

磁贴的两种目标不可混用：上述 Element 是界面控件；官方 `statusBar(clickTile, component)` 的 component 是 TileService 组件标识（如 `com.example/.ExampleTileService`），不是磁贴文字或 resource-id。**本轮已确认**：首版已有磁贴 UI 点击只复用 `tap(element)`，不增加 component `clickTile` 入口；面板方法只接受 expandNotifications、expandSettings、collapse 三个命令。调用方显式展开所需面板再点击目标，Automation 不根据磁贴自动猜面板、发现或添加磁贴，不用命令完成假称磁贴已切换到某状态。添加/移除磁贴及其他 statusBar 命令不因上游支持而纳入。

固定官方依据（查询 2026-10-23；仅研究，不是已测组合）：UiAutomator2 v8.7.0 的 [键盘实现](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/keyboard.ts)、[剪贴板实现](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/clipboard.ts)、[弹窗实现](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/alert.ts)、[执行映射](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/execute-method-map.ts)；Android driver v14.0.8 的 [IME/键盘](https://github.com/appium/appium-android-driver/blob/v14.0.8/lib/commands/keyboard.ts)、[面板实现](https://github.com/appium/appium-android-driver/blob/v14.0.8/lib/commands/system-bars.ts)、[继承执行映射](https://github.com/appium/appium-android-driver/blob/v14.0.8/lib/execute-method-map.ts)；Python Client 固定提交见第 8 节，另见 [clipboard.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/clipboard.py)。官方 README 的剪贴板参数误写 lable，执行映射和客户端实际为 label；不照抄该拼写。mobilePressKey 的 flags TS 注解与文档/Python 整数类型不一致，实际 server 参数验证留作版本资格项，不擅自转字符串。

### 5.4 应用管理：包级操作及完整组合

六项能力沿用原需求，不重新征求是否纳入。**本轮已确认最小语义选项白名单**：终止不暴露上游 timeout；安装只公开 `replace: bool = True`、`allow_test_packages: bool = False`；卸载只公开 `keep_data: bool = False`。应用由明确 `app_id` 标识，不把 Session ID、当前前台包、Element 或应用显示名当包名。原有 Session target package 不随 activate 自动改写。所有预算和稳定错误遵守第 5 节；不开放任意 `**options`，也不把 500 秒 Session 空闲超时当应用操作等待值。

| 调用意图 / 候选方法 | 调用方输入 | Automation 执行职责 / 官方入口 | 完成、失败与副作用 |
| --- | --- | --- | --- |
| 激活 `activate_app(app_id)` | 明确 Android 包名 | 官方 activateApp；必要时启动或带到前台，不先 terminate/reset | 激活命令完成，不证明某 Activity/业务页面已出现，不自动安装缺失应用 |
| 终止 `terminate_app(app_id)` | 包名；不公开上游 timeout | 官方 terminateApp 获取原进程、force-stop 并按官方规则等待；具体等待值由统一操作预算适配，不自行杀其他进程 | 保留 true/false：false 可表示原未运行；true 是官方终止判定，不保证持续停止。不得通过内部 timeout≤0 跳过状态核对来伪装完成 |
| 状态 `query_app_state(app_id)` | 包名 | 官方 queryAppState；安装检查、运行状态和窗口焦点判断由 driver 完成 | Android 已核对状态为 0 未安装、1 未运行、3 后台、4 前台；失败/未知不是 0，不承诺 iOS 的状态 2 或持续健康 |
| 安装 `install_app(app_path, *, replace=True, allow_test_packages=False)` | 明确本地单 APK 路径；显式是否替换已有包、是否允许测试包 | 校验仅允许本地 APK，传给官方 installApp；路径属于 Appium 服务所在文件系统，首批本地连接不自动上传/下载 | 安装/升级命令完成，不启动应用。replace=true 沿 Appium 默认允许替换/升级；版本/签名/数据迁移受 Android 约束；失败可能有已完成准备，不自动卸载重装兜底 |
| 卸载 `remove_app(app_id, *, keep_data=False)` | 包名；显式是否请求保留应用数据和缓存 | 官方 mobile: removeApp；使用能保留官方返回值的公开入口，不从 Python 返回 self 推断 bool | true 表示找到并成功卸载；false 可表示未安装。默认不保留数据；仅 keep_data=true 才承诺发送保留请求，实际平台结果须验证；卸载可能影响当前应用与后续 Session |
| 清数据 `clear_app(app_id)` | 明确包名；终止/核对使用公共操作总预算 | **已确认必要组合**：内部查询安装/运行状态，运行中则官方 terminateApp，再核对未运行后调用官方 clearApp；见下文组合边界 | 清除应用数据、缓存和设置的命令完成，不重启、不重授权限、不保证原 Session 继续可用；前置终止已完成而清除失败时保留部分完成事实 |

`clear_app` 的必要组合**本轮已确认**：官方 clearApp 只调用 adb.clear，文档要求应用存在且未运行；Automation 必须完成所承诺的设备步骤，不能迫使 Integrations 先停应用。同一 Session 准入和操作总预算内，先查询安装/运行状态；未安装明确返回而不发送 terminate/clear；运行中调用一次官方 terminateApp，然后显式核对已安装且未运行，才调用一次 clearApp。不调用公开方法递归取锁，不增加任意等待/搜索循环。官方 terminateApp 在原进程被新进程替代时也可能返回 true，所以不能仅凭 true 继续清数据。再次运行、状态不明或预算不足时停止，不发 clear、不反复终止；已终止但 clear 失败或响应丢失时保留部分完成/执行未知。核对与清除非原子，竞态按实际失败或未知返回，不自动重试、回滚或声称数据已保留。各阶段如何分配预算仍由公共预算模型收敛，不重新开放组合决定。

选项边界**本轮已确认**：安装只公开 `replace=True` 与 `allow_test_packages=False`；卸载只公开 `keep_data=False`；终止、安装、卸载均不公开上游 timeout，由后续统一操作预算模型规定内部适配和不足预算行为。`checkVersion` 会把操作变为可能跳过安装，`grantPermissions` 会扩大到权限副作用，`useSdcard`、`noIncremental`、`skipInstallCheck` 也不首发。正常 quit 的 noReset/shouldTerminateApp 不能抵消显式卸载/清数据。安装本地 APK 不是承诺可以读 Appium server 任意其他文件；不接受 URL、APK 集或隐藏下载。未来新增选项须按其独立语义确认，不提供 `**options` 绕过白名单。

官方文档与实现差异必须保留：安装 timeout 的 v8.7.0 README 写 6000ms，而 v14.0.8 mobileInstallApp 注释写 20000ms，当前实现还向 appium-adb 传递可选值；本文**不采用任一数字作为默认**，需沿实际选定依赖继续核验或显式设定。clearApp 文档称返回 stdout，但所查 Android driver 实现 await adb.clear 后无返回，故本接口只承诺命令完成，不暴露虚构 stdout/bool。terminateApp 已查默认等待 500ms，这是应用进程等待，与 Session 500秒空闲不是同一设置。

版本化依据：UiAutomator2 v8.7.0 [应用 API 文档](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md#mobile-queryappstate)、Android driver v14.0.8 [app-management.ts](https://github.com/appium/appium-android-driver/blob/v14.0.8/lib/commands/app-management.ts) 与 [执行映射](https://github.com/appium/appium-android-driver/blob/v14.0.8/lib/execute-method-map.ts)、Python Client 固定提交 [applications.py](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/applications.py)。这些分别核对的版本不是已锁定或已测兼容组合，Appium-adb 默认值、权限副作用与测试 APK 的最终状态仍须后续资格验证。

本增量验收轮廓（未执行）：隐藏键盘 true/false/失败不混同；剪贴板中文/空串往返及读取失败；IME 焦点变化不伪称指定目标；官方弹窗识别失败不自动点击；面板命令白名单与 Element 磁贴点击；应用状态0/1/3/4；终止未运行及被重新拉起；本地APK升级失败、卸载未安装、清除前置失败/部分完成/响应丢失。应用变更后不自动重建 Session/重放命令，原占用和清理按真实状态处理。仅文档与官方资料核验，无设备/服务调用。

## 6. 场景推演及尚待解决的断点

以下为**调用契约推演**，不是产品代码示例或已运行测试。所有步骤明确归属同一已选择的 Session；业务流程由调用方组合。

| 场景 | 公共操作顺序 | 必须验证的失败分支 | 当前断点 |
| --- | --- | --- | --- |
| S01 单设备生命周期 | IF-01 → 显式选 ID → Runtime active 连接 → IF-02 → IF-04 → 退出 Runtime | 无设备、设备占用、创建响应丢失、关闭未知、主体与清理同时失败 | U01/U02/U03/U06/U07；不能提前释放连接或设备占用 |
| S02 观测后点击 | IF-05 → 从属性构造定位 → IF-10 → 调用方按需要 IF-08/IF-05 | 节点已消失、文本改变、重复匹配、控件遮挡、点击响应丢失 | 目标/前置规则；不把节点变为 ref、不自动点击另一个匹配 |
| S02a 同一 Element 跨调用复用 | 同一 Session 保存其创建的目标定位描述，界面刷新后再次操作该 Element；每次重新查询唯一节点及所需几何 | 不复用旧 elementId/bounds；无匹配等待、多匹配报歧义；动作发出后 stale/响应丢失不自动重定位重放 | Element 语义/Session归属已确认；具体工厂与错误模型待定，不证明多次匹配是同一物理节点 |
| S02b Element 创建与跨 Session 使用 | A 创建 Element 时不查询设备；B 接收 A 的 Element 时拒绝；A 依然可按自身状态使用该目标 | 跨 Session 拒绝发生在任何设备请求前，不复制/改绑；不同对象即使同设备也不绕过所属检查 | 创建和归属行为已确认；关闭后构造/操作规则与稳定错误类型待设计 |
| S02c 父容器与XPath首版边界 | 根XPath可构造Element；子目标by=XPATH且parent非空在构造阶段拒绝 | 不查询设备、不改写XPath、不丢parent全页搜索；根XPath父+ID子不被本条一并禁止但须资格验证 | 首版组合限制已确认；parent其他策略/类型及实际查询支持待定 |
| S03 文本三个意图 | 对同一字段分别演示 IF-13、IF-14、IF-15，调用方显式决定所需意图 | 清空后输入失败、聚焦改变布局、文本定位失效、超时但可能已写入 | 官方替换能力/目标身份；输入不默认为追加或替换，不自动提交 |
| S03b 文本目标暂时禁用/未显示 | 唯一用户名输入框已显示但 enabled=false，等待启用后执行选定文本操作一次；未显示只等待 | 超过预算不写入、不额外点击/滚动/切页/隐藏键盘；多个匹配报歧义；普通标签满足基本条件也不代表可编辑 | 基本前置及不自研编辑性识别已确认；等待错误/正式字段及实际版本资格仍待设计 |
| S03c 读取禁用或未显示控件 | 在driver可定位范围内找到唯一控件，读取文字、enabled/displayed等请求属性 | 不等待属性变true、不启用/显示/聚焦；driver不可读取时报告失败/未知；多匹配不取第一个 | 读取前置已确认；不存在与不可观测的准确分类、返回字段仍待设计 |
| S03a 特殊 Enter 尾缀 | send_keys/replace_element_value 输入以字面反斜线+n结尾 | 纯值阶段拒绝，不定位/聚焦/清空，不改写文字，不发送 Enter | 单项已确认；真实LF/CR和其他字符支持仍待资格验证 |
| S04 容器中查找并操作 | IF-05/06 明确容器 → IF-18 → IF-10 重定位目标 | 不支持的查找策略、预算耗尽、容器消失、目标重复 | U05；官方搜索限制，返回不能宣称列表业务完整 |
| S04a 相对点/区域手势 | 本次操作采样显示区域，按宽高转换 [0,1] 点、起终点或区域，再调用官方能力；容器另由定位给出 | 绝对像素参数/模式不接受；不将同一坐标改按容器局部解释；旋转/窗口变化导致采样失效时不盲用旧几何 | 相对坐标与统一基准已确认，变化检测、边界与舍入待设计 |
| S05 键盘、弹窗和面板 | 调用方判断后 IF-22/23/26/27/28/29 | 键盘原隐藏/隐藏失败、IME焦点变化、官方弹窗识别失败、磁贴缺失、厂商差异 | 5.3；IME目标待收敛，磁贴Element点击复用tap，不自动接收弹窗或回退点击 |
| S06 应用与 Session 分离 | IF-30 → IF-32 → IF-31 → IF-04；IF-33/34/35 单独显式场景 | 应用状态未知、终止后被重新拉起、安装/清数据后会话变化、关闭默认值交互 | U06及5.4；应用关闭不等于Session关闭，清数据前置组合不能外包给Integrations |
| S06a 清数据的必要组合 | 单次 IF-35 内部检查安装/运行 → 必要 terminate → 核对未运行 → clear；同一次Session准入与总预算 | 未安装、停止失败、被重新拉起、停止已完成但清除失败、清除响应丢失 | 5.4组合已确认；不要求接入层拼步骤，不递归取锁、不回滚或自动重试；阶段预算待公共模型收敛 |
| S07 多设备隔离 | 在同一 active Runtime connection 中两个明确设备各建 Session，操作只作用于各自归属 | A 的正常 quit 不关闭 B；相同设备拒绝；客户端/端口资源独立；创建/退出及跨线程冲突分别验证 | 正常生命周期已确认，U03/并发资格仍未解决；不是跨进程多连接或并行通过声明 |
| S07a 同 Session 重叠调用 | A 操作仍在执行时，B 操作请求同一 Session | B 返回忙且没有设备命令发送，不排队；A 不被打断；A 结束后的显式新调用独立处理 | 产品规则已确认；原子准入、重入、关闭/取消竞态及取消后的收尾时点待设计 |
| S07b 500 秒空闲与异常回收 | 无新命令后由 Appium 回收；后续调用按实际失效或未知结果处理 | 命令执行中不按空闲计时推断关闭；不以反复 Session 查询续命；Session 不在列表不证明设备清理完成；创建无 ID 不猜归属 | 空闲默认已确认；跨进程未知占用保证与核实方式仍待决，不自动新建 |
| S08 接入一致性 | 同意图的 Python 调用与未来 MCP JSON/CLI 参数映射 | 接入是否擅自追加聚焦、清空、重试、等待或重新选设备 | 仅纸面映射，不提前实现 CLI/MCP 或 Session daemon |

推演通过标准：调用方能说明下一步依据；执行未知时不会被迫猜“可以整段重跑”；Automation 为自身承诺提供全部设备步骤。尚未定义的键名、坐标、超时等保持断点，不用伪代码填成默认行为。

## 7. 移动端参考与取舍

研究日期：2026-10-23。固定提交仅证明当时源码形态，不是精确兼容/质量/设备支持背书。第三方项目是设计参考，不作为本项目依赖批准；不复制其默认重试、截图回退、压缩丢字段或协议实现。下列路径可直接定位主入口与主要执行：

| 项目 / 固定提交 | 公开形态与关键源码 | 本设计采用的启发 / 保留差异 |
| --- | --- | --- |
| callstack/agent-device `6ea9f81733943d0408cad2046fac1caafbde977c` | [命令定义](https://github.com/callstack/agent-device/blob/6ea9f81733943d0408cad2046fac1caafbde977c/src/commands/interaction/metadata.ts)、[MCP Adapter](https://github.com/callstack/agent-device/blob/6ea9f81733943d0408cad2046fac1caafbde977c/src/mcp/command-tools.ts)；CLI/MCP/Node 共享执行 | 共享定义、明确 fill/type、动作结果分层；不引入其跨调用 ref、隐式启动设备和整套框架 |
| mobile-next/mobile-mcp `c659f8ee34873a832adea7daca9c69172d887e70` | [工具表](https://github.com/mobile-next/mobile-mcp/blob/c659f8ee34873a832adea7daca9c69172d887e70/src/server.ts)、[Robot 执行](https://github.com/mobile-next/mobile-mcp/blob/c659f8ee34873a832adea7daca9c69172d887e70/src/mobile-device.ts)；配套 mobilecli 动作 CLI | 设备显式、接入复用执行；不照搬当前焦点输入、像素坐标和批量调工具回调模式 |
| appium/appium-mcp `85ae0c7702f4f752fa7eeb5f0f329326aee7ff1b` | [Session](https://github.com/appium/appium-mcp/blob/85ae0c7702f4f752fa7eeb5f0f329326aee7ff1b/src/tools/session/session.ts)、[手势](https://github.com/appium/appium-mcp/blob/85ae0c7702f4f752fa7eeb5f0f329326aee7ff1b/src/tools/gestures/schema.ts)；MCP 启动命令不是逐动作 CLI | 官方命令映射和所有权可参考；不采用 active Session，不照搬自建滚动搜索循环/宽泛回退 |
| mobile-dev-inc/Maestro `6468ea39a9930f3ceda2581470f6ea7af8dfe81e` | [流程入口](https://github.com/mobile-dev-inc/Maestro/blob/6468ea39a9930f3ceda2581470f6ea7af8dfe81e/maestro-cli/src/main/java/maestro/cli/mcp/tools/RunTool.kt)、[引擎](https://github.com/mobile-dev-inc/Maestro/blob/6468ea39a9930f3ceda2581470f6ea7af8dfe81e/maestro-orchestra/src/main/java/maestro/orchestra/Orchestra.kt)；MCP run/CLI test 执行流程 | 单操作与流程分开；不建立 YAML 引擎，不照搬自动权限和重启默认值 |
| zhongerxin/iPhone-use `3ce9c080534e89fab91a237bf1c53a4a7e9d80a7` | [工具与运行入口](https://github.com/zhongerxin/iPhone-use/blob/3ce9c080534e89fab91a237bf1c53a4a7e9d80a7/server/iphone_use.py)、[Controller](https://github.com/zhongerxin/iPhone-use/blob/3ce9c080534e89fab91a237bf1c53a4a7e9d80a7/server/wda_controller.py)；MCP/JSON CLI 共享运行 | 完整设备操作、部分执行、批次停止；不自动批准长文本续传、视觉回退和跨页采集 |
| leeguooooo/iphone-use `1708236e2ad44f51649a5289ab5294ab44eef4c5` | [MCP 参数和步骤](https://github.com/leeguooooo/iphone-use/blob/1708236e2ad44f51649a5289ab5294ab44eef4c5/crates/mcp/src/server.rs)、[HTTP/执行](https://github.com/leeguooooo/iphone-use/blob/1708236e2ad44f51649a5289ab5294ab44eef4c5/crates/server/src/http.rs) | 动作/观测/未知分开，入口可暴露子集；不将 clear 最佳努力或快照索引当作本项目替换保证 |
| FSQ-lab/FSQ `1b629c57b5cde12c2158ad155bd8a494e08c8208` | [Android Interface](https://github.com/FSQ-lab/FSQ/blob/1b629c57b5cde12c2158ad155bd8a494e08c8208/fsq_agent/core/interfaces/_android_driver.py)、[实现](https://github.com/FSQ-lab/FSQ/blob/1b629c57b5cde12c2158ad155bd8a494e08c8208/fsq_agent/drivers/android/_uiautomator2.py)；CLI 面向任务/Case，内部工具不是 MCP 服务承诺 | 参数/能力/执行分层；Android Python uiautomator2 非 Appium driver；performActions 定义但该后端未实现，不计有效能力 |
| microsoft/AutoGenesis `158020978f651834912ea867b356845549f7a032` | [MCP 工具及执行](https://github.com/microsoft/AutoGenesis/blob/158020978f651834912ea867b356845549f7a032/appium-mcp-server/tools/appium_driver_tool.py) | 多步动作和状态意图可参考；执行不放在我们的 MCP Adapter，不照搬固定 sleep/宽泛异常归并及静默回退 |

## 8. 库复用、官方依据与设计阻塞

本批写文档，不实现 Python，**不安装或修改依赖**。面向后续实现的选型是 Ready 前提；下表区分本轮已批准用途与仍待资格验证项，批准不等于SPEC gate或实施授权。

| 用途与候选 | 当前判断 | 需补的版本化依据与验证 | 状态 |
| --- | --- | --- | --- |
| WebDriver/Session：Appium-Python-Client 6.0.8 + Selenium 4.51.0 | **用户本轮具体批准**：直接固定这两个版本，仅用于Automation的Session/WebDriver/Appium命令；不启用AppiumService、浏览器、Selenium Manager或BiDi | 传递依赖锁定/许可证/安全、实际wheel签名、create/quit、timeout/取消/异常/清理、系统端口与目标server/driver资格验证 | 版本/用途已批准；资格验证和SPEC/实现仍阻塞 |
| Android发现：Python3.11 `subprocess` + 调用方显式官方ADB | **用户本轮具体批准**：只执行固定 `adb devices -l`，不使用shell/PATH回退/任意ADB，不自行实现协议 | 实际Android Platform Tools版本、输出/状态、超限、显式Control取消与子进程回收；真实查询需设备授权 | 用途已批准；资格验证/设备操作仍阻塞 |
| JSON/XML：Python 3.11 标准库、成熟 XML 解析库/现有封装 | JSON 纯值转换与业务映射不等于批准重写解析器；XML 安全与资源界限待评估 | 目标 Python 官方行为、拒绝/限制策略、完整层级与大输入、异常、采集和返回上限分开验证 | U02/U04；未批准 |
| 版本比较/协调/取消：现有批准库、标准库、成熟封装 | 不重新实现通用版本或协调框架；不能因为同账号锁已存在就复制为设备锁 | 复用既有批准用途记录；新增范围、身份、恢复与故障需独立评估 | U01/U03/U07 |

原稿固定 UiAutomator2 v8.7.0 参考仅是核验入口：[README](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/README.md)、[元素命令](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/lib/commands/element.ts)、[手势](https://github.com/appium/appium-uiautomator2-driver/blob/v8.7.0/docs/android-mobile-gestures.md)。本文未重做其完整资格研究，不把引用等同于已验证支持。后续每个选型记录须含查询日期、版本/允许范围、官方 API/源码位置、成熟度/维护/安全/许可证/类型/传递依赖、保证与适配缺口、验证方法及具体批准原文；缺关键依据保持阻塞。

命名核对日期 2026-10-23：仅用于术语研究的 Appium Python Client 固定提交 `d261253b89786fb4686b374721f0fbd0b8c02854`，不是候选版本选定或安装批准。[ActionHelpers](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/action_helpers.py)公开 tap/swipe/scroll/drag_and_drop；[Applications](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/applications.py)公开 activate_app/terminate_app/query_app_state/install_app/remove_app；[Keyboard](https://github.com/appium/python-client/blob/d261253b89786fb4686b374721f0fbd0b8c02854/appium/webdriver/extensions/keyboard.py)公开 hide_keyboard/press_keycode/long_press_keycode。这些词对应的原始参数和所有者需逐项映射；本文不照搬裸元素或像素坐标参数。文本和会话关闭的最终命名需结合本项目封装语义继续核对。

待决顺序：D01 Session 形态方向已确认（明确对象归属、核心无当前 Session/全局 Registry、重叠调用立即报忙且不排队；类名/关闭/取消竞态仍待设计）→ D02 正常生命周期及 500 秒空闲回收已确认，接续 U03-P1 核实回收/未知占用边界，不预定持久恢复机制 → D03 目标/坐标和观测 schema → D04 预算/取消/错误表达 → D05 近期操作前置与 Appium 命名/官方映射 → D06 版本/用途选型 → D07 feature 顺序与预算确认。技术事实先研究，用户只决定产品取舍；每次只问一个关键问题，不重复询问已有确认。

### 8.1 剩余决策清单（按收敛顺序）

下表只列尚未确认的新增产品取舍和后续设计工作；第 2.1/2.2 节已确认事项不重新开放。`建议`不是批准，`技术门槛`由版本化资料和资格验证回答，不交给用户猜测。

| 顺序 | 决策 / 工作 | 已确认边界 | 当前建议或需产出的契约 | 状态 |
| --- | --- | --- | --- | --- |
| P1 | IME 目标语义 | B4 已纳入；命令完成不代表业务发送；Integrations 不补聚焦步骤 | 首版只提供“对当前焦点执行 editor action”；不接收 Element、不自动点击或聚焦。若调用方需要指定目标，先显式执行已有 Element 操作并自行确认焦点 | **建议待确认**；官方入口只作用于 active input field，见 5.3 |
| P2 | 面板与已有磁贴入口 | 展开通知、展开快捷设置、收起、点击已有磁贴已纳入；不添加/移除磁贴 | `status_bar` 只接受三个命令白名单；视觉磁贴只复用 `tap(element)`，不首发 TileService component `clickTile` | **本轮确认**；组件不是界面标签或 resource-id |
| P3 | `clear_app` 必要组合 | 清数据是显式应用操作；Automation 封装其承诺所需设备步骤 | 同一 Session 准入与总预算内：查询安装/运行状态 → 必要时终止 → 核对未运行 → clear；无法证明停止即不清除，不重试、不回滚，保留部分完成 | **本轮确认**；查询与清除非原子，阶段预算待 P6 |
| P4 | 应用选项白名单和默认 | 六项应用能力已纳入；默认保留数据；不开放任意 `**options` | 终止无上游 timeout；安装 `replace=True`、`allow_test_packages=False`；卸载 `keep_data=False`。`checkVersion`、权限、SD 卡、增量安装、跳过检查等不首发 | **本轮确认**；内部等待适配待 P6 与锁定版本资格验证 |
| P5 | 公共错误模型 | 响应丢失不能断言未执行；不自动重放；同 Session 重叠立即报忙 | 异常式接口；稳定错误族、`request_state`、`completed_steps`、原始异常链及 `cleanup_errors` 分别表达；无通用 retryable | **本轮确认**；具体上游映射待锁定版本资格验证 |
| P6 | 预算与取消 | 目标等待默认15秒；Session空闲默认500秒；检查点取消已确认；各层与响应预算分开 | 复用 `runtime.OperationControl`；`control=None` 沿 Appium 默认并接受可能无有限上限；显式 Control 提供总预算；阻塞命令结束及收尾前保持忙 | **本轮确认**；显式 timeout 能力与清理仍须锁定版本资格验证 |
| P7 | 生命周期异常恢复 | 正常为单active connection、多Session、显式quit；不自动心跳/重建/重放 | creating/active/uncertain/closing/closed；未知时禁普通命令并保留本进程占用；崩溃后保证终止，不写持久账本；direct_connection关闭 | **本轮确认**；Runtime并发退出竞态和实际客户端清理待资格验证 |
| P8 | 近期 feature 设计 | 一次一个 feature，约 1200 产品行目标；AIF-01/02 优先 | 补齐 AIF-01/02 的完整接口、错误/预算/恢复验收、选型门槛和模块整体验收接缝，再确认顺序与预算 | **待 P1–P7 收敛；未 Ready** |

并行但不由上述产品问答替代的技术门槛：Appium Python Client/UiAutomator2/Appium Server 精确版本与用途选型，ADB 设备发现方式，XML/JSON 处理，跨线程客户端与多 Session 资源参数，取消/传输清理能力。任何候选仍须按第 8 节完成资格研究和具体用户批准；本清单不批准依赖、设备操作或 SPEC delta。

## 9. Feature 地图与近期设计深度

旧 AUTO-01–09 不被本表自动替换。以下是新草案 `AIF-*` 便于区分，均**未 Ready/未实施/顺序待确认**。公共类型随首个实际行为 feature 交付，不拆成“写数据类”feature。近期详细设计优先 AIF-01/02，其余保持行为验收轮廓，不先写全模块。

| Feature | 行为目标 / 非目标 | 依赖与 SPEC 影响 | 独立验收与验证入口 | 产品/测试/文档预算（新增+删除） |
| --- | --- | --- | --- | --- |
| AIF-01 | 查询已有设备；不启动设备、不自动选择 | U02，设备查询选型；Automation | 成功/无设备/查询失败、身份/状态、资源预算；已有 pytest 入口＋获准真实查询 | 250–450 / 250–450 / 80–140 |
| AIF-02 | 明确设备 Session 创建/跨调用复用/关闭与占用保护；不交付动作/Registry | AIF-01，D01/D02/U02/U03/U06/U07；Automation、必要 Runtime/Contracts delta | 生命周期、重复占用、部分创建、关闭未知、双错误、多设备接缝；pytest＋获准真实 Session | 700–1100 / 700–1200 / 140–240；明显超额先重拆 |
| AIF-03 | 读取范围内结构及唯一控件/原始定位依据；不跨页采集 | AIF-02，U04；观测与目标契约 | 64 KiB 边界、层级/全文/状态、多窗口、范围回退、歧义；pytest＋授权页面 | 700–1100 / 800–1300 / 140–240 |
| AIF-04 | 定位后点击/双击/长按及必要条件等待；不判断业务成功 | AIF-03，前置条件与预算核验 | 唯一/缺失/歧义、按动作检查、一次执行、等待不重放；pytest＋测试应用 | 450–750 / 500–850 / 100–160 |
| AIF-05 | 输入/清空/替换三个意图，必要动作组合；不当前焦点输入/提交 | AIF-04，文本官方能力资格 | 不隐式清空、目标身份、部分执行、响应丢失；pytest＋授权输入页面 | 350–650 / 450–800 / 100–180 |
| AIF-06 | 已选滑动/滚动/查找/拖动；不自建通用搜索 | AIF-04，U05；坐标/官方策略 | 相对坐标、明确容器、策略限制、停止/未知；pytest＋授权滚动页面 | 450–800 / 500–900 / 100–180 |
| AIF-07 | 已选键盘/纯文本剪贴板/弹窗；不自建识别 | AIF-04，5.3候选/焦点边界及版本资格 | 无隐式提交、键盘true/false、剪贴板空串/失败、官方识别失败不降级；pytest＋授权设备 | 350–650 / 400–750 / 80–140 |
| AIF-08 | 通知栏/快捷设置展开收起及已有磁贴；不新增磁贴 | AIF-07，5.3面板白名单与Element tap复用建议 | 面板种类/厂商差异、无目标、不伪称开关状态；pytest＋授权设备 | 200–450 / 300–500 / 60–120 |
| AIF-09 | 应用激活/终止/状态；不推断业务页面 | AIF-02，U06及5.4 | Android0/1/3/4、未运行终止/被重新拉起、Session与应用分开；pytest＋授权应用 | 200–400 / 250–450 / 60–120 |
| AIF-10 | 显式安装/卸载/清数据及必要前置；不改变默认保留数据 | AIF-09，U06/U08及5.4组合/选项确认 | 本地APK与升级失败、卸载未安装、清除前停止/核对及部分完成、Session后续状态；pytest＋专用APK/设备授权 | 250–450 / 350–550 / 80–140；组合超额须先重拆 |

顺序建议 AIF-01 → AIF-02；后续先完成 AIF-03/04，再根据真实验收依赖收敛文本、手势、系统与应用序列。表中可早满足依赖的 feature 也不并行实施，不因某项审查/验证受阻转去实现另一项。每个 feature 启动时固定自己的 Git 基线，累计新增+删除，测试/文档单列；移动/生成项单列理由，不用净增长规避约 1200 行目标。

实际已有工具为 `uv run pytest`、Ruff、strict mypy、import-linter 及构建入口，均按根 SPEC 使用；Automation 测试尚不存在，本文未运行产品验证。设备安装/清数据等操作未授权，不编造真实链路结果。

当前模块/平台整体验收：明确设备 → Session → 结构/定位/已选动作/等待 → 应用管理 → 关闭/占用释放；覆盖失败/超时/取消/资源清理、64 KiB、多设备需求及适用真实 Android 链路。模拟通过不等于设备通过，单 feature 不等于模块完成。

### 9.1 AIF-01：只读设备发现

**目标**：调用方从明确的 Android SDK `adb` 可执行文件查询当前 ADB server 已知的真机和已启动模拟器，取得可用于 AIF-02 的稳定设备ID、可选名称和本次连接状态；空列表是成功结果。**非目标**：不自动选择设备，不启动/创建模拟器，不连接/配对无线设备，不等待设备上线，不执行任意ADB命令、shell、安装或属性采集。

公共形态建议：

```python
list_devices(
    adb_executable: Path,
    *,
    control: OperationControl | None = None,
) -> tuple[DeviceInfo, ...]
```

`DeviceInfo` 为Automation不可变值，字段为 `id: str`、`name: str | None`、`connection_state`。`id` 是本次ADB列出的serial原文，经UTF-8/长度/控制字符校验后保留，不用展示名替代；`name` 取 `adb devices -l` 的model描述，缺失时为None，不伪造serial为名称。连接状态至少区分connected、offline、unauthorized、unknown；空输出设备段返回空tuple，命令失败、不可解析和超限不能伪装成空列表。原始ADB任意附加字段不成为公共schema。

执行只允许参数数组 `[adb_executable, "devices", "-l"]`，不用shell、PATH回退或环境中的另一个adb。路径须为绝对普通文件；显式路径失败不扫描SDK或回退。调用可能按ADB官方行为启动本机ADB server，但不会启动设备或模拟器，须在实施验收中记录该宿主副作用。输出按UTF-8严格解码，建议上限64KiB、最多256个设备；超限明确失败。返回按ID排序以获得确定性，不把输出顺序当优先级。`control=None` 不增加项目总预算；显式Control时子进程须在deadline/取消时终止、等待回收并关闭pipe后返回，不能遗留进程。

复用评估（查询2026-10-23；推荐方案用途已获用户本轮具体批准，尚未实施）：

| 候选 | 适配性与代价 | 判断 |
| --- | --- | --- |
| Python 3.11 `subprocess` + 官方Android SDK Platform Tools `adb devices -l` | 复用官方ADB client/server和已安装SDK，不实现ADB wire protocol；只需有界子进程、固定命令和小型行解析 | **已批准首feature用途**；无新增Python依赖，仍须记录并资格验证实际Platform Tools版本 |
| adbutils 2.12.0 | 提供直接ADB server协议和设备列表，但引入requests、deprecation、retry2、Pillow，能力面远超只读发现；默认socket timeout可为None | 不推荐首feature；额外协议实现/依赖/重试面没有收益 |
| adb-shell 0.4.4 | 自行实现ADB shell/FileSync，USB为experimental，PyPI元数据未声明目标Python范围，当前用途不需要shell/FileSync | 不推荐 |

官方依据为Android Developers [adb文档](https://developer.android.com/tools/adb)：ADB是Platform Tools中的client/server/daemon；`adb devices -l`列出serial、state及描述，官方明确device不表示Android已经完全启动，offline与无设备不同。标准库方案不是自研ADB协议；解析仅覆盖该受限命令的公开输出，遇到未知状态保留unknown而非扩展任意命令。

错误与验收：无效路径/参数为 `invalid_argument/not_sent`；同一发现调用取消/超时为已确认公共模型；执行失败、非零退出、非法UTF-8、重复ID冲突、输出/设备数超限分别稳定分类。受控临时可执行文件验证参数、排序、空列表、connected/offline/unauthorized/unknown、边界与进程回收；获准真实验证须运行明确adb路径，核对至少无设备或实际设备之一，证明未自动选择、启动模拟器或执行第二条设备命令。AIF-01产品/测试/文档预算维持250–450 / 250–450 / 80–140；超出先重拆。SPEC增量仅Automation公开入口、DeviceInfo/错误和源码映射；不改Runtime/Contracts。

**Ready阻塞**：标准库+官方ADB CLI用途已获用户批准；实际Platform Tools版本与行为尚未资格验证，真实ADB查询尚未授权。批准不等于设备操作、SPEC或实现授权。

### 9.2 AIF-02：明确设备 Session 生命周期

**目标**：在一个active Runtime connection内，为调用方明确指定的device创建独立Appium Session，跨多次调用复用，提供本地 `session_info` 和显式 `quit`，执行本进程同设备占用、同Session立即忙及已确认异常状态机。**非目标**：不交付界面动作、观测、外部Session attach、全局Session查询、持久Registry、跨进程占用、后台心跳、自动恢复/重放、Appium服务启停或设备调度器。

候选公共形态；参数名仍须独审和最终设计确认，行为边界如下：

```python
create_session(
    connection: RuntimeConnection,
    device_id: str,
    *,
    app_id: str,
    app_path: Path | None = None,
    auto_launch: bool = False,
    force_app_launch: bool = False,
    no_reset: bool = True,
    full_reset: bool = False,
    should_terminate_app: bool = False,
    new_command_timeout_seconds: float = 500,
    capabilities: Mapping[str, JsonValue] | None = None,
    control: OperationControl | None = None,
) -> Session
```

首批要求明确 `app_id`，即使同时给APK也用它作为Session目标包和短resource-id默认包；`app_path=None`表示使用已安装应用，非None须为本地绝对单APK路径且由当前本地Appium服务可读。该收敛避免从APK或前台应用猜目标包，仍保留原需求的已安装包/APK两种输入。`auto_launch`等一等映射Appium能力，不创造keep/activate/restart模式；组合冲突在任何Session请求前拒绝，具体矩阵须按最终UiAutomator2版本资格验证。

Automation固定并验证 `platformName=Android`、`appium:automationName=UiAutomator2`、`appium:udid=device_id`、目标app/appPackage、500秒空闲默认及首批已确认范围。原始capabilities只允许批准白名单内、JSON可表达且有界的附加项；与一等参数、设备、平台、driver、连接端点、`direct_connection`、系统端口或首批范围冲突时明确拒绝，不静默覆盖。`enableMultiWindows=true`按原需求加入所选版本正确入口，但不据此宣称已取得窗口来源。Automation为不同active/uncertain Session分配并保留唯一UiAutomator2 `systemPort`；这是内部资源，不要求调用方调度，外部客户端冲突不在保证内。WebView/Chromedriver、MJPEG和录屏端口不因并行章节存在而配置。

每个Session持有一个独立Appium客户端、设备/目标身份和生命周期状态；不同Session不共享WebDriver实例、sessionId或命令连接。同进程内部协调器只保存设备与systemPort保留信息，不能按ID查回Session或作为公共Registry。创建请求发出前同时保留device和port；按第5.0.2节处理成功、可证明未创建、响应未知。`direct_connection=False`，禁止新Session响应把客户端切到未经Runtime验证的端点。普通操作与quit在开始前验证Runtime connection仍active；首批要求调用方将Runtime退出与所有Session生命周期串行化，正常顺序仍为全部quit后退出。现有Runtime没有可供Automation持有的lease，因此跨线程并发退出的check-then-exit竞态不承诺被完全拦截；若最终要求强制阻止退出，必须单列Runtime SPEC delta，不能读私有锁实现。

`session_info`只读本地快照，不发Appium命令。`quit`在active且不busy时发送一次DELETE；closed再次quit返回None；busy立即报忙；closing/uncertain不自动再发DELETE。有效成功响应、Appium客户端连接资源关闭和Automation收尾都完成后才释放本进程device/port。主体错误与客户端关闭错误按已确认 `cleanup_errors` 并存。进程崩溃后内存占用保证终止，不写磁盘；新进程不宣称旧Session已被500秒机制清理。

依赖复用决定（查询2026-10-23；版本/用途已获用户本轮具体批准，尚未安装或实施）：

| 用途 | 推荐版本与证据 | 适配/验证缺口 |
| --- | --- | --- |
| Appium公共客户端 | `Appium-Python-Client==6.0.8`，2026-10-20发布，PyPI Production/Stable，Apache-2.0，Python>=3.10，当前漏洞列表为空；**批准仅用于Session/WebDriver/Appium命令，不启用AppiumService** | 必须验证create/quit、AppiumBy、mobile命令、idempotency key、direct_connection关闭、客户端资源关闭、异常映射 |
| WebDriver传输依赖 | 直接固定 `selenium==4.51.0`，2026-10-09发布，Apache-2.0，Python>=3.10，当前漏洞列表为空；6.0.8元数据要求`>=4.51.0,<5`；**批准作为上述固定传输/元素依赖** | 直接固定避免宽范围漂移；须审查urllib3/trio/websocket等传递依赖和锁定产物，Automation不启用浏览器/Selenium Manager/BiDi |

6.0.8还依赖typing-extensions~=4.16，Selenium带来certifi、urllib3[socks]、trio、trio-websocket、typing_extensions、websocket-client；不得把Appium客户端一项批准解释为这些依赖无需锁定/许可证/安全核验。官方README称v4.3+请求默认120秒，但所核Selenium4.51.0 `ClientConfig`源码默认取 `socket.getdefaulttimeout()`，资料存在差异；必须以实际锁定wheel公开签名和行为测试为准。该差异尤其阻塞显式Control映射与用户已接受的“control=None沿Appium默认”准确说明。

AIF-02受控验证不要求真实设备的部分：临时HTTP Appium协议服务验证capabilities、单次create/quit、无自动重试、direct connection不切换、稳定错误/原始异常/清理错误、同Session并发立即忙、本进程设备/port占用、状态机及connection失效前置拒绝；客户端线程/连接全部结束后资源才可复用。不得用mock成功代替Appium客户端真实序列化与异常路径。获准真实验收必须使用固定Appium/UiAutomator2组合和专用Android设备，覆盖已安装包与本地APK、autoLaunch=false、500秒能力协商、同设备拒绝、不同设备独立Session、分别quit且A不关闭B；不执行本feature范围外界面动作。创建/quit响应丢失、进程崩溃及500秒实际回收至少在隔离测试服务/设备授权后验证，不能靠sleep或会话列表推断清理。

AIF-02预算维持700–1100产品 / 700–1200测试 / 140–240文档行；若process coordinator、能力矩阵和客户端适配累计明显超过约1200产品改动，先按“Session创建关闭”与“多Session资源隔离”两个可验收行为重新拆分，不删减错误/清理验证。未来SPEC delta主要在根依赖/Automation公开映射与Session契约；按当前进程内范围和串行Runtime退出前提，暂不需要Runtime或Contracts delta。

**Ready阻塞**：Appium-Python-Client 6.0.8 / Selenium 4.51.0版本与限定用途已获用户批准；全部传递依赖锁定核验、实际wheel API、默认/显式timeout、清理、并行systemPort和目标server/driver组合尚未资格验证；真实Appium/设备/APK操作未授权。`app_id`必填及Runtime并发退出仅设为首批串行前提仍需最终设计确认。AIF-01先验收后才能实施AIF-02。

## 10. 拟议 SPEC 影响、设计验证与后续

| 文件 | 未来可能增量；本批不修改 |
| --- | --- |
| 根 SPEC | Automation 公开 Python 映射、已确认平台/公开原则、模块依赖及库选择后的范围 |
| Automation SPEC | Session/设备、目标、观测、执行控制、错误及逐 feature 已确认操作；不写待办与研究日志 |
| Runtime SPEC | 仅 D02 确实需要改变锁/连接资格/使用生命周期时列出 delta；不凭未来设计提前改现状 |
| Contracts SPEC | 只有确认跨模块共同拥有的纯值才新增；Session 生命周期对象和本模块类型不自动搬入 |
| Integrations SPEC | 后续单独确认接入的公开映射；不因本设计承诺 MCP/CLI 同时交付或 daemon |

本设计验收：原需求覆盖可追溯；新决策/建议/同业事实分开；每个操作回答意图、输入、职责、完成/失败；近期 feature 可验证且有预算；候选不冒充批准；官方/库/Runtime 缺口可见；不同接入无需补设备逻辑。

本轮文档验证采用本地链接、表格列数、空白、完整 tracked/untracked 差异与哈希检查；不运行设备或产品测试。设计独审须未参与编写的新上下文实际读取完整文稿、固定依据与完整差异；初轮 full，最多两轮修复复审。独立上下文 `/root/automation_interface_draft_review` 已完成 full 审查，实际核验 19 份固定依据、完整单文件差异及 6 条原始对话消息。F01 指出第 5 节执行阶段划分超出了已确认五原则的具体范围；已修为建议待确认，并保留原稿响应丢失不代表未执行的规则。第 1 轮 repair-only 结论为 **pass / F01 closed**，审核稿 SHA-256 为 `d655bb78afa34e62871d99edd45b7c7a9fa2799c9b98281a856dbaa67613e42f`，完整差异 SHA-256 为 `776772083f08ddf4a388e7352596fc104e161907b971e087f16b2da22bb0ea71`；本次仅追加该审查结果及更新页首状态，不把审核稿哈希冒充追加记录后的全文身份。此结论只覆盖 v0.1 草案一致性，后续实质设计增量仍需相应审查。架构只读子任务因未完成首读预检被停止，无有效研究交付，不作为设计依据。

后续实质增量独立 full 审查由同一独立审查上下文完成，结论 **pass**；实际核对 15 份固定依据和 9 条原始确认消息。审核稿 SHA-256 为 `fa6824ac2f9413642e634bf0e446746435d26e0ab64e1edec3dd46f1c7180edd`，完整差异为 `764e285f696ca1cd40a327e0046f0e3773c34345011ac92b4ee57e5fc9c280fc`；从前次审核稿的累计差异为 `b790f0266af75e76385de9d274106c718af8f2ccaae4564208a9c9bcac8835a9`。审查仅确认新增建议、既有约束及确认状态一致，不批准 D02、库版本、设备操作或 Ready；本段与页首为审查结果追加记录，审核哈希不表示追加后的全文身份。

本次后续实质增量 full 独审结论 **pass**，审核稿 SHA-256 `df34c6fa5d5af6edb334fd16ac31d3909a68c60c04c73cc90c4f5502bd9d53ad`，完整差异 `bda77225d3f34dd0ef8d9f72a49387b154ddf7b76a8589fa2ea89fe742380013`，从 D02 审核稿累计差异 `a43cd099cdc76993f7783791717a3e879f03856ee2a309003526ddab9c4c68fd`。独立核验 11 份固定依据、6 条用户原文、8 份官方研究原文，412 行/73,029 bytes，文档验证通过，无产品/设备运行。本次追加的点击类前置确认及状态记录不在该审核稿哈希内；不以此前审查代替最终设计确认或实际版本资格验证。

Appium 专家研究身份：新上下文 `/root/appium_element_expert`、任务 `AUTO-ELEMENT-EXPERT-01`，任务包 SHA-256 `9fb4964b65ee8784ad0d3e9b4bed980d6ea45a05abb0ffb2a34ab73da74db88b`；首个实际 functions.exec → tools.exec_command 完整读取 9 份 fixed 原文并核验哈希，随后实际读取固定官方页面/源码，正常 final 返回。本次无写入/实验/安装/设备操作；未使用此前无有效交付的 architect 子任务。研究为 Interface 候选提供事实，不代替用户确认、库选型或独立设计审查。第 4.3 节工厂/父 XPath/薄映射及第 5.2 节兼容矩阵均据该研究补充。

用户选择 by/value 后，Tech Lead 另派全新专家上下文 `/root/appium_by_value_expert`、任务 `AUTO-ELEMENT-BYVALUE-EXPERT-02`，任务包 SHA-256 `5ecfc8afeeee25a47e46e53a236f5a45570bcd5e0708b0009a7c56105f09eb8b`；实际首读任务及9份固定原文、哈希匹配，并读取固定官方AppiumBy/查询资料。结论：原样 XPath 可承载调用方的精确 text/属性AND，不需要自造 TEXT/COMPOSITE 或生成器；建议普通查询先评估 ID/ACCESSIBILITY_ID/XPATH 三策略，白名单尚待确认。短ID/package、parent+XPath 和滚动策略限制继续保留，不因精简入口被删除。研究只读，无设备/安装/测试/写入，仍不是依赖或最终接口批准。

Element 增量独立 full 审查结论 **pass**，审核稿 `f91ff04a4e585af35dc25226f3c2cb35368f154cc9fd33892118d76df842c789`（105,749 bytes/576行），完整差异 `2278af8fff8fcb5417935f02d88a0683f70d149001db068b4a6247e95a48f64d`，累计差异 `13ab2d7b788624c749195c207da4adffd8a551dde77ea4d39dc45d8997a7f755`。实际核验13份固定依据、15条原始确认和51条专家真实工具/返回记录，未只采纳摘要。该快照中的关键字工厂仍为建议；用户最新 by/value 选择及本次对应修订不在此审查身份内，不把旧通过当作新稿批准。

by/value-parent增量独立full审查发现F02：兼容矩阵一处仍写父XPath组合待确认，与新确认冲突。已修正并通过第1轮repair-only复审，**F02 closed / pass**；修复审核稿 SHA-256 `aa6fa1e5d07576962b6a44053a91f056bed0017bc4859cc45bf399af8bc24275`（112,978 bytes），完整差异 `ca02ebbb2a3535340d10dba30dd39a2d823f892934390752429457c50eb4108b`，修复增量 `c1f635986ea791cfcef1620d3f2b0eebaebd1e7f49fcc23adfa4e8786fca1641`。实际核验11份固定依据、两条用户原始问答及25条专家真实记录，三份差异重建一致；无产品/设备运行。此次页首和审查记录追加不在审核稿哈希内，审查不是参数全量确认或Ready。

本轮补齐 by/value Element 构造示例、parent解析流程及package边界后，已继续完成第5.3/5.4节系统与应用公开接口表，并更新总表、场景和feature验收轮廓。保留的新增产品取舍为IME目标语义、面板/已有磁贴入口收敛、清数据必要组合和应用选项默认；均为建议，集中评审，不重问已确认能力及正常package规则。Element 创建归属和重定位、by/value方向、parent+XPath首版拒绝、短ID默认Session包名及单次覆盖均沿用确认。

系统/应用研究由Tech Lead实际读取固定官方源码完成，未运行设备/服务/安装/测试。新专家任务 `AUTO-SYSTEM-APP-EXPERT-03` 首读预检失败已停止，无有效研究交付，不把其角色身份或消息当作来源，也未重复启动。实际官方原文和哈希另存本地 `/tmp/aca-auto-interface-design-20261023/system-app/research/manifest.json`，设计中已保留持久官方版本链接与差异说明。当前新增设计增量独审通过，产品取舍仍待确认；跨进程未知占用、预算/取消、具体依赖版本及API资格仍阻塞Ready。最终设计确认前保持草案，只有另行显式 `$spec-driven <已确认设计路径>` 才能进入SPEC gate与实现。

系统/应用实质增量由原独立上下文 `/root/automation_interface_draft_review` 完成 full 审查，结论 **pass，无确定缺陷**；F01/F02保持关闭。审核稿 SHA-256 `2294e6df0891fb77c3709d2ae008fb31c4510e5d56ad7b7b6e2a4684596769d5`（128,407 bytes/669行），完整差异 `765147e6237d72a46a9a8cd4063b1c60c18539beb72192deb041d55c341f193d`，累计差异 `08e77cfd2e28119b0334b138d0bd6dd07fd7dfcaff4842433896134aa5c2f2a7`。实际核对13份固定依据、三份完整差异重建及13份有效官方原文，2处404未用作依据；10个本地链接、表格与空白检查通过。累计文档新增78/删除26行，产品/测试均0，无设备/服务操作。此处及页首为结果追加，审核哈希不冒充追加后全文身份；通过不代表最终批准、Ready或设备验收。
