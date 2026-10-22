# 项目配置

将 [minimal.toml](minimal.toml) 复制到项目中，明确传入文件路径。应用启动时加载一次：

```python
from appium_connect_agent.configuration import ConfigurationError, load_configuration
from appium_connect_agent.runtime import Runtime

try:
    loaded = load_configuration("appium.toml")
except ConfigurationError as error:
    for issue in error.issues:
        print(issue.source, issue.field, issue.code, issue.message)
    raise

runtime = Runtime(loaded.settings)
for source in loaded.sources:
    print(source.field, source.source, source.config_file)
```

`Runtime(...)` 这里只构造对象。加载成功仅表示配置有效，不表示工具、环境、服务或设备就绪。
本例不会启动、诊断或连接 Appium；连接需要已启动的本地服务和明确配置的地址。

只支持可选 `[runtime]` 表，字段均可省略；未填写时删除整行，不要填空字符串。
空文件、仅注释文件或空 `[runtime]` 都有效，全部字段为 `None`、来源为 `default`。

| 字段 | TOML 值 | 说明 |
| --- | --- | --- |
| `appium_executable` | 路径字符串 | Appium 可执行文件 |
| `appium_home` | 路径字符串 | Appium home 目录 |
| `node_executable` | 路径字符串 | Node 可执行文件 |
| `npm_executable` | 路径字符串 | npm 可执行文件 |
| `java_home` | 路径字符串 | Java home 目录 |
| `android_sdk_root` | 路径字符串 | Android SDK 根目录 |
| `server_url` | URL 字符串 | HTTP loopback 地址，必须带端口；不提供默认地址 |

例如，在配置文件中加入 `appium_home = "./tools/appium"`。六项工具路径可为绝对路径，
相对路径以本次指定配置文件的目录为基准；不会检查工具是否存在，也不会解析工具符号链接。
通过配置文件符号链接加载时仍以指定链接的目录为基准，保留路径中的 `..`。
不支持 `~`、`$NAME`、`${NAME}` 或 `%NAME%` 占位，请填写具体路径。

`server_url` 沿用 `LocalSettings` 校验：只支持本地 HTTP loopback、明确端口和安全 base path，
例如 `http://localhost:4723/wd/hub`；输出会规范化 localhost 和尾斜线。
不支持远程地址、HTTPS、认证、查询或 fragment。

配置文件路径可为字符串或 `Path`，相对路径以调用加载入口时的工作目录为准。
只读取明确指定的一份 UTF-8 普通文件，最大 1 MiB；文件缺失或不可读时明确报错。
不会搜索配置、读取环境变量、写回文件或监听变更。

未知字段、非字符串值、空字符串和非法 URL 都会整份加载失败。TOML 语法或编码错误
先报告解析问题；语法正确时，`issues` 集中列出能够确定的字段问题。问题仅包含来源、
字段、错误码和修正提示，不复制字段原值。

`loaded.config_file` 是所选文件的绝对路径；`settings` 是唯一 Contracts `LocalSettings`。
`sources` 为七个字段各保存一条来源，`file` 指向该文件，`default`/`override` 没有文件。
返回值、设置和来源均不可变。修改 TOML 不会改变已持有的快照；重启读取配置的应用时
重新加载即可，不需要由本库重启 Appium。

## Python 参数覆盖

同一入口支持七个同名关键字参数，优先级为：明确参数值 ＞ 文件值 ＞ 默认 `None`。
只传需要替换的字段，其他字段保留文件值；文件仍必须存在且可读。

```python
from pathlib import Path

from appium_connect_agent.configuration import load_configuration

loaded = load_configuration(
    "appium.toml",
    appium_home=Path("./tools/appium"),
    server_url="http://localhost:4724/",
)
assert loaded.settings.server_url == "http://127.0.0.1:4724"
source = next(item for item in loaded.sources if item.field == "server_url")
assert source.source == "override"
assert source.config_file is None
```

前六个路径参数接受字符串或 `Path`，`server_url` 只接受字符串。
相对参数路径仍以指定配置文件的目录为基准，不受调用时其他路径值影响；
路径对象同样不检查存在性，不解析符号链接，不展开 home 或变量占位。

省略参数表示保留原值。显式 `None`、空字符串和错误类型都会报错，
不能通过它们临时清除文件设置；无需覆盖时直接省略该参数。

文件先读取并解析；读取、编码或 TOML 语法错误会先停止加载。
文件可解析后，文件和参数各自校验，`issues` 聚合两处能够确定的问题；
正确参数不能掩盖错误文件。参数问题的来源为 `argument`，字段名不带 `runtime.` 前缀。

空文件也可以通过参数提供设置：

```python
# empty.toml 是调用方已创建的空文件。
loaded = load_configuration("empty.toml", server_url="http://127.0.0.1:4723")
```

覆盖只作用于本次返回的快照，不写入 TOML。无 `server_url` 时仍不提供默认地址；
空文件加参数加载成功同样不表示服务或设备就绪。
