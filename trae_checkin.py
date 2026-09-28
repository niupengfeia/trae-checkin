#!/usr/bin/env python3
"""
TraeCode / TraeWork 每日自动签到脚本（多账号版）

通过 API 直接调用签到接口，不需要打开客户端。
支持单账号（环境变量）和多账号（飞书多维表格）两种模式。
支持三种认证方式：
  - RefreshToken 模式（推荐）：客户端采集的长期凭证，自动调 ExchangeToken 换新 Token
  - Cookie 模式：用 sessionid cookie 自动换 JWT token，有效期长
  - JWT Token 模式：直接配置 JWT token，有效期约 8 小时
支持每账号独立设备指纹（签到状态按设备指纹隔离，多设备多账号必填，
用 collect_account_info.py 在各账号登录的客户端上一键采集）。
支持飞书群通知（单账号详情卡片 / 多账号汇总卡片）。

用法：
  # 单账号模式（Cookie 方式）
  TRAE_COOKIE="sessionid=xxx; ..." python3 trae_checkin.py

  # 单账号模式（RefreshToken 方式，推荐）
  TRAE_REFRESH_TOKEN=xxx TRAE_USER_ID=123 \
    TRAE_DEVICE_ID=111 TRAE_MACHINE_ID=222 TRAE_IDE_VERSION=2.3.87416 \
    python3 trae_checkin.py

  # 单账号模式（JWT Token 方式）
  TRAE_JWT_TOKEN=xxx python3 trae_checkin.py

  # 多账号模式（飞书多维表格）
  FEISHU_APP_ID=xxx FEISHU_APP_SECRET=yyy FEISHU_BITABLE_APP_TOKEN=zzz \
    FEISHU_BITABLE_ACCOUNT_TABLE=tblxxx python3 trae_checkin.py

  # 仅查询状态
  python3 trae_checkin.py --status

  # JSON 输出
  python3 trae_checkin.py --json

环境变量（单账号模式，优先级：cookie > refresh_token > jwt_token）：
  TRAE_COOKIE          - Cookie 字符串（含 sessionid 等）
  TRAE_REFRESH_TOKEN   - 客户端采集的 RefreshToken（推荐，collect_account_info.py 获取）
  TRAE_JWT_TOKEN       - JWT access token（Cloud-IDE-JWT 格式）

环境变量（单账号设备指纹，RefreshToken/多设备多账号时建议配置）：
  TRAE_USER_ID         - 用户 ID（x-uid）
  TRAE_DEVICE_ID       - 设备 ID（x-device-id）
  TRAE_MACHINE_ID      - 机器 ID（x-machine-id）
  TRAE_IDE_VERSION     - 客户端版本（x-ide-version）

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
import uuid
import base64
import argparse

try:
    import requests
except ImportError:
    print("请先安装依赖：pip install requests", file=sys.stderr)
    sys.exit(1)


# ========== TraeCode API 配置 ==========

CLOUDIDE_BASE = "https://api.trae.cn/cloudide/api/v3"
# CN 区域网页版 WEBSITE_API_URL = https://api.trae.cn（ug-normal.trae.ai 是国际版域名，国内账号 404）
TRAE_BASE = "https://api.trae.cn/trae/api/v2"

GET_USER_TOKEN_URL = f"{CLOUDIDE_BASE}/common/GetUserToken"
EXCHANGE_TOKEN_URL = f"{CLOUDIDE_BASE}/trae/oauth/ExchangeToken"
CHECKIN_STATUS_URL = f"{TRAE_BASE}/ug/checkin_credits/status"
CHECKIN_CLAIM_URL = f"{TRAE_BASE}/ug/checkin_credits/claim"

# OAuth ClientID 与客户端类型绑定（逆向自官方客户端 main.js）：
#   TRAE 版客户端（Trae CN / Trae）默认 ono9krqynydwx5
#   SOLO 版客户端（TRAE SOLO CN / TRAE SOLO / TraeWork）默认 en1oxy7wnw8j9n
# RefreshToken 只与其客户端类型匹配的 ClientID 互换，按序自动尝试
OAUTH_CLIENT_IDS = ["ono9krqynydwx5", "en1oxy7wnw8j9n"]

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


# ========== 认证：RefreshToken 换 Token ==========

def exchange_token(refresh_token: str, user_id: str = "") -> dict:
    """
    使用客户端采集的 RefreshToken 调 ExchangeToken 换取 JWT token。
    RefreshToken 与客户端类型绑定的 ClientID 匹配（TRAE 版 / SOLO 版默认值不同），
    按序自动尝试；可重复使用、不使客户端登录态失效。
    返回 Result 字段：Token / TokenExpireAt / RefreshExpireAt / UserID / BoundDeviceID 等。
    """
    last_err = ""
    for client_id in OAUTH_CLIENT_IDS:
        try:
            resp = requests.post(
                EXCHANGE_TOKEN_URL,
                json={
                    "ClientID": client_id,
                    "RefreshToken": refresh_token,
                    "ClientSecret": "-",
                    "UserID": str(user_id or ""),
                },
                headers=DEFAULT_HEADERS,
                timeout=15,
            )
            data = resp.json()
            result = data.get("Result", {})
            if result.get("Token"):
                return result
            err = data.get("ResponseMetadata", {}).get("Error", {})
            last_err = err.get("Message") or str(data)[:200]
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"ExchangeToken 换取失败: {last_err}")


# ========== 获取有效 JWT Token ==========

def get_valid_jwt_token(account: dict) -> dict:
    """
    从账号配置中获取有效的 JWT token 及用户信息。
    优先级：cookie > refresh_token > jwt_token
    返回 {"token": "...", "tenant_id": "...", "user_id": "..."}
    """
    # 方式 1：Cookie 模式
    cookie = account.get("cookie", "").strip()
    if cookie:
        return get_token_from_cookie(cookie)

    # 方式 2：RefreshToken 模式（客户端采集，推荐）
    refresh_token = account.get("refresh_token", "").strip()
    if refresh_token:
        user_id = account.get("user_id", "").strip()
        result = exchange_token(refresh_token, user_id)
        return {
            "token": result.get("Token", ""),
            "expired_at": result.get("TokenExpireAt", ""),
            "user_id": str(result.get("UserID", "") or user_id),
            "tenant_id": str(result.get("TenantID", "") or ""),
        }

    # 方式 3：直接配置 JWT token
    jwt_token = account.get("jwt_token", "").strip()
    if jwt_token:
        return {"token": jwt_token, "tenant_id": "", "user_id": ""}

    raise RuntimeError("未配置任何认证信息（cookie / refresh_token / jwt_token）")


# ========== 签到接口（客户端风格，与官方桌面客户端/开源项目 trae-work-checkin-plus 一致） ==========

# 客户端应用 ID（官方桌面客户端上报的固定值）
APP_ID = "6eefa01c-1036-4c7e-9ca5-d891f63bfcd8"

# 设备指纹默认取自本机 Trae CN 客户端 storage.json，可用环境变量覆盖：
#   TRAE_DEVICE_ID / TRAE_MACHINE_ID / TRAE_IDE_VERSION
FP_DEFAULTS = {
    "device_id": "92837310108621",
    "machine_id": "f858aa6f29a5f6dd4e7c91c325e4713ab36be6ce90d9e6f27053d6b8421b02a0",
    "ide_version": "2.3.87416",
    "device_type": "mac",
    "os_version": "Darwin 27.0.0",
}


def _uid_from_jwt(jwt_token: str) -> str:
    """从 JWT payload 解析用户 ID（data.id），cookie 模式下一般不需要"""
    try:
        payload = jwt_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return str(data.get("data", {}).get("id", ""))
    except Exception:
        return ""


def _device_params(account: dict = None) -> dict:
    """
    解析设备指纹参数。
    优先级：账号自身配置（多维表格采集值，多账号隔离的关键） > 环境变量 > 内置默认值。
    """
    account = account or {}

    def pick(account_key: str, env_key: str) -> str:
        v = (account.get(account_key, "") or os.environ.get(env_key, "")).strip()
        return v or FP_DEFAULTS[account_key]

    return {
        "device_id": pick("device_id", "TRAE_DEVICE_ID"),
        "machine_id": pick("machine_id", "TRAE_MACHINE_ID"),
        "ide_version": pick("ide_version", "TRAE_IDE_VERSION"),
    }


def _auth_headers(jwt_token: str, user_id: str = "", account: dict = None) -> dict:
    """
    构造客户端风格的认证头。
    签到/领取接口按设备指纹校验并隔离签到状态：
      - 缺设备指纹头会报 9004（The submitted order parameters are incorrect）
      - 签到状态按设备指纹隔离，账号2 必须用账号2 客户端采集的指纹
    account 为 None 时（单账号环境变量模式）回退到 TRAE_* 环境变量 / 内置默认值。
    """
    fp = _device_params(account)
    return {
        "Authorization": f"Cloud-IDE-JWT {jwt_token}",
        "X-Cloudide-Token": jwt_token,
        "x-uid": str(user_id or ""),
        "x-app-id": APP_ID,
        "x-device-id": fp["device_id"],
        "x-machine-id": fp["machine_id"],
        "x-request-id": str(uuid.uuid4()),
        "x-ide-version": fp["ide_version"],
        "x-ide-version-code": fp["ide_version"].replace(".", ""),
        "x-device-type": FP_DEFAULTS["device_type"],
        "x-os-version": FP_DEFAULTS["os_version"],
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_checkin_status(jwt_token: str, user_id: str = "", account: dict = None) -> dict:
    """
    查询今日签到状态（按账号设备指纹隔离）。
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
        headers=_auth_headers(jwt_token, user_id, account),
        json={},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"查询签到状态失败: code={data.get('code')}, msg={data.get('message')}"
        )
    return data


def claim_checkin(jwt_token: str, user_id: str = "", account: dict = None) -> dict:
    """领取今日签到积分（空请求体，客户端不发 req_source）"""
    resp = requests.post(
        CHECKIN_CLAIM_URL,
        headers=_auth_headers(jwt_token, user_id, account),
        json={},
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
      - cookie: Cookie 字符串
      - refresh_token: RefreshToken（客户端采集，推荐）
      - jwt_token: JWT token（可选）
      - user_id / device_id / machine_id / ide_version:
        设备指纹参数（签到状态按设备隔离，多账号须各自客户端采集）
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
        user_id = (
            token_info.get("user_id", "")
            or str(account.get("user_id", "")).strip()
            or _uid_from_jwt(jwt_token)
        )

        # 2. 查询签到状态（带账号专属设备指纹）
        status = get_checkin_status(jwt_token, user_id, account)
        already_checked = status.get("checked_in", False)
        current_credit = status.get("credits", 0)
        enable = status.get("enable", True)
        did_checked_in = status.get("did_checked_in", False)

        result["current_credit"] = current_credit
        result["status_detail"] = status

        if already_checked:
            result["success"] = True
            result["action"] = "skipped"
            result["message"] = f"今日已签到，当前积分: {current_credit}"
        elif not enable:
            # 与网页版守卫一致：enable=false 不发起领取（此时领取会报 9004）
            result["success"] = True
            result["action"] = "disabled"
            result["message"] = f"签到功能未开放(enable=false)，当前积分: {current_credit}"
        elif did_checked_in:
            # 网页版守卫：did_checked_in=true 时不再领取
            result["success"] = True
            result["action"] = "skipped"
            result["message"] = f"今日已领过(did_checked_in)，当前积分: {current_credit}"
        else:
            if status_only:
                result["success"] = True
                result["action"] = "status_only"
                result["message"] = f"今日未签到，当前积分: {current_credit}"
            else:
                # 3. 领取签到积分
                claim_data = claim_checkin(jwt_token, user_id, account)
                earned = (claim_data.get("gained_credits")
                          or claim_data.get("credits_gained")
                          or claim_data.get("reward")
                          or claim_data.get("extra_credits")
                          or claim_data.get("credits")
                          or 0)
                result["success"] = True
                result["action"] = "claimed"
                result["earned_credit"] = earned
                result["claim_detail"] = claim_data
                result["message"] = f"签到成功，获得 {earned} 积分"

                # 领取后重查状态拿最新总积分（与网页版行为一致）
                try:
                    new_status = get_checkin_status(jwt_token, user_id, account)
                    result["current_credit"] = new_status.get("credits", current_credit)
                except Exception:
                    pass

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
    elif success and action in ("status_only", "disabled"):
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
                elif r.get("action") == "disabled":
                    detail_lines.append(
                        f"{icon} **{name}**：签到未开放（当前 {r.get('current_credit', 0)} 积分）"
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
  TRAE_COOKIE          Cookie 字符串（有效期长）
  TRAE_REFRESH_TOKEN   客户端采集的 RefreshToken（推荐，collect_account_info.py 获取）
  TRAE_JWT_TOKEN       JWT access token

设备指纹环境变量（单账号模式可选；多账号模式从多维表格按账号读取，无需配置）：
  TRAE_USER_ID / TRAE_DEVICE_ID / TRAE_MACHINE_ID / TRAE_IDE_VERSION
  （不配则用内置默认指纹；多设备多账号时必须每账号配各自的值）

多账号环境变量（飞书多维表格）：
  FEISHU_APP_ID              飞书应用 App ID
  FEISHU_APP_SECRET          飞书应用 App Secret
  FEISHU_BITABLE_APP_TOKEN   多维表格 app_token
  FEISHU_BITABLE_ACCOUNT_TABLE  账号表 table_id
  FEISHU_BITABLE_LOG_TABLE   （可选）签到日志表 table_id

通知环境变量：
  FEISHU_WEBHOOK_URL         飞书群机器人 Webhook

示例：
  # Cookie 模式
  TRAE_COOKIE="sessionid=xxx; ..." python3 trae_checkin.py

  # RefreshToken 模式（推荐，采集方式见 collect_account_info.py）
  TRAE_REFRESH_TOKEN=xxx TRAE_DEVICE_ID=111 \\
    TRAE_MACHINE_ID=222 TRAE_IDE_VERSION=2.3.87416 python3 trae_checkin.py

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
            elif result["success"] and result["action"] == "disabled":
                print(f"     {icon} 签到功能未开放 ({result['current_credit']} 积分)")
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
