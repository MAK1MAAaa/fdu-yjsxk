# fdu-yjsxk

复旦大学研究生选课系统的串行选课辅助脚本，支持定时多课程选课、单课程捡漏、浏览器 Cookie 读取和登录态自检。

提交返回受理号不代表选上：脚本查询该受理号的最终结果，再处理下一门课程。最终结果请到选课系统的“已选课程”页核对。

## 当前版本

- 仅支持串行，`serial_mode` 必须为 `true`。请勿同时启动多个选课窗口。
- 交互请求间隔允许 **0.1—60 秒**；回车沿用个人 `config.json`，代码缺省值为 **0.8 秒**。
- 不包含多线程试验、1ms/10ms 交互间隔或超过 1 秒的后台刷新功能。
- 自动读取 Cookie 不等于自动登录；登录过期后需在浏览器重新登录。

## 快速开始

需要 uv；项目声明 Python 3.9+，依赖由 `pyproject.toml` 和 `uv.lock` 管理。

```bash
uv sync --locked
```

1. 首次使用将 `config.example.json` 复制为 `config.json`，已有个人配置不要覆盖。
2. 填写课程信息、`target`、`start_time` 和 `end_time`。示例日期不会自动更新。
3. 在 Edge 或 Chrome 登录与 `target` 一致的选课系统，确认浏览器能打开选课页。
4. 先运行自检，再启动对应选课模式。

| 用途 | macOS 双击入口 | Windows 双击入口 |
|---|---|---|
| 登录态自检 | `先跑自检.command` | `先跑自检.bat` |
| 定时多课程选课 | `一键抢课.command` | `一键抢课.bat` |
| 单课程捡漏 | `单课程捡漏.command` | `单课程捡漏.bat` |

以上双击启动器统一位于 `scripts/` 目录。启动器通过 uv 使用锁定依赖。macOS 一键抢课先执行自检，通过后询问间隔。
入口、配置和日志按项目根目录定位，从其他目录运行绝对路径入口也可使用。

## 命令行

### Selenium 自动登录（可选）

在 `scripts/` 中打开 `自动登录.command` 或 `自动登录.bat`，也可运行：

```bash
uv run --locked --extra login python -m fdu_yjsxk.selenium_login
```

首次运行可能需要下载浏览器驱动，需已安装 Edge 或 Chrome。实现使用
[Selenium WebDriver](https://www.selenium.dev/documentation/webdriver/browsers/edge/)。
可将 `.env.example` 复制为 `.env`，填写 `FDU_USERNAME` 和 `FDU_PASSWORD`；
没有凭据时在新打开的独立浏览器中手动登录。不要把密码放进命令行或提交 Git。

脚本从选课页面进入当前认证流程，只在 `https://id.fudan.edu.cn` 自动填写凭据，
最多尝试提交一次。表单无法识别、验证码和二次验证需手动完成，等待上限 180 秒。
脚本等待账号密码框可交互，校验填写结果后明确点击“登录”按钮；填写期间页面重绘会继续等待。
终端显示凭据是否加载、当前域名及填写阶段，但不显示密码或认证链接参数。
不保证所有登录方式都能自动完成；真实账号登录结果仍需核对。

取得选课 Cookie 后请求主页验证 Token；通过后原子更新 `cookie.txt`，不提交课程。
该入口使用独立临时浏览器，不读取或覆盖日常 Edge 配置；退出时关闭浏览器。
后续选课请将 `config.json` 的 `cookie_source` 设为 `file` 并先自检，避免 `auto`
优先读取日常浏览器中的旧 Cookie。原串行入口不会在后台自动拉起 Selenium。

### 登录后导出课程列表

双击 `scripts/自动登录.command` / `.bat` 会在登录后尝试自动采集课程。
命令行使用：

```bash
uv run --locked --extra login python -m fdu_yjsxk.selenium_login --export-courses
```

- `exports/course-list.json`：专门保存课程清单，包含可识别课程、分类待核对条目及采集提示；成功导出后原子更新。
- `web/catalog/`：可复用课程工作台，`index.html`、`styles.css`、`app.js` 分别负责页面、样式和交互，不内嵌个人课程数据。
- `exports/config-courses-时间戳.json`：仅含 `courses` 的候选片段，不是完整配置；所有课程默认 `enabled: false`。

先切换公共课/学科专业课一级标签，再按 `tabwid` 读取六个子分类表格；当前这两类页面不启用分页。
不会点击选课或退课按钮，不会覆盖 `config.json`。先核对清单及提示，再将目标条目复制到配置、调整顺位并启用。
无法确认 `lx` / `bqmc` 的条目只放入 `unresolved`，不加入候选配置。
`exports/` 已加入 Git 忽略。已通过有效会话在线验证；范围为六个子分类，不包含公选、重修和其他课程。
清单的 `categories` 记录分类加载状态和行数；空表不推断为接口失败，也不代表全校没有该类课程。

双击 `scripts/查看课程列表.command`（Windows 使用同名 `.bat`），或运行：

```bash
uv run --locked python -m fdu_yjsxk.catalog_server
```

浏览入口自动打开本机页面，仅监听 `127.0.0.1` 的空闲端口。没有 JSON 时不展示课程，
每 3 秒检查本地文件；采集成功后自动渲染，后续更新会清空旧勾选。无需重新生成 HTML。
服务只开放页面和课程 JSON，不提供项目目录、配置或 Cookie。关闭终端或 Ctrl+C 停止服务。
静态资源仅开放固定的 `styles.css` 和 `app.js`，不开放任意文件路径。
手动载入 JSON 会暂停自动更新，刷新页面恢复。当前仅维护可复用工作台，不再提供内嵌数据 HTML 生成器。

工作台支持以下筛选，条件可叠加：

- 公共课 / 专业课大类筛选。
- 分类标签与下拉框联动：政治、第一外国语、专业外语、学位基础、学位专业、专业选修；标签显示当前大类内的教学班数量，包括空分类。
- 课程名、教师、代码、地点搜索，容量筛选，以及隐藏时间冲突。
- 重置筛选不清空勾选；跨分类勾选后可统一复制，新增清单则清空勾选，避免混用旧数据。

复制的条目只含 `name`、`kcdm`、`bjdm`、`lx`、`bqmc`、`enabled`，名称包含教师，
`enabled` 为 `true`。复制片段末尾带逗号，作为 `courses` 数组最后一项时需删除该逗号。
批量复制按清单顺序输出（包括筛选前已勾选的课程），粘贴后请自行调整顺位。
页面显示采集时的容量和冲突，不会刷新实时状态、提交选课或修改配置。

### 常规选课命令

```bash
# 自检：读取 Cookie、请求主页并检查 Token，不提交选课
uv run --locked python grab.py --dry-run

# 按配置时间和课程顺位运行
uv run --locked python grab.py

# 交互设置本次间隔，仍沿用配置起止时间
uv run --locked python grab.py --ask-interval

# 跳过开始时间，但不延长截止时间
uv run --locked python grab.py --now

# 选择一门课、时长和间隔，然后立即捡漏
uv run --locked python grab.py --single

# 包入口与 grab.py 等价
uv run --locked python -m fdu_yjsxk --help
```

`--probe` 会发送真实选课请求，不是只读自检；不要用它代替 `--dry-run`。
`--force` 配合 `--probe` 使用。`--single` 请单独使用。

### 单课程捡漏

菜单来自本地配置，只显示启用且未标记 `selected: true` 的课程，不查询实时余量。
运行时长允许 1—1440 分钟，默认 120 分钟。任一选择步骤输入 `0` 可取消。

确认间隔后直接串行提交所选课程；选上、系统提示已选或到时停止。
本次时间与间隔只在内存中生效，不修改配置文件。正常结束后在终端汇总结果和耗时。

## 配置

完整字段说明见 [config.example.json](config.example.json)。

| 字段 | 含义 |
|---|---|
| `target` | 与浏览器登录域名一致的选课域名 |
| `start_time` / `end_time` | 本次运行的本地开始/截止时间，须检查日期 |
| `courses` | 课程数组；普通模式按数组顺序处理启用课程 |
| `request_interval` | 请求处理后的等待秒数，不是固定请求速率 |
| `round_interval` | 轮次额外等待；`0` 表示不额外等待 |
| `homepage_refresh_secs` | 安全轮次边界按需刷新主页的最短间隔 |
| `cookie_refresh_secs` | 重新读取 Cookie 的间隔 |
| `cookie_source` / `browser` | Cookie 来源模式和浏览器，例如 `auto` / `edge` |
| `http_timeout` | HTTP 超时设置，不是整个请求严格的墙钟上限 |
| `poll_interval` / `poll_max` | 受理号查询间隔与每次调用内的查询次数 |
| `full_max_tries` | 单门满额重试上限；`0` 表示不限次数，仍受截止时间限制 |

`name` 用于显示，`bjdm` 是实际教学班代码，`lx` 和 `bqmc` 为系统分类参数。
请从当前学期页面或网络响应核对这些值，不能仅凭课程名称推断班号。
不需要继续选的课程应设为 `enabled: false`；`selected` 标记仅用于单课程菜单筛选。

自动 Cookie 模式只在浏览器读取失败时尝试 `cookie.txt`。个人配置可能与示例不同。
配置不支持热更新，修改后需停止旧进程再重新启动。不要提交个人配置和登录凭据。

## 等待、刷新与结果判定

- 定时等待期间提前预热；最后 5 秒避免开始常规刷新。
- 定时开始或缓存恢复后的首 5 秒暂缓常规刷新；Token 缺失或明确失效时仍恢复。
- 收到每日缓存提示后等待 13:00，从第一顺位重试；13:00 后仍提示缓存时至少等待 0.8 秒再检查。
- 满额按间隔继续重试；网络或服务异常按 1、2、4、8、12 秒退避，并尊重 `Retry-After`。
- 已取得受理号时继续查询同一请求，结果未知时暂不提交其他课程。
- 提交断网且未取得受理号时，结果可能未知，必须核对已选列表。

缩短间隔不会取消缓存等待、网络超时或退避，也不保证提高成功率。
已发出的请求可能在截止后才返回，过期配置不会自动顺延到次日。

## 日志与常见问题

普通模式追加写入根目录 `grab.log`；单课程捡漏仅输出终端，不保存日志。
按 `Ctrl+C` 可停止。退出码 `0` 也可能表示启动前取消，不能单凭退出码判断选课成功。

| 现象 | 检查方式 |
|---|---|
| `Unable to read database file` | 确认浏览器登录；macOS 为实际启动脚本的终端开启完全磁盘访问权限，彻底退出后重开 |
| 登录跳转、Cookie 无效或 Token 缺失 | 检查域名，在浏览器重新登录后自检 |
| `ConnectTimeout` / `ReadTimeout` | 检查网络、代理及浏览器访问；不能仅据此认定是间隔导致 |
| 持续满额 | 本次请求被拒绝，不代表程序故障，也不能判断期间是否出现过余量 |
| 启动后立即退出 | 检查截止日期和启用课程列表 |

日志不输出 Cookie 或 Token 值，分享截图和配置前仍应检查敏感信息。

## 目录结构

```text
fdu-yjsxk/
├── grab.py                    # 兼容入口
├── scripts/                   # 双击启动器
│   ├── 一键抢课.command / .bat # 定时入口
│   ├── 单课程捡漏.command / .bat # 单课程入口
│   ├── 先跑自检.command / .bat # 自检入口
│   ├── 自动登录.command / .bat # 登录并采集课程
│   └── 查看课程列表.command / .bat # 启动可复用工作台
├── web/catalog/               # 课程工作台：HTML / CSS / JavaScript
├── exports/                   # 本地课程清单与配置候选，Git 忽略
├── fdu_yjsxk/                 # Python 业务模块
│   ├── cli.py / __main__.py   # 常规选课入口
│   ├── client.py / runner.py  # HTTP 请求与串行调度
│   ├── single.py             # 单课程捡漏
│   ├── selenium_login.py     # 浏览器登录与 Cookie 保存
│   ├── course_catalog.py     # 分类采集与 JSON 导出
│   ├── catalog_server.py     # 本机只读课程工作台服务
│   └── settings.py / cookies.py / diagnostics.py / errors.py / logging.py
├── tests/                     # 离线回归测试
├── docs/
│   ├── README.md              # 文档索引
│   ├── 使用说明.md            # 详细操作说明
│   └── archive/               # 历史说明及课程规划
├── config.example.json        # 配置模板
├── config.json                # 个人配置，Git 忽略
├── .env.example               # 自动登录凭据模板；真实 .env 不提交
├── cookie.txt / grab.log      # 本地凭据和日志，Git 忽略
└── pyproject.toml / uv.lock    # 依赖声明与锁文件
```

操作细节见 [使用说明](docs/使用说明.md)，历史资料见 [文档索引](docs/README.md)。
历史课程规划不代表当前开课情况或个人配置。

目录维护约定：业务模块放 `fdu_yjsxk/`，所有双击入口放 `scripts/`，
静态页面放 `web/catalog/`，本地生成数据放 `exports/`。不要把运行结果混入源码目录。
`grab.py` 和包入口仍用于兼容已有命令；`.venv/` 是当前运行环境，不作为无用文件清理。
个人 `.env`、`config.json`、`cookie.txt`、`grab.log` 及历史资料保留，不随代码清理删除。

## 开发验证

```bash
uv run --locked python -B -m unittest discover -s tests -v
```

测试使用模拟响应，不登录、不提交真实选课。

## 来源与使用提醒

项目基于 [JarynWong/fdu_course_enrollment](https://github.com/JarynWong/fdu_course_enrollment) 的思路重写。
请遵守学校规则，控制请求频率，避免给服务器造成额外压力。本工具不保证选课成功。
本仓库未提供独立的 LICENSE 文件，不在此作额外授权声明。
