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
不会搜索配置、读取环境变量、写回文件或监听变更；当前入口没有参数覆盖。

未知字段、非字符串值、空字符串和非法 URL 都会整份加载失败。TOML 语法或编码错误
先报告解析问题；语法正确时，`issues` 集中列出能够确定的字段问题。问题仅包含来源、
字段、错误码和修正提示，不复制字段原值。

`loaded.config_file` 是所选文件的绝对路径；`settings` 是唯一 Contracts `LocalSettings`。
`sources` 为七个字段各保存一条来源，`file` 指向该文件，`default` 没有文件。
返回值、设置和来源均不可变。修改 TOML 不会改变已持有的快照；重启读取配置的应用时
重新加载即可，不需要由本库重启 Appium。
