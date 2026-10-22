# AGENTS.md — trae-checkin AI 交接文档

> 给后续 AI / 新会话快速接手用。这里只写 README 查不到的坑、实测结论和约束。
> 核心原则：**修改代价最小化**，只浏览相关模块，不整仓扫读。
> **脱敏硬规则**：代码、文档、提交信息中不得出现成员真名，一律用「账号1~4」「成员」等指代（飞书表格里的数据除外）。

## 项目一句话

TraeCode/TraeWork 每日自动签到：GitHub Actions 定时（北京时间 00:23 / 20:42，分钟数刻意避开整点高峰，实际执行常有延迟属正常）运行 `trae_checkin.py`，按飞书多维表格里的多账号凭证签到领积分，写日志表 + 发飞书卡片。

## 文件与职责

| 文件 | 职责 | 注意 |
|---|---|---|
| `trae_checkin.py` | 主签到脚本（Actions 跑） | 签到/卡片/日志逻辑都在这 |
| `collect_account_info.py` | 采集本机客户端登录态并自动推送表格 | **改动后必须 `cp` 同步到 `trae-collect-win/`** |
| `feishu_bitable.py` | 飞书表客户端 | 无 requests 时自动退化为 urllib 垫片；单条更新必须 PUT |
| `setup_bitable.py` | 表字段初始化 | 同样需同步 Win 副本 |
| `trae-collect-win/` | Windows 免安装采集包 | 便携 Python 为 embeddable 发行版；bat/txt 为 GBK 编码 |
| `一键采集.command` | Mac 双击入口（等效 bat） | UTF-8；零依赖（系统 python3 + openssl 兜底 + urllib 垫片）；分发给其他 Mac 需 `xattr -d com.apple.quarantine` 去 Gatekeeper 拦截 |
| `.github/workflows/daily-checkin.yml` | 定时任务 | 凭证全部走 Actions secrets（FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_ACCOUNT_TABLE / FEISHU_BITABLE_LOG_TABLE / 飞书 webhook 及两个跳转 URL） |

## 关键实测结论（逆向验证过，勿凭猜测推翻）

1. **Token 生命周期**：JWT 约 14 天，RefreshToken 约 180 天。客户端每 ~12-14 天自动续期一次（或重登/升级），每次都会把表格里存的旧 RT 顶掉 → **活跃账号约 1-2 周失效一次属预期行为**，不是故障。恢复 = 该账号在其客户端机器上重跑一次采集脚本（按用户ID自动回填），无需排查。
2. **简单版 ExchangeToken**（脚本现用的）只返回服务端缓存的 JWT，不续期、不消耗续期链。签名版续期已逆向验证可行（本地 `diag_signed_exchange.py`，含设备密钥已 gitignore 勿入库），但会与客户端抢续期链，故未启用——只适合"不再天天用客户端"的账号。
3. **签到状态接口**完整返回仅 5 个字段：`checked_in / did_checked_in / credits / extra_credits / enable`。**`credits` = 该账号当日签到所得数字（领取前后不变，每账号不同）**，本次获得积分直接取它即可（v2.3.4–v2.5.1 用"领取前后差值"恒得 0，日志表里一周的成功记录全 0 即此教训）。`extra_credits`（实测 100）暂不参与；若发现某账号实际到账 = credits + extra_credits，一行改公式。领取响应本身不含积分字段。
4. **飞书 API 两个坑**：① 单条记录更新官方方法是 **PUT**，PATCH 会被网关直接 404（纯文本 `404 page not found`），json 解析会报出误导性的 "Extra data"；② 非 JSON 响应现已统一报「HTTP 状态码 + 响应内容」。
5. **推送匹配规则**：按「用户ID」字符串严格相等匹配行；`--name` 仅用于新账号建行或改名；匹配不到就新建一行。表格里账号名称与 --name 大小写不同会各自成行（历史遗留，勿用名称做匹配键）。
6. **Windows 便携包**：embeddable Python 的 `._pth` 文件**不把脚本目录加进 sys.path**，同目录 import 会报 No module named → `push_to_bitable` 已手动补。**Mac 上测不出此问题**，复现方法见下。
7. **GBK 编码**：`trae-collect-win/` 的 bat 和 txt 是 GBK+CRLF（中文 Windows 原生格式）。**绝不能用编辑器或默认 UTF-8 的工具打开后保存**；要改就用 Python 以 `gbk` 编码字节重写（`open(p,"wb").write(s.encode("gbk"))`）。
8. **飞书凭证**：真实配置只存一份 `trae-collect-win/feishu_config.json`（含 App Secret，已 gitignore 不入库）；主目录脚本会自动回退到该子目录查找；环境变量优先于配置文件；模板 `feishu_config.example.json` 入库。

## 固定坐标

- 仓库：`github.com:niupengfeia/trae-checkin.git`（main，直接 push 即交付，不走 AIMD）
- 多维表格「TraeCode 签到管理」：base `SY5ubBKnGavDghssJZNcRy1wnwb`
  - 账号列表：`tblde0WP7zCS1BzI`（4 个成员账号，回填按「用户ID」列匹配，不用看账号名称）
  - 签到日志：`tblaEEwA79KSq3cw`（关键字段：状态=成功/已签到/失败，本次获得积分：成功=实际领取值，已签到/失败=0）
- 卡片：标题带「· X/N 成功」；头部红（有失败）/绿（有领取）/蓝（全已签）动态；时间**固定北京时间**（Actions 服务器是 UTC，用 `gmtime(ts + 8*3600)`，不能用 localtime）

## 验证手法（Mac 上模拟目标环境）

- **卡片/推送逻辑**：monkeypatch `trae_checkin.requests.post` 捕获 payload，不真发消息
- **Windows ._pth 环境**：清空 sys.path 中相关目录 + `importlib.util.spec_from_file_location` 按路径加载模块，再调 `push_to_bitable`（记得先设 4 个 dummy FEISHU_* 环境变量，防止读到真实配置碰真实表格）
- **Actions UTC 时区**：`os.environ['TZ']='UTC'; time.tzset()`
- **读 GBK 文件**：`iconv -f GBK -t UTF-8` 或 Python decode

## 运维模式（刻意手动，不做自动任务）

- 失效恢复：飞书卡片标红某账号 → 该账号主人双击对应平台的采集入口（Windows：`trae-collect-win/一键采集.bat`；Mac：根目录 `一键采集.command`）→ 自动回填 → 下轮签到恢复
- 分发：Windows 压缩整个 `trae-collect-win/`；Mac 把根目录的 `collect_account_info.py / feishu_bitable.py / setup_bitable.py / 一键采集.command / feishu_config.json` 打包（内含真实配置，不入 git）
- 每次改动：README「更新日志」补一条（变更的权威记录）；提交信息用中文一句话说清 why + what

## 遗留事项

- 卡片汇总「今日领取」是**本轮口径**：晚上那轮全撞"已签到"时显示 +0。跨轮聚合（今日总领取 = 对各成功账号的 credits 求和）已论证，用户尚未拍板
- 各账号实际到账数额仅其中 1 个账号确认过（+200）；其余 3 个待日志验证
- 成员手里的采集包需替换 v2.5.4 修复后的 `collect_account_info.py`（._pth sys.path 坑），仅此一个文件需覆盖
