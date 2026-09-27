# TraeCode / TraeWork 每日自动签到

通过 API 直接调用签到接口，实现每日自动领取积分，无需打开客户端。
支持部署在 GitHub Actions、服务器、云函数等任何环境。

## ✨ 功能特性

- 🍪 **Cookie 模式（推荐）**：用浏览器 Cookie 自动换 JWT Token，有效期长达数月
- 🔄 **Token 自动续期**：每次运行自动调用 GetUserToken 换取最新 Token
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

### 第 1 步：获取 Cookie

1. 打开浏览器访问 **https://work.trae.cn** 并登录
2. 按 **F12** 打开开发者工具 → 切换到 **Network（网络）** 面板
3. 刷新页面，找到任意一个 `api.trae.cn` 的请求
4. 在 Request Headers 中找到 `Cookie` → 右键复制值（完整的一长串）

> 💡 Cookie 包含 `sessionid=...; odin_tt=...; ...` 等多个字段，完整复制。

### 第 2 步：测试签到

```bash
# 安装依赖
pip3 install requests

# 查询状态（不领取积分）
TRAE_COOKIE="你的cookie整串" python3 trae_checkin.py --status

# 执行签到
TRAE_COOKIE="你的cookie整串" python3 trae_checkin.py

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

### 第 1 步：获取每个账号的 Cookie

每个账号单独获取一次，方法见上面「快速开始」第 1 步。

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

**账号列表**：账号名称、Cookie、启用
**签到日志**：日期、账号、状态（单选）、获得积分、当前积分、错误信息

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
| `GITHUB_ACTIONS_URL` | GitHub Actions 页面 URL（卡片"手动补签"按钮跳转） | ❌ 可选 |

> 💡 单账号模式只配 `TRAE_COOKIE` 就行，不需要飞书应用和多维表格。
>
> 💡 **卡片按钮说明**：配置了 `FEISHU_BITABLE_URL` 和 `GITHUB_ACTIONS_URL` 后，飞书通知卡片底部会出现「查看签到日志」和「手动补签」按钮，方便直接跳转操作。
>
> 手动补签按钮的 URL 是你的 Actions 页面地址，格式类似：
> `https://github.com/你的用户名/trae-checkin/actions/workflows/daily-checkin.yml`

---

### 第 8 步：添加账号并测试运行

#### 8.1 在多维表格加账号

1. 打开「账号列表」表 → 新增一行：
   - **账号名称**：自定义显示名（如"主号"、"工作号"）
   - **Cookie**：粘贴浏览器复制的 Cookie
   - **启用**：打勾 ✅
2. 有几个账号就加几行

#### 8.2 手动运行测试

3. GitHub 仓库 → **Actions** → 左侧选「TraeCode Daily Check-in」
4. 右侧点 **Run workflow** → 选 main → Run workflow
5. 等几秒刷新，查看运行结果
6. 去飞书群看通知卡片
7. 去多维表格「签到日志」表看记录

---

## ✅ 完成！

每天 **北京时间 09:00** 自动签到，结果推送到飞书群。

---

## 🔧 日常操作（全在飞书里）

| 操作 | 在哪里做 |
|------|----------|
| 添加新账号 | 多维表格 → 账号列表 → 新增一行 |
| 禁用账号 | 取消「启用」列的勾选 |
| 修改显示名 | 直接改「账号名称」列的文字 |
| 更换 Cookie | Cookie 列替换新的值 |
| 查看历史 | 打开「签到日志」表 |
| 手动补签 | GitHub Actions → Run workflow |

---

## 🔩 其他部署方式

### Linux 服务器 + Crontab

```bash
# 上传脚本到服务器
# 编辑 crontab
crontab -e
# 每天 9:00 执行
0 9 * * * cd /opt/trae-checkin && TRAE_COOKIE="xxx" python3 trae_checkin.py >> checkin.log 2>&1
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
| `POST /cloudide/api/v3/common/GetUserToken` | POST | Cookie 换 JWT Token |
| `POST /trae/api/v2/ug/checkin_credits/status` | POST | 查询签到状态 |
| `POST /trae/api/v2/ug/checkin_credits/claim` | POST | 领取签到积分 |

认证头格式：
```
Authorization: Cloud-IDE-JWT <jwt_token>
Content-Type: application/json
```

---

## ❓ 常见问题

### Q: Cookie 会过期吗？过期了怎么办？
A: 有效期通常数月。过期后签到会失败，飞书会收到失败通知。重新登录网页版，复制新 Cookie 替换即可。

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

- **v2.2.0** - 飞书卡片新增快捷按钮（查看日志 / 手动补签）；签到日志时间精确到秒；新增 repository_dispatch 触发方式
- **v2.1.0** - 移除 JWT Token 字段（Cookie 模式更优），修复 GitHub Actions 路径问题
- **v2.0.0** - 新增 Cookie 模式（推荐），适配 Cloud-IDE-JWT 认证格式
- **v1.0.0** - 初始版本，支持 API 签到 + 飞书通知 + 多账号管理
