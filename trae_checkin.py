#!/usr/bin/env python3
"""
TraeCode / TraeWork 每日自动签到脚本（多账号版）

通过 API 直接调用签到接口，不需要打开客户端。
支持单账号（环境变量）和多账号（飞书多维表格）两种模式。
支持两种认证方式：
  - Cookie 模式（推荐）：用 sessionid cookie 自动换 JWT token，有效期长
  - JWT Token 模式：直接配置 JWT token，有效期约 8 小时
  - Refresh Token 模式（legacy）：旧版 refresh_token 方式
支持飞书群通知（单账号详情卡片 / 多账号汇总卡片）。

用法：
  # 单账号模式（Cookie 方式，推荐）
  TRAE_COOKIE="sessionid=xxx; ..." python3 trae_checkin.py

  # 单账号模式（JWT Token 方式）
  TRAE_JWT_TOKEN=xxx python3 trae_checkin.py

  # 多账号模式（飞书多维表格）
  FEISHU_APP_ID=xxx FEISHU_APP_SECRET=yyy FEISHU_BITABLE_APP_TOKEN=zzz \
    FEISHU_BITABLE_ACCOUNT_TABLE=tblxxx python3 trae_checkin.py

  # 仅查询状态
  python3 trae_checkin.py --status

  # JSON 输出
  python3 trae_checkin.py --json

环境变量（单账号模式，优先级：cookie > jwt_token > refresh_token）：
  TRAE_COOKIE          - Cookie 字符串（含 sessionid 等），推荐
  TRAE_JWT_TOKEN       - JWT access token（Cloud-IDE-JWT 格式）
  TRAE_REFRESH_TOKEN   - （legacy）refresh_token

环境变量（多账号/飞书多维表格模式）：
  FEISHU_APP_ID          - 飞书自建应用 App ID
  FEISHU_APP_SECRET      - 飞书自建应用 App Secret
  FEISHU_BITABLE_APP_TOKEN - 多维表格 app_token
  FEISHU_BITABLE_ACCOUNT_TABLE - 账号表 table_id
  FEISHU_BITABLE_LOG_TABLE     - （可选）签到日志表 table_id

环境变量（飞书通知，两种模式都支持）：
  FEISHU_WEBHOOK_URL  - 飞书群机器人 Webhook 地址
"""

import os
import sys
import json
import time
import argparse

try:
    import requests
except ImportError:
    print("请先安装依赖：pip install requests", file=sys.stderr)
    sys.exit(1)


# ========== TraeCode API 配置 ==========

CLOUDIDE_BASE = "https://api.trae.cn/cloudide/api/v3"
UG_BASE = "https://ug-normal.trae.ai/trae/api/v2"

GET_USER_TOKEN_URL = f"{CLOUDIDE_BASE}/common/GetUserToken"
CHECKIN_STATUS_URL = f"{UG_BASE}/ug/checkin_credits/status"
CHECKIN_CLAIM_URL = f"{UG_BASE}/ug/checkin_credits/claim"
REFRESH_TOKEN_URL = f"{UG_BASE}/ug/auth/refresh"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://work.trae.cn",
    "Referer": "https://work.trae.cn/",
}


# ========== 认证：Cookie 换 Token ==========

def get_token_from_cookie(cookie_str: str) -> dict:
    """
    使用 cookie 调用 GetUserToken 接口换取 JWT token。
    返回 {"token": "...", "expired_at": "...", "user_id": "...", "tenant_id": "..."}
    """
    resp = requests.post(
        GET_USER_TOKEN_URL,
        headers={
            **DEFAULT_HEADERS,
            "Cookie": cookie_str,
        },
        timeout=15,
    )
    data = resp.json()
    result = data.get("Result", {})
    if not result or not result.get("Token"):
        msg = data.get("message") or data.get("msg") or str(data)
        raise RuntimeError(f"用 Cookie 换取 Token 失败: {msg}")
    return {
        "token": result["Token"],
        "expired_at": result.get("ExpiredAt", ""),
        "user_id": result.get("UserID", ""),
        "tenant_id": result.get("TenantID", ""),
    }


# ========== 认证：Refresh Token（legacy） ==========

def refresh_access_token(refresh_token: str) -> dict:
    """使用 refresh_token 刷新 access_token（旧接口，保留兼容）"""
    resp = requests.post(
        REFRESH_TOKEN_URL,
        json={"refreshToken": refresh_token},
        headers=DEFAULT_HEADERS,
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"刷新 token 失败: code={data.get('code')}, msg={data.get('message')}"
        )
    return data["data"]


# ========== 获取有效 JWT Token ==========

def get_valid_jwt_token(account: dict) -> dict:
    """
    从账号配置中获取有效的 JWT token 及用户信息。
    优先级：cookie > jwt_token > refresh_token
    返回 {"token": "...", "tenant_id": "...", "user_id": "..."}
    """
    # 方式 1：Cookie 模式（推荐）
    cookie = account.get("cookie", "").strip()
    if cookie:
        return get_token_from_cookie(cookie)

    # 方式 2：直接配置 JWT token
    jwt_token = account.get("jwt_token", "").strip()
    if jwt_token:
        return {"token": jwt_token, "tenant_id": "", "user_id": ""}

    # 方式 3：refresh_token（legacy）
    refresh_token = account.get("refresh_token", "").strip()
    if refresh_token:
        token_data = refresh_access_token(refresh_token)
        return {
            "token": token_data.get("accessToken", ""),
            "tenant_id": token_data.get("tenantId", ""),
            "user_id": token_data.get("userId", ""),
        }

    raise RuntimeError("未配置任何认证信息（cookie / jwt_token / refresh_token）")


# ========== 签到接口 ==========

def _auth_headers(jwt_token: str, cookie: str = "") -> dict:
    """构造带认证的请求头（与网页版一致：authorization 小写 + 带 cookie）"""
    headers = {
        **DEFAULT_HEADERS,
        "authorization": f"Cloud-IDE-JWT {jwt_token}",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def get_checkin_status(jwt_token: str, cookie: str = "") -> dict:
    """
    查询今日签到状态。
    返回字段示例：
      {
        "checked_in": true,
        "code": 0,
        "credits": 200,
        "did_checked_in": false,
        "enable": true,
        "extra_credits": 50,
        "message": "success"
      }
    """
    resp = requests.post(
        CHECKIN_STATUS_URL,
        headers=_auth_headers(jwt_token, cookie),
        json={"req_source": 3},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"查询签到状态失败: code={data.get('code')}, msg={data.get('message')}"
        )
    return data


def claim_checkin(jwt_token: str, cookie: str = "", tenant_id: str = "", user_id: str = "") -> dict:
    """领取今日签到积分"""
    resp = requests.post(
        CHECKIN_CLAIM_URL,
        headers=_auth_headers(jwt_token, cookie),
        json={"req_source": 3},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"领取签到积分失败: code={data.get('code')}, msg={data.get('message')}"
        )
    return data


# ========== 单账号签到 ==========

def checkin_single(account: dict, status_only: bool = False) -> dict:
    """
    单个账号签到，返回结果字典。

    account 字段：
      - name: 账号显示名
      - cookie: Cookie 字符串（推荐）
      - jwt_token: JWT token（可选）
      - refresh_token: 旧版 refresh_token（可选，legacy）
    """
    result = {
        "success": False,
        "action": "unknown",
        "current_credit": 0,
        "earned_credit": 0,
        "error": "",
        "message": "",
    }

    try:
        # 1. 获取有效 JWT token + 用户信息
        token_info = get_valid_jwt_token(account)
        jwt_token = token_info["token"]
        tenant_id = token_info.get("tenant_id", "")
        user_id = token_info.get("user_id", "")
        cookie = account.get("cookie", "").strip()

        # 2. 查询签到状态
        status = get_checkin_status(jwt_token, cookie)
        already_checked = status.get("checked_in", False)
        current_credit = status.get("credits", 0)

        result["current_credit"] = current_credit
        result["status_detail"] = status

        if already_checked:
            result["success"] = True
            result["action"] = "skipped"
            result["message"] = f"今日已签到，当前积分: {current_credit}"
        else:
            if status_only:
                result["success"] = True
                result["action"] = "status_only"
                result["message"] = f"今日未签到，当前积分: {current_credit}"
            else:
                # 3. 领取签到积分
                claim_data = claim_checkin(jwt_token, cookie, tenant_id, user_id)
                earned = claim_data.get("credits", 0)
                result["success"] = True
                result["action"] = "claimed"
                result["earned_credit"] = earned
                result["claim_detail"] = claim_data
                result["message"] = f"签到成功，获得 {earned} 积分"

                # 领取后更新当前积分（如果返回了的话）
                if claim_data.get("credits"):
                    result["current_credit"] = claim_data["credits"]

    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["message"] = f"签到失败: {e}"

    return result


# ========== 多账号（多维表格） ==========

def load_accounts_from_env() -> list[dict]:
    """从环境变量加载单账号（向后兼容多种配置方式）"""
    cookie = os.environ.get("TRAE_COOKIE", "").strip()
    jwt_token = os.environ.get("TRAE_JWT_TOKEN", "").strip()
    refresh_token = os.environ.get("TRAE_REFRESH_TOKEN", "").strip()

    if not cookie and not jwt_token and not refresh_token:
        return []

    return [{
        "name": os.environ.get("TRAE_ACCOUNT_NAME", "默认账号"),
        "cookie": cookie,
        "jwt_token": jwt_token,
        "refresh_token": refresh_token,
        "enabled": True,
        "record_id": "",
    }]


def load_accounts_from_bitable() -> list[dict]:
    """从飞书多维表格加载账号列表"""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.environ.get("FEISHU_BITABLE_ACCOUNT_TABLE", "").strip()

    if not all([app_id, app_secret, app_token, table_id]):
        return []

    try:
        from feishu_bitable import FeishuBitable, load_accounts_from_bitable
        bitable = FeishuBitable(app_id, app_secret, app_token)
        accounts = load_accounts_from_bitable(bitable, table_id)
        return accounts
    except Exception as e:
        print(f"[警告] 从多维表格加载账号失败: {e}", file=sys.stderr)
        return []


def write_logs_to_bitable(results: list[dict]):
    """将签到结果写入多维表格日志表"""
    log_table = os.environ.get("FEISHU_BITABLE_LOG_TABLE", "").strip()
    if not log_table:
        return

    try:
        from feishu_bitable import FeishuBitable, write_checkin_log
        bitable = FeishuBitable()
        for r in results:
            write_checkin_log(
                bitable,
                log_table,
                account_name=r.get("name", "未知"),
                success=r.get("success", False),
                action=r.get("action", "unknown"),
                credit=r.get("current_credit", 0),
                earned=r.get("earned_credit", 0),
                error_msg=r.get("error", ""),
            )
    except Exception as e:
        print(f"[警告] 写入签到日志失败: {e}", file=sys.stderr)


# ========== 飞书通知 ==========

def _status_style(result: dict) -> tuple[str, str]:
    """根据结果返回 (图标, 颜色)"""
    success = result.get("success", False)
    action = result.get("action", "unknown")
    if success and action == "claimed":
        return "🎉", "green"
    elif success and action == "skipped":
        return "✅", "blue"
    elif success and action == "status_only":
        return "ℹ️", "blue"
    else:
        return "❌", "red"


def send_feishu_notification(
    webhook_url: str,
    results: list[dict],
    timestamp: int = None,
    bitable_url: str = "",
    github_actions_url: str = "",
) -> bool:
    """
    发送飞书卡片消息通知。
    - 单账号：发送详情卡片
    - 多账号：发送汇总卡片
    - 支持底部按钮（查看日志、手动补签）
    """
    if not webhook_url:
        return False

    try:
        timestamp = timestamp or int(time.time())
        total = len(results)
        success_count = sum(1 for r in results if r.get("success"))
        claimed_count = sum(1 for r in results if r.get("action") == "claimed")
        failed_count = sum(1 for r in results if not r.get("success"))
        total_earned = sum(r.get("earned_credit", 0) for r in results if r.get("success"))

        # 汇总状态
        if failed_count > 0:
            status_icon = "⚠️"
            status_text = f"签到完成（{success_count}/{total} 成功）"
            color = "red"
        elif claimed_count > 0:
            status_icon = "🎉"
            status_text = f"签到成功（{claimed_count}/{total} 个账号领取）"
            color = "green"
        else:
            status_icon = "✅"
            status_text = f"签到完成（全部已签到）"
            color = "blue"

        # 构造账号明细
        detail_lines = []
        for r in results:
            icon, _ = _status_style(r)
            name = r.get("name", "未知")
            if r.get("success"):
                if r.get("action") == "claimed":
                    detail_lines.append(
                        f"{icon} **{name}**：+{r.get('earned_credit', 0)} 积分（当前 {r.get('current_credit', 0)}）"
                    )
                else:
                    detail_lines.append(
                        f"{icon} **{name}**：已签到（当前 {r.get('current_credit', 0)} 积分）"
                    )
            else:
                err = r.get("error", "未知错误")
                if len(err) > 80:
                    err = err[:80] + "..."
                detail_lines.append(f"{icon} **{name}**：{err}")

        # 汇总字段
        fields = [
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**总账号**\n{total}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**成功**\n{success_count}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**今日领取**\n+{total_earned}"}},
            {"is_short": True, "text": {"tag": "lark_md", "content": f"**失败**\n{failed_count}"}},
        ]

        elements = [
            {"tag": "div", "fields": fields},
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(detail_lines),
                },
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}"
                    }
                ],
            },
        ]

        # 底部按钮（如果配置了对应 URL）
        actions = []
        if bitable_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📋 查看签到日志"},
                "type": "default",
                "url": bitable_url,
            })
        if github_actions_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔄 手动补签"},
                "type": "primary",
                "url": github_actions_url,
            })
        if actions:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "action",
                "actions": actions,
            })

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{status_icon} TraeCode 每日签到",
                    },
                    "template": color,
                },
                "elements": elements,
            },
        }

        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp_data = resp.json()
        if resp_data.get("code") == 0 or resp_data.get("StatusCode") == 0:
            print("[飞书] 通知推送成功")
            return True
        else:
            print(f"[飞书] 通知推送失败: {resp_data}", file=sys.stderr)
            return False

    except Exception as e:
        print(f"[飞书] 通知推送异常: {e}", file=sys.stderr)
        return False


# ========== 主逻辑 ==========

def main():
    parser = argparse.ArgumentParser(
        description="TraeCode / TraeWork 每日自动签到（支持单账号/多账号）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
单账号环境变量（优先级从高到低）：
  TRAE_COOKIE          Cookie 字符串（推荐，有效期长）
  TRAE_JWT_TOKEN       JWT access token
  TRAE_REFRESH_TOKEN   旧版 refresh_token（兼容）

多账号环境变量（飞书多维表格）：
  FEISHU_APP_ID              飞书应用 App ID
  FEISHU_APP_SECRET          飞书应用 App Secret
  FEISHU_BITABLE_APP_TOKEN   多维表格 app_token
  FEISHU_BITABLE_ACCOUNT_TABLE  账号表 table_id
  FEISHU_BITABLE_LOG_TABLE   （可选）签到日志表 table_id

通知环境变量：
  FEISHU_WEBHOOK_URL         飞书群机器人 Webhook

示例：
  # Cookie 模式（推荐）
  TRAE_COOKIE="sessionid=xxx; ..." python3 trae_checkin.py

  # 多账号（多维表格）
  FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=yyy \\
    FEISHU_BITABLE_APP_TOKEN=zzz FEISHU_BITABLE_ACCOUNT_TABLE=tblxxx \\
    python3 trae_checkin.py
        """,
    )
    parser.add_argument("--status", action="store_true", help="仅查询签到状态，不领取积分")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    args = parser.parse_args()

    timestamp = int(time.time())
    all_results = []

    # 1. 加载账号（优先多维表格，其次环境变量）
    accounts = load_accounts_from_bitable()
    if not accounts:
        accounts = load_accounts_from_env()

    if not accounts:
        print("❌ 未找到任何账号配置", file=sys.stderr)
        print("请配置 TRAE_COOKIE / TRAE_JWT_TOKEN / TRAE_REFRESH_TOKEN", file=sys.stderr)
        print("或配置飞书多维表格相关环境变量", file=sys.stderr)
        return 1

    if not args.json:
        print(f"📋 共 {len(accounts)} 个账号，开始签到...\n")

    # 2. 逐个签到
    for i, acc in enumerate(accounts, 1):
        if not acc.get("enabled", True):
            if not args.json:
                print(f"[{i}/{len(accounts)}] ⏸️  {acc['name']}：已禁用，跳过")
            continue

        if not args.json:
            print(f"[{i}/{len(accounts)}] 🔄 {acc['name']}：正在签到...")

        result = checkin_single(acc, status_only=args.status)
        result["name"] = acc.get("name", "未知")
        result["record_id"] = acc.get("record_id", "")
        all_results.append(result)

        if not args.json:
            icon, _ = _status_style(result)
            if result["success"] and result["action"] == "claimed":
                print(f"     {icon} 签到成功 +{result['earned_credit']} 积分")
            elif result["success"] and result["action"] == "skipped":
                print(f"     {icon} 今日已签到 ({result['current_credit']} 积分)")
            elif result["success"] and result["action"] == "status_only":
                print(f"     {icon} 未签到 ({result['current_credit']} 积分)")
            else:
                err = result.get('error', '未知')
                if len(err) > 100:
                    err = err[:100] + "..."
                print(f"     {icon} 失败: {err}")

    # 3. 写入日志表
    write_logs_to_bitable(all_results)

    # 4. 飞书通知
    feishu_webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if feishu_webhook:
        # 按钮链接（直接从环境变量读取，用户自己配置完整 URL）
        bitable_url = os.environ.get("FEISHU_BITABLE_URL", "").strip()
        github_actions_url = os.environ.get("ACTIONS_URL", "").strip()

        send_feishu_notification(
            feishu_webhook,
            all_results,
            timestamp,
            bitable_url=bitable_url,
            github_actions_url=github_actions_url,
        )

    # 5. 输出结果
    if args.json:
        output = {
            "timestamp": timestamp,
            "total": len(all_results),
            "success_count": sum(1 for r in all_results if r.get("success")),
            "failed_count": sum(1 for r in all_results if not r.get("success")),
            "results": all_results,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print()
        success = sum(1 for r in all_results if r.get("success"))
        failed = len(all_results) - success
        if failed == 0:
            print(f"✅ 全部完成：{success}/{len(all_results)} 个账号成功")
        else:
            print(f"⚠️  部分失败：{success}/{len(all_results)} 成功，{failed} 个失败")

    # 全部成功返回 0，有失败返回 1
    return 0 if all(r.get("success") for r in all_results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)
