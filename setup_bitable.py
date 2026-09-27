#!/usr/bin/env python3
"""
飞书多维表格字段初始化脚本

自动为已有的数据表添加所需字段。
使用前请先在飞书中手动创建两张表：
  1. 账号列表（表名：账号列表）
  2. 签到日志（表名：签到日志）

运行后会自动为这两张表添加所需字段，并输出 table_id。

使用方法：
  FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=yyy \
    FEISHU_BITABLE_APP_TOKEN=bascnzzz \
    python3 setup_bitable.py
"""

import os
import sys

try:
    import requests
except ImportError:
    print("请先安装依赖：pip install requests", file=sys.stderr)
    sys.exit(1)

from feishu_bitable import FeishuBitable


# ========== 字段定义 ==========

# 账号表字段
# (字段名, 字段类型, 属性)
# 字段类型: 1=多行文本, 2=数字, 3=单选, 5=日期, 7=复选框
ACCOUNT_TABLE_FIELDS = [
    ("账号名称", 1, None),
    ("Cookie", 1, None),
    ("JWT Token", 1, None),
    ("启用", 7, None),
]

# 签到日志表字段
LOG_TABLE_FIELDS = [
    ("日期", 5, {"date_formatter": "yyyy/MM/dd"}),
    ("账号", 1, None),
    ("状态", 3, {
        "options": [
            {"name": "成功"},
            {"name": "已签到"},
            {"name": "失败"},
        ]
    }),
    ("获得积分", 2, None),
    ("当前积分", 2, None),
    ("错误信息", 1, None),
]


def ensure_fields(bitable: FeishuBitable, table_name: str, fields: list) -> str:
    """
    确保数据表存在并补充缺失的字段。
    返回 table_id，找不到则返回空字符串。
    """
    # 1. 查找表
    tables = bitable.list_tables()
    target_table = None
    for t in tables:
        if t.get("name") == table_name:
            target_table = t
            break

    if not target_table:
        print(f"  ❌ 找不到表「{table_name}」")
        print(f"     请先在飞书多维表格中手动创建这张表")
        return ""

    table_id = target_table["table_id"]
    print(f"  ✅ 找到表「{table_name}」(table_id: {table_id})")

    # 2. 检查已有字段
    existing_fields = bitable.list_fields(table_id)
    existing_field_names = {f["field_name"] for f in existing_fields}

    # 3. 补充缺失的字段
    for field_name, field_type, property_ in fields:
        if field_name in existing_field_names:
            print(f"     ✅ 字段「{field_name}」已存在")
        else:
            print(f"     ➕ 创建字段「{field_name}」...")
            try:
                bitable.create_field(table_id, field_name, field_type, property_)
                print(f"       创建成功")
            except Exception as e:
                print(f"       ⚠️  创建失败: {e}")

    return table_id


def main():
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN", "").strip()

    print("=" * 60)
    print("  飞书多维表格字段初始化 - TraeCode 签到助手")
    print("=" * 60)
    print()

    # 检查必填参数
    missing = []
    if not app_id:
        missing.append("FEISHU_APP_ID")
    if not app_secret:
        missing.append("FEISHU_APP_SECRET")
    if not app_token:
        missing.append("FEISHU_BITABLE_APP_TOKEN")

    if missing:
        print("❌ 缺少以下环境变量：")
        for m in missing:
            print(f"   - {m}")
        print()
        print("请先配置这些环境变量，然后重新运行。")
        return 1

    try:
        print("🔗 连接飞书多维表格...")
        bitable = FeishuBitable(app_id, app_secret, app_token)
        print("   连接成功！")
        print()

        # 列出所有表现有表，方便用户对照
        print("📚 当前多维表格中的表：")
        tables = bitable.list_tables()
        if not tables:
            print("   （空）")
        for t in tables:
            print(f"   - {t.get('name')}  (table_id: {t.get('table_id')})")
        print()

        # 账号表
        print("📋 账号列表表：")
        account_table_id = ensure_fields(bitable, "账号列表", ACCOUNT_TABLE_FIELDS)
        print()

        # 日志表
        print("📝 签到日志表：")
        log_table_id = ensure_fields(bitable, "签到日志", LOG_TABLE_FIELDS)
        print()

        # 输出配置信息
        print("=" * 60)
        if account_table_id:
            print("  ✅ 初始化完成！")
            print("=" * 60)
            print()
            print("请将以下信息配置到 GitHub Secrets 或环境变量中：")
            print()
            print(f"  FEISHU_BITABLE_APP_TOKEN={app_token}")
            print(f"  FEISHU_BITABLE_ACCOUNT_TABLE={account_table_id}")
            if log_table_id:
                print(f"  FEISHU_BITABLE_LOG_TABLE={log_table_id}")
            print()
            print("💡 下一步：")
            print("  1. 在飞书多维表格的「账号列表」中添加账号")
            print("  2. 填写账号名称和 Cookie，勾选「启用」")
            print("  3. 运行签到脚本测试：python3 trae_checkin.py --status")
        else:
            print("  ⚠️  账号表未找到，请先手动创建")
            print("=" * 60)
            print()
            print("请在飞书多维表格中：")
            print("  1. 新建一张表，命名为「账号列表」")
            print("  2. （可选）新建一张表，命名为「签到日志」")
            print("  3. 重新运行本脚本")
            return 1

    except Exception as e:
        print(f"\n❌ 初始化失败: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)
