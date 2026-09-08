# fdu-yjsxk · 复旦大学研究生选课脚本

一个用于复旦大学研究生选课系统的串行选课辅助程序，当前配置使用 `yjsxk.fudan.sh.cn`。

## 项目结构

```text
fdu-yjsxk/
├── grab.py                      # 兼容旧命令与双击启动器的入口
├── fdu_yjsxk/                   # Python 实现
│   ├── cli.py / __main__.py     # 命令行入口与退出码
│   ├── settings.py              # 根目录路径、配置加载和校验
│   ├── cookies.py               # 浏览器与文件 Cookie 读取
│   ├── client.py                # HTTP 会话、Token、提交与轮询
│   ├── runner.py                # 串行调度、定时等待与恢复
│   ├── single.py                # 单课程菜单与临时运行配置
│   ├── diagnostics.py           # 自检与单次链路演练
│   └── errors.py / logging.py   # 异常分类与日志
├── tests/                       # 离线回归与入口兼容测试
├── docs/
│   ├── 使用说明.md              # 当前操作说明
│   ├── 选课备选方案与课程表.md  # 历史规划记录
│   └── archive/                 # 旧版说明存档
├── config.json                  # 个人配置，不提交 Git
├── config.example.json          # 配置字段示例
├── cookie.txt / grab.log         # 本地凭据与运行记录，不提交 Git
├── 一键抢课.command / .bat      # 原有 macOS / Windows 双击入口
├── 单课程捡漏.command / .bat    # 数字选择一门课，立即开始捡漏
├── 先跑自检.command / .bat
└── pyproject.toml / uv.lock      # 依赖声明与锁文件
```

日常操作见 [使用说明](docs/使用说明.md)，课程规划见
[选课备选方案与课程表](docs/选课备选方案与课程表.md)。
启动器、配置和日志都按项目根目录定位，从其他目录运行绝对路径入口也能找到原配置。
当前版本只保留串行调度，`serial_mode` 须为 `true`。

本项目基于 [JarynWong/fdu_course_enrollment](https://github.com/JarynWong/fdu_course_enrollment) 重写。
原脚本基于 2024 年的选课协议，在 2026 年的系统上已多处失效，本仓库按当前系统的真实接口逻辑
重新实现，并补上了原版缺失的一键 Cookie 读取、串行选课、链路自检等能力。

## 与原版的区别

| | 原版 course.py | 本仓库 grab.py |
|---|---|---|
| csrfToken 提取 | `value='...'` 单引号，已失效 | 兼容单/双引号，实测可用 |
| 选课结果判定 | `code!=0` 就当成功 | 两步异步：提交拿 `xid` → 轮询 `code==1` 才算选上 |
| Cookie | 手动 F12 复制 | 自动读浏览器本地库（含 HttpOnly） |
| 多门课 | 一轮全提交 | 串行：确认当前受理号结果后再提交下一门 |
| 配置 | 改源码里的全局变量 | 独立 `config.json`，不用动代码 |
| 自检 | 无 | `--dry-run` 环境自检 |

## 环境要求

- **[uv](https://docs.astral.sh/uv/getting-started/installation/)**（负责 Python 环境与依赖管理）
- **Python 3.9+**（推荐 3.10 ~ 3.13，3.13 实测可用；未安装时 uv 可自动下载）
- 依赖声明在 `pyproject.toml`，版本锁定在 `uv.lock`

```bash
uv sync --locked
```

## 快速开始

> ⚠️ **重要：无论用哪种方式，跑「自检」之前，都必须先在浏览器登录一次选课系统，并保持登录状态。**
> 脚本是自动从浏览器里读你的登录 Cookie 来访问选课系统的，没登录的话自检会直接报「Cookie 无效」。

### 第 0 步：登录选课系统（必做，先于一切）

用 **Edge 或 Chrome** 打开与 `config.json` 中 `target` 一致的选课域名，用统一身份认证（UIS）账号登录，
进入选课页面。**登录后别关闭浏览器、别退出登录**，脚本会自动从浏览器里读取 Cookie。

### 一键双击（推荐）

登录后，双击对应脚本即可：

| 平台 | 自检（先跑） | 抢课 |
|---|---|---|
| macOS | 双击 `先跑自检.command` | 双击 `一键抢课.command` |
| Windows | 双击 `先跑自检.bat` | 双击 `一键抢课.bat` |

> macOS 首次双击 `.command` 若被系统拦截，右键 →「打开」即可。
> `.command` / `.bat` 会检查 uv，并通过锁文件自动同步环境后运行。

如果 macOS 自检提示 `Unable to read database file`，请到「系统设置 → 隐私与安全性
→ 完全磁盘访问权限」中允许“终端”，彻底退出并重新打开终端后再运行自检。

### 命令行

```bash
# 1. 按锁文件创建环境并安装依赖
uv sync --locked

# 2. 在浏览器登录一次选课系统（Edge 或 Chrome），保持登录

# 3. 自检（不会提交任何选课请求）
uv run --locked python grab.py --dry-run

# 4. 抢课（会等到 config.json 里的 start_time 再开始）
uv run --locked python grab.py
```

## 命令行参数

```bash
uv run --locked python grab.py             # 正常跑，等到 start_time 开始
uv run --locked python grab.py --dry-run   # 环境自检，不发请求
uv run --locked python grab.py --now       # 忽略 start_time，立即开始
uv run --locked python grab.py --probe     # 链路演练：发 1 次真实请求看服务器回什么
uv run --locked python -m fdu_yjsxk --help # 包入口；支持相同参数
```

运行输出会同时追加到项目目录下的 `grab.log`，方便事后排查服务器返回结果。

## 配置

所有配置都在 `config.json` 里，关键项：

```jsonc
{
  "target": "yjsxk.fudan.sh.cn",         // 与浏览器登录域名一致
  "start_time": "2026-09-07 12:59:56",   // 每次运行前更新日期和时间
  "end_time": "2026-09-07 14:59:56",     // 截止后不再发起新请求
  "cookie_source": "auto",               // 浏览器读取失败时才回退 cookie.txt
  "browser": "edge",                     // 从哪个浏览器读 Cookie
  "cookie_refresh_secs": 240,             // 定期重新读取浏览器 Cookie
  "homepage_refresh_secs": 1.0,           // 轮次边界检查主页刷新间隔
  "request_interval": 0.8,                // 同一轮各课程请求间隔
  "round_interval": 0,                    // 正常轮次连续执行，不额外等待
  "serial_mode": true,                   // 一门一门来，务必保持 true
  "full_max_tries": 0,                   // 满额不限次数，仍受 end_time 约束
  "courses": [
    // name / bjdm / lx / bqmc / enabled
  ]
}
```

- `bjdm`（班级代码）格式为 `学年学期 + 课程代码 + .班号`，需要到选课系统抓取，不同年级前缀不同。
- `lx` / `bqmc` 是选课系统的分类编码，已在脚本内说明对应关系。
- `enabled: false` 的课程不参与抢课。
- `round_interval: 0` 取消额外轮次等待；各课程之间仍保留 `request_interval`。
- `homepage_refresh_secs` 是最短刷新间隔，在安全的轮次边界按需检查，不是后台每秒独立发请求；已受理请求等待结果时不刷新 Token。定时开始或缓存恢复后的首 5 秒暂缓常规刷新，Token 缺失或明确失效时仍恢复。
- `full_max_tries: 0` 表示满额无限重试直到截止；正整数只限制对应课程，达到上限不会算作选课成功。
- `cookie_source: auto` 只在浏览器 Cookie 读取失败时尝试本地 `cookie.txt`。登录过期仍需在 Edge 重新登录；脚本会读取更新后的 Cookie。
- 服务端返回的新 Cookie 由 Session 保存；浏览器 Cookie 未变化时不覆盖它。日志不输出 Cookie 或 Token 值。
- 截止时间会在每门课和每次轮询前检查，等待及网络超时参数受剩余时间限制；已经发出的请求可能在截止后才收到响应。过期配置不会自动顺延到次日。

### 2026-09-07 日志复盘与重试策略

最近一次运行从 12:59:56 开始，到 13:02:01 汇总退出，共记录 148 次提交拒绝：
10 次“数据缓存中”、138 次“容量已满或退选席位暂未释放”。每门课约 3.4 秒一次，
已无 30 秒轮次空档；该次运行没有网络或登录异常，也未记录成功受理。
日志只能说明每次请求时服务器拒绝选课，不能判断期间是否曾有名额被其他人选走。

1. 收到每日缓存提示后中断本轮，保留 Token，等待到 13:00 再从第一顺位开始；提前预热，避免恢复时无条件刷新主页。13:00 后仍收到缓存提示时按课程间隔（至少 0.8 秒）短暂等待并继续检查，不顺延到次日。
2. 满额属于正常重试，保持连续串行请求；只有网络故障或服务暂不可用才进行 1、2、4、8、12 秒退避，并尊重服务器的 `Retry-After` 秒数。
3. HTTP 503、代理超时不再触发重新读取 Cookie；认证/CSRF 错误才进入登录态恢复。
4. 已取得受理号但尚无最终结果时保留同一受理号继续查询，暂不提交其他课程；只有明确成功或明确已选才移出待抢列表。提交阶段如果断网且未取得受理号，结果可能未知，最终须核对“已选课程”。
5. 当前配置优先级：温旭 `GEIP40015.11` → 徐志宏 `GEIP40017.04` → 数据库 → 高级软件开发。温旭班为 2 学分，周四 6–7 节、江湾 JB201，与原李健班时段相同。

离线回归测试（模拟时钟和服务器响应，不登录、不提交选课）：

```bash
uv run --locked python -B -m unittest discover -s tests -v
```

### bjdm 怎么获取

`bjdm` 是唯一不能凭空填的字段，必须从选课系统抓。它是选课接口真正要传的班级代码，格式固定为：

```
学年学期前缀(10位) + 课程代码 + . + 班号
例如：2026202701CS50014.01
      └─前缀─┘└─课码─┘└班号┘
```

获取方法（在已登录选课系统的浏览器里）：

1. 按 `F12` 打开开发者工具，切到 **Network（网络）** 面板。
2. 在选课系统里点「查询课程」或刷新课程列表，让课程数据加载出来。
3. 在网络请求里找到 `loadKcxx.do`、`loadXkjg.do` 之类返回 JSON 的接口，点开它的 **Response（响应）**。
4. 每个课程对象里就带 `bjdm`（班级代码）、`kcdm`（课程代码）、`lx`、`bqmc` 这些字段，照着填进 `config.json`。

> 提示：`kcdm` 就是课程代码（如 `CS50014`），拿到后 `bjdm` 其实就是「前缀 + 课程代码 + 班号」拼出来的，
> 前缀对同一年级是固定的。

### 让 AI 自动读浏览器、生成 config.json

如果不想手动 F12 一条条抄，可以让 AI 控制浏览器直接读取课程信息，自动帮你写好 `config.json`。
前提是你已经在用带浏览器自动化能力的 AI（如 WorkBuddy + bsk 扩展）。

**工作方式**：脚本会自动从浏览器读登录 Cookie 来访问选课系统，同样地，AI 也能控制浏览器
打开选课页面、读取课程列表，再把每门课的 `name` / `kcdm` / `bjdm` / `lx` / `bqmc` 填进 `config.json`。

**操作步骤：**

1. 先确认浏览器扩展已连接、AI 能控制浏览器（例如在 WorkBuddy 里装好 bsk 扩展，状态为绿色已连接）。
2. 确保浏览器已经登录选课系统，并且**能正常打开选课页面**（校外需先挂校园网/VPN，见下方警告）。
3. 直接对 AI 说一句，例如：

   > “帮我打开选课系统，读取我要抢的那几门课的班级代码，写进 config.json。”

4. AI 会打开选课系统 → 读取课程列表 → 按课程名/老师/上课时间匹配 → 生成或更新 `config.json`。

**为什么推荐这么干**：`bjdm` 是选课接口真正要传的班级代码，手抄容易错（尤其是班号 `.01`/`.02`/`.03`），
AI 直接读原始数据能保证一字不差，还能顺带核对课程容量、把难抢的课排在前面。

> ⚠️ **前置条件**：选课系统 `yjsxk.fudan.edu.cn` 是校内系统，校外直连会连不上（`28.0.0.39` 是校内网段）。
> 无论手动抓还是让 AI 抓，都**必须先能访问选课系统**——在校外需要先连校园网或学校 VPN。
> 否则浏览器会报 `ERR_CONNECTION_CLOSED`，AI 也读不到任何内容。

## 为什么是一门一门选

本项目采用“提交一门 → 根据该受理号确认结果 → 再提交下一门”的流程，
结果未知时继续查询原受理号。课程在 `courses` 数组中的顺序就是处理优先级。
当前只支持串行配置，不据此推断学校服务端是否支持并发。

## 免责声明

- 本程序仅供学习交流，功能仅为辅助选课，**存在抢课失败的可能**。
- 请控制请求频率、及时停止程序，**避免给学校服务器带来过大压力**。
- 请遵守学校相关规定，使用本程序产生的任何后果由使用者自行承担。

## 许可

本项目为重写实现，代码可自由参考。原项目 [JarynWong/fdu_course_enrollment](https://github.com/JarynWong/fdu_course_enrollment)
未附带 LICENSE，如需使用原版代码请自行联系原作者。
