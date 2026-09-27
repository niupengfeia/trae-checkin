# TraeCode / TraeWork 每日自动签到

通过 API 直接调用签到接口，实现每日自动领取积分，无需打开客户端。
支持部署在任何服务器、GitHub Actions、云函数等环境。

## 功能特性

- ✅ **纯 API 调用**：不需要打开客户端，轻量高效
- 🍪 **Cookie 模式（推荐）**：用浏览器 Cookie 自动换 Token，有效期长（数月）
- 🔄 **Token 自动续期**：Cookie 模式下每次运行自动获取新 Token
- 🛡️ **幂等安全**：已签到自动跳过，重复运行无副作用
- 👥 **多账号支持**：支持单账号（环境变量）和多账号（飞书多维表格）
- 📊 **JSON 输出**：方便接入其他监控/通知系统
- 📱 **多端通用**：TraeCode 和 TraeWork 的积分互通
- 🔔 **飞书通知**：签到成功/失败自动推送到飞书群（汇总卡片）
- 📋 **签到日志**：自动写入飞书多维表格，历史记录可查

## 认证方式对比

| 方式 | 配置内容 | 有效期 | 自动续期 | 推荐度 |
|------|----------|--------|----------|--------|
| **Cookie 模式** ⭐ | 浏览器 Cookie 字符串 | 数月 | ✅ 每次自动换新 Token | ⭐⭐⭐⭐⭐ |
| JWT Token 模式 | JWT 字符串 | 约 8 小时 | ❌ 手动更新 | ⭐⭐ |
| Refresh Token 模式 | refresh_token | 不确定 | ❓ 不确定（旧接口） | ⭐（兼容） |

## 文件说明

```
trae-checkin/
├── trae_checkin.py          # 主签到脚本（单账号/多账号）
├── feishu_bitable.py        # 飞书多维表格模块（读取账号、写入日志）
├── run_checkin.sh           # Shell 包装脚本（带日志）
├── crontab.example          # Linux crontab 配置示例
├── requirements.txt         # Python 依赖
├── README.md                # 使用说明
└── .github/
    └── workflows/
        └── daily-checkin.yml  # GitHub Actions 定时任务
```

## 快速开始（单账号）

### 第一步：获取 Cookie（推荐方式）

1. 打开浏览器，访问 **https://work.trae.cn** 并登录
2. 按 **F12** 打开开发者工具
3. 切换到 **Network（网络）** 面板
4. **刷新一下页面**（F5）
5. 在请求列表里找到任意一个 `api.trae.cn` 的请求（筛选框搜 `api` 更快）
6. 点击那个请求，右侧切到 **Headers（标头）** 选项卡
7. 往下翻到 **Request Headers** 区域
8. 找到 `Cookie` 这一行，**复制整行的值**（很长一串，包含 `sessionid=...; odin_tt=...; ...`）
9. 保存好这串 Cookie

> 💡 **为什么 Cookie 模式更好？**
> - Cookie 有效期很长（通常数月）
> - 脚本每次运行时会自动调用 `GetUserToken` 接口换取最新的 JWT Token
> - 只要 Cookie 没失效，就永远不用手动更新 Token

### 第二步：测试签到

```bash
# 安装依赖
pip install requests

# 测试（仅查询状态，不领取积分）
TRAE_COOKIE="你的cookie字符串" python3 trae_checkin.py --status

# 执行签到
TRAE_COOKIE="你的cookie字符串" python3 trae_checkin.py

# JSON 格式输出
TRAE_COOKIE="你的cookie字符串" python3 trae_checkin.py --json

# 带飞书通知
TRAE_COOKIE="你的cookie字符串" FEISHU_WEBHOOK_URL=你的飞书webhook python3 trae_checkin.py
```

### 其他认证方式

#### JWT Token 模式

```bash
# 从 GetUserToken 接口或 Cloud-IDE-JWT header 中获取
TRAE_JWT_TOKEN="eyJ..." python3 trae_checkin.py
```

#### Refresh Token 模式（旧接口，兼容）

```bash
TRAE_REFRESH_TOKEN="xxx" python3 trae_checkin.py
```

## 飞书通知配置

脚本支持将签到结果自动推送到飞书群，成功和失败都会通知。

### 创建飞书机器人

1. 打开飞书，进入你想接收通知的群聊
2. 点击群设置（右上角「...」）→ **群机器人** → **添加机器人**
3. 选择 **自定义机器人**
4. 填写机器人名称，比如「TraeCode 签到助手」
5. 安全设置（三选一，推荐「自定义关键词」）：
   - 方式 A（推荐）：自定义关键词 → 添加 `签到`
   - 方式 B：加签 → 复制签名密钥（需要额外配置，暂不支持）
   - 方式 C：IP 白名单 → 填写允许的 IP 段
6. 点击 **添加**，复制生成的 **Webhook 地址**

### 使用方式

```bash
# 本地测试
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx \
  TRAE_COOKIE="你的cookie" python3 trae_checkin.py
```

### 通知效果

- 🎉 **签到成功**：绿色卡片，显示获得积分和当前总积分
- ✅ **今日已签到**：蓝色卡片，显示当前积分
- ❌ **签到失败**：红色卡片，显示错误信息

## 飞书多维表格（多账号管理）

如果你有多个 TraeCode 账号，可以用飞书多维表格来管理，完全在飞书里操作，不用去 GitHub 改配置。

### 整体架构

```
飞书多维表格 ← (账号列表) → GitHub Actions ← (每日定时) → TraeCode API
      ↓                                      ↓
  签到日志表                         飞书群通知（汇总卡片）
```

### 第一步：创建飞书自建应用

1. 打开飞书开放平台：https://open.feishu.cn/
2. 点击右上角 **「开发者后台」** → **创建企业自建应用**
3. 填写应用名称（如"TraeCode 签到助手"），选择用途，点击创建
4. 在应用首页，你会看到 **App ID** 和 **App Secret**，复制保存好
5. 左侧菜单 → **权限管理** → 搜索并添加以下权限：
   - `bitable:app` - 多维表格读写权限
   - `bitable:app:readonly` - 多维表格只读权限
6. 左侧菜单 → **添加应用能力** → 添加 **机器人**（可选，不影响 API）
7. 点击右上角 **版本管理与发布** → **创建版本** → 发布（个人版一般直接通过）

> 💡 飞书个人版也可以创建自建应用，功能完全够用。

### 第二步：创建多维表格

1. 在飞书中新建一个**多维表格**（Base），命名如"TraeCode 签到管理"
2. 创建**第一张表**：账号列表，字段如下：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 账号名称 | 单行文本 | **自定义显示名**，随便起（如"张三"、"工作号"等） |
| Cookie | 单行文本 | **推荐**，浏览器 Cookie 字符串（有效期长） |
| JWT Token | 单行文本 | （可选）JWT access token |
| 启用 | 复选框 | 勾选=启用，不勾选=跳过 |

> 💡 只填 Cookie 就够了，JWT Token 列可以不加。
> 脚本会自动用 Cookie 换取最新的 JWT Token。

3. 创建**第二张表**（可选但推荐）：签到日志，字段如下：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 日期 | 日期 | 签到日期 |
| 账号 | 单行文本 | 账号名称 |
| 状态 | 单选 | 成功 / 已签到 / 失败 |
| 获得积分 | 数字 | 本次获得积分 |
| 当前积分 | 数字 | 当前总积分 |
| 错误信息 | 单行文本 | 失败时的错误信息 |

4. 在浏览器中打开这个多维表格，从 URL 中获取以下信息：
   - **app_token**：URL 中 `/base/` 后面、`?` 前面的一串字符（通常以 `bascn` 开头）
   - **table_id**：URL 中 `table=` 后面的值（通常以 `tbl` 开头）
   - 分别记录两张表的 table_id

5. **给应用添加多维表格权限**：
   - 打开多维表格 → 右上角「...」→ **更多** → **添加文档应用**
   - 搜索你刚创建的应用名称，添加进去

> ⚠️ 这步很重要！不加的话应用读不到表格数据。

### 第三步：配置 GitHub Secrets

在 GitHub 仓库的 Secrets 中添加以下 secret：

| Name | 说明 | 必填 |
|------|------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID | ✅ |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret | ✅ |
| `FEISHU_BITABLE_APP_TOKEN` | 多维表格 app_token | ✅ |
| `FEISHU_BITABLE_ACCOUNT_TABLE` | 账号表 table_id | ✅ |
| `FEISHU_BITABLE_LOG_TABLE` | 签到日志表 table_id | ❌ 可选 |
| `FEISHU_WEBHOOK_URL` | 飞书群机器人 Webhook | ❌ 可选但推荐 |

> 💡 配置了多维表格后，就不需要 `TRAE_COOKIE` 环境变量了，账号从表格读取。

### 第四步：管理账号

直接在飞书多维表格中操作：

- **添加账号**：新增一行，填写账号名称和 Cookie，勾选启用
- **禁用账号**：取消「启用」列的勾选
- **修改名称**：直接改「账号名称」列的文字，通知里会同步更新
- **更新 Cookie**：直接修改 Cookie 列的值（Cookie 过期时）
- **查看历史**：打开签到日志表查看每天的签到记录

### 多账号通知效果

飞书群里会收到一张汇总卡片：

```
🎉 TraeCode 每日签到（2/3 个账号领取）
┌─────────┬─────────┐
│ 总账号  │ 成功    │
│ 3       │ 3       │
├─────────┼─────────┤
│ 今日领取 │ 失败    │
│ +400    │ 0       │
└─────────┴─────────┘

🎉 张三：+200 积分（当前 3,200）
🎉 工作号：+200 积分（当前 1,500）
✅ 备用号：已签到（当前 800 积分）

⏰ 2026-09-27 09:00:05
```

## 部署方案

### 方案一：GitHub Actions（推荐，免费免运维）

适合没有自己服务器的用户，完全免费，每天自动运行。

1. **新建 GitHub 仓库**（Private 推荐）
2. **上传脚本**：将 `trae-checkin/` 目录上传到仓库
3. **配置 Secrets**：
   - 进入仓库 Settings → Secrets and variables → Actions
   - 点击 **New repository secret**
   - 配置相关环境变量（单账号就配 `TRAE_COOKIE`，多账号配飞书相关）
   - （可选）再添加一个：Name: `FEISHU_WEBHOOK_URL`，Secret: 你的飞书机器人 Webhook 地址
4. **启用 Actions**：
   - 进入仓库 Actions 页面
   - 找到 "TraeCode Daily Check-in" workflow
   - 点击 **Enable workflow**
5. **手动测试**：
   - 点击 **Run workflow** → 选择分支 → 运行
   - 查看运行结果

> 默认每天北京时间 09:00 自动执行，可在 `.github/workflows/daily-checkin.yml` 中修改 cron 表达式。

### 方案二：Linux 服务器 + Crontab

适合有自己服务器的用户。

```bash
# 1. 上传脚本到服务器
scp -r trae-checkin/ user@your-server:/opt/trae-checkin/

# 2. 安装依赖
ssh user@your-server
pip install requests

# 3. 测试
cd /opt/trae-checkin
TRAE_COOKIE="你的cookie" python3 trae_checkin.py

# 4. 添加定时任务
crontab -e
# 复制 crontab.example 中的配置，修改路径和 cookie

# 5. 查看日志
tail -f /opt/trae-checkin/checkin.log
```

### 方案三：macOS 本地 + launchd

适合想在自己电脑上定时运行的用户。

```bash
# 赋予执行权限
chmod +x run_checkin.sh

# 直接用 crontab：
crontab -e
# 添加：0 9 * * * TRAE_COOKIE="xxx" /path/to/run_checkin.sh
```

### 方案四：云函数（阿里云/腾讯云/华为云）

适合有云资源的用户，按调用次数计费，几乎免费。

1. 创建 Python 云函数
2. 将 `trae_checkin.py` 和 `feishu_bitable.py` 内容复制进去
3. 配置环境变量（`TRAE_COOKIE` 或飞书多维表格相关）
4. 设置每日定时触发器

## API 说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `POST /cloudide/api/v3/common/GetUserToken` | POST | 用 Cookie 换取 JWT Token |
| `POST /trae/api/v2/ug/checkin_credits/status` | POST | 查询今日签到状态 |
| `POST /trae/api/v2/ug/checkin_credits/claim` | POST | 领取今日签到积分 |

认证头：
```
Authorization: Cloud-IDE-JWT <jwt_token>
Content-Type: application/json
```

## 常见问题

### Q: Cookie 会过期吗？过期了怎么办？
A: Cookie 有效期通常数月。过期后脚本会签到失败，飞书会收到失败通知。你只需要重新登录一次网页版，复制新的 Cookie 替换进去就行。

### Q: Cookie 安全吗？会不会泄露？
A: 脚本只在本地或 GitHub Actions 的加密环境中使用 Cookie，不会打印或上传。请妥善保管，不要提交到公开仓库。GitHub Secrets 是加密存储的，安全可靠。

### Q: 每天签到能得多少积分？
A: 免费用户 150 积分/天，会员用户 200 积分/天。积分有效期 31 天。

### Q: 重复运行会重复扣/加积分吗？
A: 不会。脚本会先查询今日签到状态，已签到则直接跳过。服务端也做了幂等校验。

### Q: 支持多账号吗？
A: 支持。在飞书多维表格中每行一个账号，或者为每个账号分别配置定时任务。

### Q: 飞书个人版能用吗？
A: 可以。飞书个人版也能创建企业自建应用，功能完全够用。

### Q: 会封号吗？
A: 风险极低。脚本调用的是官方 API，行为和手动签到完全一样，每天只有几次请求。2-3 个自用账号完全没问题。

## 注意事项

⚠️ **免责声明**：
- 本脚本仅用于个人账号的自动化签到，请勿用于批量账号或刷奖励
- 调用的接口来自官方客户端/网页版，可能随版本更新而变化
- 如遇签到失败，请先检查 Cookie / Token 是否过期
- 请遵守 TraeCode / TraeWork 的用户协议

## 更新日志

- v2.0.0 - 新增 Cookie 模式（推荐），适配 Cloud-IDE-JWT 认证，更新 API 字段
- v1.0.0 - 初始版本，支持 API 签到 + token 自动刷新
