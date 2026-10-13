# TraeCode / TraeWork 每日自动签到

通过 API 直接调用签到接口，实现每日自动领取积分，无需打开客户端。
支持部署在 GitHub Actions、服务器、云函数等任何环境。

## ✨ 功能特性

- 🔑 **RefreshToken 模式（推荐）**：客户端采集长期凭证，自动调 ExchangeToken 换新，比 Cookie 更持久
- 🖥️ **设备指纹隔离**：签到状态按设备指纹区分，多设备多账号时每账号用各自客户端采集的参数
- 🍪 **Cookie 模式**：用浏览器 Cookie 自动换 JWT Token，有效期长达数月
- 🛡️ **幂等安全**：已签到自动跳过，重复运行无副作用
- 👥 **多账号支持**：飞书多维表格管理，完全在飞书里操作
- 🔔 **飞书通知**：签到结果自动推送到飞书群（汇总卡片 + 快捷按钮）
- 🔘 **卡片按钮**：一键跳转查看日志 / 手动补签
- 📋 **签到日志**：自动写入多维表格，精确到秒，历史记录可查
- 📊 **JSON 输出**：方便接入其他监控系统

## 📁 文件说明

```
trae-checkin/
├── trae_checkin.py          # 主签到脚本（单账号/多账号）
├── collect_account_info.py  # 账号信息一键采集（RefreshToken + 设备指纹）
├── trae-collect-win/        # Windows 免安装采集包（自带便携 Python，无需装环境）
├── feishu_bitable.py        # 飞书多维表格模块（读账号、写日志）
├── setup_bitable.py         # 多维表格字段初始化脚本
├── run_checkin.sh           # Shell 包装脚本（带日志）
├── crontab.example          # Linux crontab 配置示例
├── requirements.txt         # Python 依赖
├── README.md                # 使用说明
└── .github/
    └── workflows/
        └── daily-checkin.yml  # GitHub Actions 定时任务
```

## 🚀 快速开始（单账号）

### 第 1 步：获取凭证

**方式 A：采集脚本（推荐，需要 Trae/TraeWork 桌面客户端已登录）**

```bash
# 解密客户端登录态需要以下任一依赖
pip3 install pycryptodome    # 或 pip3 install cryptography

python3 collect_account_info.py
```

脚本自动读取客户端登录态，输出：**RefreshToken**（长期凭证）、用户ID、设备ID、机器ID、客户端版本，并在线验证有效性。

**方式 B：浏览器 Cookie（有效期数月）**

1. 打开浏览器访问 **https://work.trae.cn** 并登录
2. 按 **F12** 打开开发者工具 → 切换到 **Network（网络）** 面板
3. 刷新页面，找到任意一个 `api.trae.cn` 的请求
4. 在 Request Headers 中找到 `Cookie` → 右键复制值（完整的一长串）

> 💡 Cookie 包含 `sessionid=...; odin_tt=...; ...` 等多个字段，完整复制。

### 第 2 步：测试签到

```bash
# 安装依赖
pip3 install requests

# RefreshToken 方式（推荐）
TRAE_REFRESH_TOKEN=xxx TRAE_USER_ID=123 \
  TRAE_DEVICE_ID=111 TRAE_MACHINE_ID=222 TRAE_IDE_VERSION=2.3.87416 \
  python3 trae_checkin.py --status

# Cookie 方式
TRAE_COOKIE="你的cookie整串" python3 trae_checkin.py --status

# 执行签到（去掉 --status 即领取积分）
# JSON 输出
TRAE_COOKIE="你的cookie整串" python3 trae_checkin.py --json
```

## 📚 完整部署指南（多账号 + 飞书管理）

### 整体架构

```
飞书多维表格 ← (账号列表) → GitHub Actions ← (每日定时) → TraeCode API
      ↓                                      ↓
  签到日志表                         飞书群通知（汇总卡片）
```

---

### 第 1 步：采集每个账号的凭证 + 设备指纹

在**每个账号各自登录的机器**上运行采集脚本：

```bash
python3 collect_account_info.py
```

输出 5 个值：RefreshToken、用户ID、设备ID、机器ID、客户端版本。

> 💡 客户端类型自动适配：Trae 版（Trae CN）和 TraeWork 版（TRAE SOLO CN）的
> RefreshToken 绑定各自不同的 OAuth ClientID，采集/签到脚本会自动识别适配，无需手动区分。
> RefreshToken 有效期约 6 个月，且可重复使用、不影响客户端登录态。

> ⚠️ **重要：签到状态按设备指纹隔离。**
> 设备ID/机器ID/客户端版本是服务端区分"哪台设备签到过"的依据，
> 多设备多账号时**必须用账号自己客户端那台机器采集的参数**。
> 如果账号2 直接套用账号1 的设备参数，会出现：账号1 签到成功领到积分，
> 账号2 显示"已签到"却没领到积分，而在账号2 自己的客户端上仍然可以签。

> 💡 不想用采集脚本也可以继续用浏览器 Cookie 方式，见「快速开始」第 1 步方式 B。
> 但多设备多账号仍建议每账号填设备参数（从各自客户端采集）。

---

### 第 2 步：本地测试脚本

先在本地验证脚本能正常工作：

```bash
# 单账号测试
TRAE_COOKIE="你的cookie" python3 trae_checkin.py --status
```

---

### 第 3 步：创建飞书自建应用

1. 打开 **https://open.feishu.cn/** → 登录 → 进入开发者后台
2. 点击 **创建企业自建应用**
3. 填写应用名称（如"TraeCode 签到助手"），点击创建
4. 在应用首页，**复制保存 App ID 和 App Secret**
5. 左侧 → **权限管理** → 搜索并开通：
   - `bitable:app`（多维表格读写）
   - `bitable:app:readonly`（多维表格只读）
6. 右上角 → **版本管理与发布** → 创建版本 → 申请发布

> 💡 飞书个人版也可以创建自建应用，功能完全够用。

---

### 第 4 步：创建多维表格

#### 4.1 新建多维表格

1. 在飞书中新建一个**多维表格**，命名如"TraeCode 签到管理"
2. 从浏览器地址栏获取 **app_token**：
   ```
   https://xxx.feishu.cn/base/【这一段就是app_token】?table=...
   ```

#### 4.2 添加文档应用

3. 多维表格页面 → 右上角 **「...」** → **更多** → **添加文档应用**
4. 搜索你刚创建的应用名称，添加进去

> ⚠️ 这步很重要！不加的话应用读不到表格数据。

#### 4.3 手动创建两张表

5. 在多维表格底部点 **「+」**，新建两张表：
   - 第一张表名：**账号列表**
   - 第二张表名：**签到日志**

> 字段不用手动加，下一步用脚本自动创建。

#### 4.4 运行初始化脚本创建字段

6. 终端执行：

```bash
FEISHU_APP_ID=你的AppID \
FEISHU_APP_SECRET=你的AppSecret \
FEISHU_BITABLE_APP_TOKEN=你的app_token \
python3 setup_bitable.py
```

脚本会自动为两张表创建所需字段：

**账号列表**：账号名称、Cookie、RefreshToken、用户ID、设备ID、机器ID、客户端版本、启用
**签到日志**：签到时间、账号、状态（单选）、本次获得积分、错误信息（已签到/失败本次获得积分为 0）

7. 脚本输出的两个 **table_id** 保存好，后面配置要用。

---

### 第 5 步：创建飞书群机器人

1. 打开飞书群 → 右上角「...」→ **群机器人** → **添加机器人**
2. 选择 **自定义机器人**
3. 名字填「TraeCode 签到助手」
4. 安全设置选 **自定义关键词** → 添加关键词 `签到`
5. 复制生成的 **Webhook 地址**

---

### 第 6 步：创建 GitHub 仓库并上传代码

1. 打开 **https://github.com/new**
2. Repository name: `trae-checkin`，Visibility: **Private**
3. Create repository
4. 终端执行：

```bash
cd /path/to/trae-checkin

git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:你的用户名/trae-checkin.git
git push -u origin main
```

> 💡 推荐配置 SSH key 免密推送：https://github.com/settings/keys

---

### 第 7 步：配置 GitHub Secrets

1. 仓库 → **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**，依次添加：

| Name | 说明 | 必填 |
|------|------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID | ✅ |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret | ✅ |
| `FEISHU_BITABLE_APP_TOKEN` | 多维表格 app_token | ✅ |
| `FEISHU_BITABLE_ACCOUNT_TABLE` | 账号表 table_id | ✅ |
| `FEISHU_BITABLE_LOG_TABLE` | 签到日志表 table_id | ❌ 可选 |
| `FEISHU_WEBHOOK_URL` | 飞书群机器人 Webhook | ❌ 推荐 |
| `FEISHU_BITABLE_URL` | 多维表格日志表完整 URL（卡片"查看日志"按钮跳转） | ❌ 可选 |
| `ACTIONS_URL` | GitHub Actions 页面 URL（卡片"手动补签"按钮跳转） | ❌ 可选 |

> 💡 单账号模式只配 `TRAE_COOKIE` 就行，不需要飞书应用和多维表格。
>
> 💡 **卡片按钮说明**：配置了 `FEISHU_BITABLE_URL` 和 `ACTIONS_URL` 后，飞书通知卡片底部会出现「查看签到日志」和「手动补签」按钮，方便直接跳转操作。
>
> 手动补签按钮的 URL 是你的 Actions 页面地址，格式类似：
> `https://github.com/你的用户名/trae-checkin/actions/workflows/daily-checkin.yml`

---

### 第 8 步：添加账号并测试运行

#### 8.1 在多维表格加账号

**方式 A（推荐，一键写入）**：

1. 把 `trae-collect-win/feishu_config.example.json` 复制为同目录的 `feishu_config.json`，填入 4 个参数（配置文件统一放在 `trae-collect-win/` 下，含 App Secret，已被 `.gitignore` 排除不会入库；主目录脚本会自动到该子目录查找）
2. 在账号对应客户端已登录的机器上，运行：

```bash
python3 collect_account_info.py              # 已有账号：按用户ID自动匹配行并覆盖凭证
python3 collect_account_info.py --name 账号2  # 新账号：同时指定账号名称
```

脚本自动采集 RefreshToken + 设备指纹并写入多维表格（按「用户ID」匹配行：已有则覆盖凭证，没有则新建一行；自动清空旧 Cookie 改走 RefreshToken 模式）。有几个账号就在各自机器上各跑一次。

> 💡 **Windows 免安装版**：仓库内 `trae-collect-win/` 目录自带便携版 Python（含解密和飞书请求所需的全部依赖，无需安装任何环境）。拷到目标电脑（或直接 clone 仓库）后，把 `feishu_config.example.json` 复制为 `feishu_config.json` 填好 4 个参数，双击「一键采集.bat」即可自动采集并写回表格（详见目录内 `使用说明.txt`）。

**方式 B（手动）**：打开「账号列表」表 → 新增一行：
   - **账号名称**：自定义显示名（如"主号"、"工作号"）
   - **RefreshToken** + **用户ID/设备ID/机器ID/客户端版本**：粘贴各自机器上 `collect_account_info.py` 的输出值
   - 或 **Cookie**：粘贴浏览器复制的 Cookie（此时设备参数留空则用默认指纹）
   - **启用**：打勾 ✅

#### 8.2 手动运行测试

3. GitHub 仓库 → **Actions** → 左侧选「TraeCode Daily Check-in」
4. 右侧点 **Run workflow** → 选 main → Run workflow
5. 等几秒刷新，查看运行结果
6. 去飞书群看通知卡片
7. 去多维表格「签到日志」表看记录

---

## ✅ 完成！

每天 **北京时间 凌晨 00:23 和 下午 20:42** 各自动签到一次（避开整点，降低 GitHub 调度延迟），结果推送到飞书群。

---

## 🔧 日常操作（全在飞书里）

| 操作 | 在哪里做 |
|------|----------|
| 添加新账号 | 该账号客户端的机器上运行 `collect_account_info.py --name 账号名`（自动新建一行） |
| 更新/刷新凭证 | 同上，不带 `--name` 也行：按用户ID自动匹配行，直接覆盖凭证 |
| 禁用账号 | 取消「启用」列的勾选 |
| 修改显示名 | 直接改「账号名称」列的文字（或采集时加 `--name 新名字`） |
| 查看历史 | 打开「签到日志」表 |
| 手动补签 | GitHub Actions → Run workflow |
| **Token 失效处理** | **签到卡片会标出失效账号：在对应机器上运行采集脚本即可恢复（详见下方说明）** |

### 🔄 Token 失效与恢复（必读）

**Token 失效是正常现象，不用排查**。客户端和签到脚本共用同一条续期链：客户端每次自动续期（约 12~14 天一次）或重新登录，都会把表格里存的旧 RefreshToken 顶掉。也就是说：

- **客户端天天在用 → 失效约 1~2 周发生一次，属预期行为**
- 签到脚本会自动识别失效并在飞书卡片上标出**哪个账号失效、怎么恢复**，不需要翻日志找原因
- 恢复只要一步（约 30 秒）：在装有该账号客户端的机器上运行
  `python3 collect_account_info.py`
  （Windows 双击「一键采集.bat」）
  按用户ID自动匹配表格行并写回新凭证，下次签到自动恢复，**无需复制粘贴**

两种失效类型的对照（卡片提示已区分）：

| 签到卡片提示 | 原因 | 恢复方法 |
|----------|------|----------|
| 🔴 RefreshToken 已失效 | 客户端续期/重登把旧 token 顶掉了（活跃账号约 1~2 周一次） | 直接重跑采集脚本 |
| 🟠 JWT 已过期（客户端疑似长期未运行） | 该账号的客户端很久没开机，缓存的 JWT 超过 14 天 | 先打开客户端确认在线 → 再运行采集脚本 |

---

## 🔩 其他部署方式

### Linux 服务器 + Crontab

```bash
# 上传脚本到服务器
# 编辑 crontab
crontab -e
# 每天 凌晨 0:23 与 下午 20:42 各执行一次
23 0 * * * cd /opt/trae-checkin && TRAE_COOKIE="xxx" python3 trae_checkin.py >> checkin.log 2>&1
42 20 * * * cd /opt/trae-checkin && TRAE_COOKIE="xxx" python3 trae_checkin.py >> checkin.log 2>&1
```

### 云函数（阿里云/腾讯云等）

1. 创建 Python 云函数
2. 复制 `trae_checkin.py` + `feishu_bitable.py`
3. 配置环境变量
4. 设置每日定时触发器

---

## 📖 API 说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /cloudide/api/v3/trae/oauth/ExchangeToken` | POST | RefreshToken 换 JWT Token（可重复使用） |
| `POST /cloudide/api/v3/common/GetUserToken` | POST | Cookie 换 JWT Token |
| `POST /trae/api/v2/ug/checkin_credits/status` | POST | 查询签到状态（按设备指纹隔离） |
| `POST /trae/api/v2/ug/checkin_credits/claim` | POST | 领取签到积分 |

认证头格式：
```
Authorization: Cloud-IDE-JWT <jwt_token>
x-device-id / x-machine-id / x-ide-version: 设备指纹（多账号各自配置）
Content-Type: application/json
```

---

## ❓ 常见问题

### Q: 账号1 签到成功，账号2 显示"已签到"却没领到积分？
A: 这是设备指纹混用导致的。签到状态按设备指纹（设备ID/机器ID/客户端版本）隔离，账号2 用了账号1 的设备参数，服务端认为"这台设备已签过"。解决：在账号2 登录的机器上运行 `collect_account_info.py`，让账号2 用自己的设备参数（按用户ID自动写回对应行）。

### Q: 不同账号能共用同一套设备参数吗？
A: 不能，原因同上。多设备多账号时每个账号必须用自己客户端采集的参数，签到脚本会按账号读取各自指纹。

### Q: RefreshToken 会让客户端掉登录吗？
A: 不会。RefreshToken 可重复使用（已实测连续换取多次均成功），不影响客户端正常登录。凭证有效期见采集脚本验证输出（一般数月）。

### Q: RefreshToken 过期了怎么办？
A: 在客户端重新登录一次该账号，再运行 `collect_account_info.py` 覆盖更新即可（按用户ID自动写回对应行）。

### Q: Cookie 会过期吗？过期了怎么办？
A: 有效期通常数月。过期后签到会失败，飞书会收到失败通知。重新登录网页版复制新 Cookie 替换，或改用 RefreshToken 模式。

### Q: Cookie 安全吗？
A: 脚本只在本地或 GitHub Actions 加密环境中使用，不会打印或上传。请妥善保管，不要提交到公开仓库。GitHub Secrets 是加密存储的。

### Q: 每天签到能得多少积分？
A: 免费用户 150 积分/天，会员用户 200 积分/天。积分有效期 31 天。

### Q: 重复运行会重复加积分吗？
A: 不会。脚本会先查询今日状态，已签到则跳过。服务端也做了幂等校验。

### Q: 支持多账号吗？
A: 支持。在飞书多维表格中每行一个账号，脚本自动批量签到并汇总通知。

### Q: 飞书个人版能用吗？
A: 可以。飞书个人版也能创建企业自建应用，功能完全够用。

### Q: 会封号吗？
A: 风险极低。脚本调用的是官方 API，行为和手动签到完全一样，每天只有几次请求。2-3 个自用账号完全没问题。

---

## ⚠️ 免责声明

- 本脚本仅用于个人账号的自动化签到，请勿用于批量账号或刷奖励
- 调用的接口来自官方客户端/网页版，可能随版本更新而变化
- 请遵守 TraeCode / TraeWork 的用户协议

## 📝 更新日志

- **v2.5.2** - 修复「本次获得积分」自 v2.3.4 起恒为 0 的生产问题：实测状态接口的 `credits` 即当日签到所得数字（领取前后不变，领取响应不含积分字段），"领取前后差值"算法从原理上取不到值（近 7 天 48 条成功记录积分全为 0 即此原因）；改为直接取 `credits`。卡片明细不再显示"（当前 X 积分）"（该数字易与余额混淆），领取行只显示"+X 积分"，已签到行只显示"已签到"
- **v2.5.1** - 修复按用户ID更新已有账号行必失败的问题：飞书单条记录更新官方方法为 PUT，原代码误用 PATCH（飞书网关不路由 PATCH，返回纯文本 404，曾导致推送报错 "Extra data"）；同时飞书 API 非 JSON 响应改为报「HTTP 状态码 + 响应内容」而非令人费解的 JSON 解析错误
- **v2.5.0** - 采集脚本改为自动推送（去掉 `--push`，默认采集即写表）：按「用户ID」精确匹配表格行回填凭证（不再依赖账号名称拼写，彻底避免"悄悄新建一行"），已有行账号名称保持不变、新账号自动建行并输出用户ID便于区分；飞书凭证支持 `feishu_config.json` 本地配置文件（含 App Secret，已加入 `.gitignore` 不入库，模板 `feishu_config.example.json`），环境变量仍兼容；Windows 采集包双击 bat 即完成"采集 + 自动推送"
- **v2.4.0** - 新增 Token 失效检测与恢复指引：签到失败时自动识别失效类型（RefreshToken 被客户端顶掉 / JWT 过期），飞书卡片标出失效账号并给出对应恢复命令；Windows 采集包支持 `--push` 直写多维表格（内置标准库 HTTP 兜底，无需安装 requests）
- **v2.3.4** - 修复「成功」记录的本次获得积分恒为 0：领取响应不含积分字段，改为用领取前后总积分差值计算；README 新增「客户端保活」说明（签到 JWT 由客户端登录签发、约 14 天有效期，脚本无法自动续期）
- **v2.3.3** - 签到日志表字段简化：获得积分/当前积分 合并为「本次获得积分」（仅记录本次签到所得，已签到/失败为 0）；定时改为北京时间凌晨 00:23 与 下午 20:42 各执行一次（避开整点，降低 GitHub 调度延迟）
- **v2.3.2** - 修复 Windows 包中文 bat 在中文系统下运行乱码/命令被切碎的问题：`一键采集.bat` 改为 GBK 编码原生格式，且 git 按原样字节入库（clone 或 GitHub 下载 ZIP 均不会改变文件内容）
- **v2.3.1** - 新增 Windows 免安装采集包 `trae-collect-win/`（自带便携版 Python + pycryptodome，双击 bat 输出账号凭证，手动粘贴到多维表格，无需任何配置）；明确 `--push` 账号名称完全相等（区分大小写）才覆盖
- **v2.3.0** - 新增 RefreshToken 模式（客户端长期凭证，ExchangeToken 自动换新）；多账号支持每账号独立设备指纹（签到状态按设备隔离）；自动适配 Trae 版 / TraeWork 版 ClientID；移除已失效的旧版刷新接口；新增 collect_account_info.py 一键采集，支持 `--push` 直写多维表格
- **v2.2.0** - 飞书卡片新增快捷按钮（查看日志 / 手动补签）；签到日志时间精确到秒；新增 repository_dispatch 触发方式
- **v2.1.0** - 移除 JWT Token 字段（Cookie 模式更优），修复 GitHub Actions 路径问题
- **v2.0.0** - 新增 Cookie 模式（推荐），适配 Cloud-IDE-JWT 认证格式
- **v1.0.0** - 初始版本，支持 API 签到 + 飞书通知 + 多账号管理
