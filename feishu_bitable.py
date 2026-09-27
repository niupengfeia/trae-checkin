#!/usr/bin/env python3
"""
飞书多维表格（Bitable）操作模块
用于管理签到账号和记录签到历史

环境变量：
  FEISHU_APP_ID          - 飞书自建应用 App ID
  FEISHU_APP_SECRET      - 飞书自建应用 App Secret
  FEISHU_BITABLE_APP_TOKEN - 多维表格 app_token（URL 中获取）
"""

import os
import time
import json
import sys

try:
    import requests
except ImportError:
    print("请先安装依赖：pip install requests", file=sys.stderr)
    sys.exit(1)


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuBitable:
    """飞书多维表格客户端"""

    def __init__(self, app_id: str = None, app_secret: str = None, app_token: str = None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.app_token = app_token or os.environ.get("FEISHU_BITABLE_APP_TOKEN", "")
        self._tenant_access_token = None
        self._token_expire_time = 0

        if not self.app_id or not self.app_secret:
            raise ValueError(
                "缺少飞书应用凭证，请配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量"
            )
        if not self.app_token:
            raise ValueError(
                "缺少多维表格 app_token，请配置 FEISHU_BITABLE_APP_TOKEN 环境变量\n"
                "获取方式：打开多维表格 → URL 中 /base/ 后面的一串字符"
            )

    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token（带缓存）"""
        # 如果 token 还有效（剩余 5 分钟以上），直接返回
        if self._tenant_access_token and time.time() < self._token_expire_time - 300:
            return self._tenant_access_token

        resp = requests.post(
            f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"获取飞书 tenant_access_token 失败: code={data.get('code')}, msg={data.get('msg')}"
            )
        self._tenant_access_token = data["tenant_access_token"]
        self._token_expire_time = time.time() + data.get("expire", 7200)
        return self._tenant_access_token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """发送飞书 API 请求"""
        url = f"{FEISHU_API_BASE}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._get_tenant_access_token()}"
        headers.setdefault("Content-Type", "application/json")

        resp = requests.request(
            method,
            url,
            headers=headers,
            timeout=15,
            **kwargs,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"飞书 API 请求失败 {method} {path}: code={data.get('code')}, msg={data.get('msg')}"
            )
        return data.get("data", {})

    # ====== 数据表操作 ======

    def list_records(self, table_id: str, page_size: int = 100, filter_expr: str = None) -> list:
        """
        列出数据表中的所有记录
        自动处理分页
        """
        all_records = []
        page_token = None

        while True:
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            if filter_expr:
                params["filter"] = filter_expr

            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
                params=params,
            )

            items = data.get("items", [])
            all_records.extend(items)

            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break

        return all_records

    def create_record(self, table_id: str, fields: dict) -> dict:
        """创建一条记录"""
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
            json={"fields": fields},
        )
        return data.get("record", {})

    def update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        """更新一条记录"""
        data = self._request(
            "PATCH",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}",
            json={"fields": fields},
        )
        return data.get("record", {})

    def batch_create_records(self, table_id: str, records: list[dict]) -> list:
        """批量创建记录（最多 500 条）"""
        if not records:
            return []
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create",
            json={"records": [{"fields": r} for r in records]},
        )
        return data.get("records", [])

    # ====== 数据表管理 ======

    def list_tables(self) -> list:
        """列出所有数据表"""
        data = self._request(
            "GET",
            f"/bitable/v1/apps/{self.app_token}/tables",
        )
        return data.get("items", [])

    def create_table(self, name: str, default_view_name: str = "表格视图") -> dict:
        """创建一个新的数据表"""
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables",
            json={
                "table": {
                    "name": name,
                    "default_view_name": default_view_name,
                }
            },
        )
        return data.get("table", {})

    def list_fields(self, table_id: str) -> list:
        """列出数据表的所有字段"""
        all_fields = []
        page_token = None
        while True:
            params = {}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                params=params,
            )
            items = data.get("items", [])
            all_fields.extend(items)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return all_fields

    def create_field(self, table_id: str, field_name: str, field_type: int, property_: dict = None) -> dict:
        """
        创建字段。

        field_type:
          1=多行文本, 2=数字, 3=单选, 4=多选, 5=日期, 7=复选框,
          11=人员, 13=电话号码, 15=超链接, 17=附件, 18=关联,
          20=公式, 21=双向关联, 22=地理位置, 23=群组, 1001=创建时间,
          1002=最后更新时间, 1003=创建人, 1004=修改人, 1005=自动编号
        """
        payload = {
            "field_name": field_name,
            "type": field_type,
        }
        if property_ is not None:
            payload["property"] = property_
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
            json=payload,
        )
        return data.get("field", {})


# ====== 工具函数 ======

def _extract_text(field_value) -> str:
    """从多维表格字段中提取纯文本（支持富文本格式）"""
    if field_value is None:
        return ""
    if isinstance(field_value, str):
        return field_value.strip()
    if isinstance(field_value, list):
        # 富文本格式：[{"text": "...", "type": "text"}, ...]
        return "".join(t.get("text", "") for t in field_value if isinstance(t, dict)).strip()
    return str(field_value).strip()


# ====== 账号管理 ======

def load_accounts_from_bitable(bitable: FeishuBitable, table_id: str) -> list[dict]:
    """
    从多维表格读取账号列表。

    预期表格字段（优先级从高到低）：
      - 账号名称 (text) - 自定义显示名称，随便起什么名字都可以
      - Cookie (text) - 浏览器 Cookie 字符串（推荐，有效期长）
      - JWT Token (text) - JWT access token（Cloud-IDE-JWT 格式）
      - Refresh Token (text) - 旧版 refresh_token（兼容）
      - 启用 (checkbox) - 是否启用，不填默认为启用

    支持的字段名别名（不区分大小写，匹配到第一个即可）：
      - 名称类：账号名称 / 名称 / 备注 / name
      - Cookie 类：Cookie / cookie / Cookie 字符串
      - Token 类：JWT Token / jwt_token / jwt / Token / token / Refresh Token / refresh_token
      - 启用类：启用 / enabled / 状态
    """
    records = bitable.list_records(table_id)
    accounts = []

    for record in records:
        fields = record.get("fields", {})

        # ---- 账号名称 ----
        name = (
            _extract_text(fields.get("账号名称"))
            or _extract_text(fields.get("名称"))
            or _extract_text(fields.get("备注"))
            or _extract_text(fields.get("name"))
            or "未命名账号"
        )

        # ---- Cookie（优先级最高，推荐）----
        cookie = (
            _extract_text(fields.get("Cookie"))
            or _extract_text(fields.get("cookie"))
            or _extract_text(fields.get("Cookie 字符串"))
        )

        # ---- JWT Token ----
        jwt_token = (
            _extract_text(fields.get("JWT Token"))
            or _extract_text(fields.get("jwt_token"))
            or _extract_text(fields.get("jwt"))
            or _extract_text(fields.get("Access Token"))
            or _extract_text(fields.get("access_token"))
        )

        # ---- Refresh Token（legacy）----
        refresh_token = (
            _extract_text(fields.get("Refresh Token"))
            or _extract_text(fields.get("refresh_token"))
            or _extract_text(fields.get("Token"))
            or _extract_text(fields.get("token"))
        )

        # ---- 启用状态 ----
        enabled = fields.get("启用", fields.get("enabled", fields.get("状态", True)))
        if isinstance(enabled, bool):
            pass
        elif enabled is None or enabled == "":
            enabled = True
        else:
            # 尝试各种表示禁用的值
            enabled_str = str(enabled).lower().strip()
            enabled = enabled_str not in ("false", "0", "no", "禁用", "关闭", "off")

        # 至少要有一种认证方式
        if not cookie and not jwt_token and not refresh_token:
            continue

        accounts.append({
            "record_id": record.get("record_id", ""),
            "name": str(name).strip(),
            "cookie": cookie,
            "jwt_token": jwt_token,
            "refresh_token": refresh_token,
            "enabled": enabled,
        })

    return accounts


# ====== 签到记录 ======

def write_checkin_log(
    bitable: FeishuBitable,
    table_id: str,
    account_name: str,
    success: bool,
    action: str,
    credit: int = 0,
    earned: int = 0,
    error_msg: str = "",
):
    """
    写入签到日志到多维表格。

    预期表格字段：
      - 日期 (date) - 签到日期
      - 账号 (text) - 账号名称
      - 状态 (single_select) - 成功/失败/已签到
      - 获得积分 (number) - 本次获得积分
      - 当前积分 (number) - 当前总积分
      - 错误信息 (text) - 失败时的错误信息
    """
    if success and action == "claimed":
        status_text = "成功"
    elif success:
        status_text = "已签到"
    else:
        status_text = "失败"

    fields = {
        "签到时间": int(time.time() * 1000),
        "账号": account_name,
        "状态": status_text,
        "获得积分": earned,
        "当前积分": credit,
    }
    if error_msg:
        fields["错误信息"] = error_msg[:500]  # 限制长度

    try:
        bitable.create_record(table_id, fields)
    except Exception as e:
        print(f"[警告] 写入签到日志失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    # 测试：读取账号列表
    try:
        bitable = FeishuBitable()
        table_id = os.environ.get("FEISHU_BITABLE_ACCOUNT_TABLE", "")
        if table_id:
            accounts = load_accounts_from_bitable(bitable, table_id)
            print(f"读取到 {len(accounts)} 个账号:")
            for acc in accounts:
                status = "✅" if acc["enabled"] else "⏸️"
                auth_type = "Cookie" if acc.get("cookie") else ("JWT" if acc.get("jwt_token") else "Refresh")
                print(f"  {status} {acc['name']} ({auth_type} 模式)")
        else:
            print("请配置 FEISHU_BITABLE_ACCOUNT_TABLE 环境变量")
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
