#!/usr/bin/env python3
"""
Trae 账号信息一键采集脚本

在「装了 Trae/TraeWork 桌面客户端且已登录目标账号」的机器上运行，
自动读取本机客户端的登录态与设备指纹，输出可直接粘贴到飞书多维表格的配置值。

采集内容：
  - RefreshToken  长期凭证（自动换新 Token，替代 Cookie，无需再从浏览器复制）
  - 用户ID        x-uid 请求头
  - 设备ID        x-device-id 请求头（iCubeAuthInfo://icube-dc:N 键名中的数字）
  - 机器ID        x-machine-id 请求头（telemetry.machineId）
  - 客户端版本    x-ide-version 请求头（iCubeLastVersion）

用法：
  python3 collect_account_info.py                        # 采集最新登录的客户端
  python3 collect_account_info.py --list                 # 列出本机所有客户端登录态
  python3 collect_account_info.py --no-verify            # 跳过 RefreshToken 在线验证
  python3 collect_account_info.py --push --name 账号2     # 采集后直接写入飞书多维表格

--push 一键写入（需 pip3 install requests 并配置环境变量）：
  FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_ACCOUNT_TABLE
  账号名称与表格中已有名称「完全相等」（区分大小写）才覆盖该行，否则新建一行；
  写入会清空该行旧 Cookie，改走 RefreshToken 模式。

仅依赖 Python 标准库（AES 解密依次尝试 pycryptodome / cryptography / openssl 命令行）。
登录态解密方法逆向自官方客户端，可能随客户端版本变化。
输出包含敏感凭证，仅在本机终端查看，请勿截图或粘贴到公开场合。
"""

import os
import sys
import json
import base64
import hashlib
import argparse
import subprocess
import urllib.request

CLOUDIDE_HOSTS = ["https://api.trae.cn", "https://api.trae.ai"]
EXCHANGE_PATH = "/cloudide/api/v3/trae/oauth/ExchangeToken"
# OAuth ClientID 与客户端类型绑定（逆向自官方客户端 main.js）：
#   TRAE 版客户端（Trae CN / Trae）默认 ono9krqynydwx5
#   SOLO 版客户端（TRAE SOLO CN / TRAE SOLO / TraeWork）默认 en1oxy7wnw8j9n
CLIENT_IDS = ["ono9krqynydwx5", "en1oxy7wnw8j9n"]


def client_id_hint(storage_path: str) -> str:
    """按客户端目录名推测优先尝试的 ClientID（目录名含 SOLO 的优先 SOLO 版 ID）"""
    if "solo" in storage_path.lower():
        return CLIENT_IDS[1]
    return CLIENT_IDS[0]

# tc 格式解密常量（逆向自官方客户端）
SALT_A = bytes([
    82, 9, 106, 213, 48, 54, 165, 56, 191, 64, 163, 158, 129, 243, 215, 251,
    124, 227, 57, 130, 155, 47, 255, 135, 52, 142, 67, 68, 196, 222, 233, 203,
    84, 123, 148, 50, 166, 194, 35, 61, 238, 76, 149, 11, 66, 250, 195, 78,
    8, 46, 161, 102, 40, 217, 36, 178, 118, 91, 162, 73, 109, 139, 209, 37,
])
SALT_B = bytes([
    31, 221, 168, 51, 136, 7, 199, 49, 177, 18, 16, 89, 39, 128, 236, 95,
    96, 81, 127, 169, 25, 181, 74, 13, 45, 229, 122, 159, 147, 201, 156, 239,
    160, 224, 59, 77, 174, 42, 245, 176, 200, 235, 187, 60, 131, 83, 153, 97,
    23, 43, 4, 126, 186, 119, 214, 38, 225, 105, 20, 99, 85, 33, 12, 125,
])
MAGIC = bytes([0x74, 0x63, 0x05, 0x10, 0x00, 0x00])


def storage_candidates() -> list:
    """本机所有 Trae 客户端的 storage.json 路径（macOS + Windows）"""
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Library", "Application Support"),
        os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")),
    ]
    names = ["Trae CN", "TRAE SOLO CN", "Trae", "TRAE SOLO"]
    out = []
    for root in {r for r in roots if os.path.isdir(r)}:
        for n in names:
            p = os.path.join(root, n, "User", "globalStorage", "storage.json")
            if os.path.exists(p):
                out.append(p)
    return out


def _pkcs7_unpad(data: bytes) -> bytes:
    """剥离 PKCS#7 填充（padding 无效时原样返回，交由上层哈希校验兜底）"""
    if not data or len(data) % 16:
        return data
    n = data[-1]
    if 1 <= n <= 16 and data[-n:] == bytes([n]) * n:
        return data[:-n]
    return data


def aes_128_cbc_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC 解密，依次尝试 pycryptodome / cryptography / openssl CLI"""
    try:
        from Crypto.Cipher import AES
        # pycryptodome 的 decrypt() 不剥填充，需手动 unpad（Node 的 finalize() 会自动剥）
        return _pkcs7_unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(data))
    except ImportError:
        pass
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        return dec.update(data) + dec.finalize()
    except ImportError:
        pass
    try:
        out = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", iv.hex()],
            input=data, capture_output=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout
        raise RuntimeError(out.stderr.decode(errors="replace").strip())
    except FileNotFoundError:
        raise RuntimeError(
            "缺少 AES 解密后端，请任装其一：\n"
            "  pip3 install pycryptodome\n"
            "  pip3 install cryptography\n"
            "  （或安装 openssl 命令行工具）"
        )


def decrypt_auth_blob(b64: str) -> dict:
    """解密 tc 格式登录态，返回 {token, refreshToken, userId, host, expiredAt, ...}"""
    buf = base64.b64decode(b64)
    if len(buf) < 39:
        raise ValueError("登录态数据太短")
    hd, rb, enc = buf[:6], buf[6:38], buf[38:]
    if hd != MAGIC:
        raise ValueError("未知的登录态加密格式（header 不匹配）")
    salt = bytes(a ^ b for a, b in zip(SALT_A, SALT_B))
    inner = hashlib.sha512(rb).digest()
    final_hash = hashlib.sha512(inner + salt).digest()
    plain = aes_128_cbc_decrypt(enc, final_hash[:16], final_hash[16:32])
    stored, payload = plain[:64], plain[64:]
    if hashlib.sha512(payload).digest() != stored:
        raise ValueError("解密校验失败（SHA-512 不符）")
    return json.loads(payload.decode("utf-8"))


def load_auth(storage_path: str) -> dict:
    """从 storage.json 读取登录态与设备指纹"""
    s = json.load(open(storage_path, encoding="utf-8"))
    enc = s.get("iCubeAuthInfo://icube.cloudide")
    if not enc:
        raise ValueError("客户端未登录（找不到 iCubeAuthInfo://icube.cloudide）")
    auth = json.loads(enc) if str(enc).strip().startswith("{") else decrypt_auth_value(str(enc))

    device_id = ""
    for k in s:
        if k.startswith("iCubeAuthInfo://icube-dc:"):
            device_id = k.split("icube-dc:", 1)[1]
            break
    return {
        "auth": auth,
        "device_id": device_id,
        "machine_id": s.get("telemetry.machineId", ""),
        "ide_version": s.get("iCubeLastVersion", ""),
        "client_dir": os.path.dirname(os.path.dirname(os.path.dirname(storage_path))),
    }


def decrypt_auth_value(b64: str) -> dict:
    try:
        return decrypt_auth_blob(b64)
    except (ValueError, RuntimeError) as e:
        raise ValueError(f"登录态解密失败: {e}")


def push_to_bitable(name: str, values: dict) -> bool:
    """
    把采集值写入飞书多维表格「账号列表」。
    账号名称「完全相等」才覆盖该行，否则新建一行（区分大小写）：
    「牛鹏飞的traeCode」与「牛鹏飞的TraeCode」视为不同账号，各自成行。
    写入会清空旧 Cookie（改走 RefreshToken 模式）。
    """
    try:
        from feishu_bitable import FeishuBitable, _extract_text
        from setup_bitable import ACCOUNT_TABLE_FIELDS
    except ImportError as e:
        print(f"❌ --push 需要 requests 库且须在项目目录下运行: {e}")
        print("   先执行: pip3 install requests")
        print("   或去掉 --push，手动把输出的值粘贴到多维表格")
        return False

    table_id = os.environ.get("FEISHU_BITABLE_ACCOUNT_TABLE", "").strip()
    if not table_id:
        print("❌ 缺少环境变量 FEISHU_BITABLE_ACCOUNT_TABLE（账号表 table_id）")
        print("   获取方式：setup_bitable.py 运行输出的 FEISHU_BITABLE_ACCOUNT_TABLE")
        return False

    try:
        bitable = FeishuBitable()

        # 补齐缺失字段（定义与 setup_bitable.py 一致）
        existing = {f["field_name"] for f in bitable.list_fields(table_id)}
        for field_name, field_type, property_ in ACCOUNT_TABLE_FIELDS:
            if field_name not in existing:
                print(f"  ➕ 补建字段「{field_name}」")
                try:
                    bitable.create_field(table_id, field_name, field_type, property_)
                except Exception as e:
                    print(f"     [警告] 创建失败: {e}")

        fields = {
            "账号名称": name,
            "Cookie": "",  # 清空旧 Cookie，强制走 RefreshToken 模式
            "RefreshToken": values["refresh_token"],
            "用户ID": values["user_id"],
            "设备ID": values["device_id"],
            "机器ID": values["machine_id"],
            "客户端版本": values["ide_version"],
            "启用": True,
        }

        # 账号名称完全相等才覆盖该行，否则新建一行
        # （区分大小写：牛鹏飞的traeCode ≠ 牛鹏飞的TraeCode，两个名字各自成行）
        record_id = ""
        for rec in bitable.list_records(table_id):
            if _extract_text(rec.get("fields", {}).get("账号名称")) == name:
                record_id = rec.get("record_id", "")
                break

        if record_id:
            bitable.update_record(table_id, record_id, fields)
            print(f"✅ 已更新多维表格账号「{name}」（table_id: {table_id}）")
        else:
            bitable.create_record(table_id, fields)
            print(f"✅ 已新建多维表格账号「{name}」（table_id: {table_id}）")
        return True
    except Exception as e:
        print(f"❌ 写入多维表格失败: {e}")
        return False


def verify_refresh_token(refresh_token: str, user_id: str, host: str, client_first: str = "") -> dict:
    """
    用 RefreshToken 调 ExchangeToken 验证其有效性（标准库实现，无第三方依赖）。
    RefreshToken 与客户端类型绑定的 ClientID 匹配（TRAE 版 / SOLO 版默认值不同），
    先试 client_first（按客户端目录名推测），失败再试另一个。
    """
    client_ids = [client_first] + [c for c in CLIENT_IDS if c != client_first] if client_first else list(CLIENT_IDS)
    last_err = ""
    for base in ([host] if host else []) + CLOUDIDE_HOSTS:
        for client_id in client_ids:
            body = json.dumps({
                "ClientID": client_id,
                "RefreshToken": refresh_token,
                "ClientSecret": "-",
                "UserID": str(user_id or ""),
            }).encode()
            try:
                req = urllib.request.Request(
                    base + EXCHANGE_PATH, data=body,
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                result = data.get("Result", {})
                if result.get("Token"):
                    return {
                        "ok": True,
                        "host": base,
                        "client_id": client_id,
                        "token_expire_at": _fmt_ms(result.get("TokenExpireAt")),
                        "refresh_expire_at": _fmt_ms(result.get("RefreshExpireAt")),
                    }
                last_err = str(data)
            except Exception as e:
                last_err = str(e)
    return {"ok": False, "error": last_err}


def _fmt_ms(ms) -> str:
    """毫秒时间戳转可读时间"""
    import datetime
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Trae 账号信息一键采集")
    parser.add_argument("--list", action="store_true", help="仅列出本机所有客户端登录态")
    parser.add_argument("--no-verify", action="store_true", help="跳过 RefreshToken 在线验证")
    parser.add_argument("--json", action="store_true", help="JSON 输出（便于脚本处理）")
    parser.add_argument("--push", action="store_true", help="采集后直接写入飞书多维表格（需配置 FEISHU_* 环境变量）")
    parser.add_argument("--name", default="", help="账号显示名（--push 用；缺省用用户ID）")
    args = parser.parse_args()

    candidates = storage_candidates()
    if not candidates:
        print("❌ 未找到 Trae 客户端的 storage.json")
        print("   请确认本机已安装 Trae/TraeWork 桌面客户端并登录目标账号")
        return 1

    # 多客户端按修改时间排序，默认取最新登录的
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    if args.list:
        print(f"本机共 {len(candidates)} 个客户端登录态：\n")
        for i, p in enumerate(candidates):
            try:
                info = load_auth(p)
                uid = str(info["auth"].get("userId", ""))
                print(f"  [{i}] {info['client_dir']}")
                print(f"      用户ID: {uid}  客户端版本: {info['ide_version']}")
            except Exception as e:
                print(f"  [{i}] {p}\n      读取失败: {e}")
        return 0

    info = None
    used_path = ""
    for p in candidates:
        try:
            info = load_auth(p)
            used_path = p
            break
        except Exception as e:
            print(f"[跳过] {p}: {e}")
    if not info:
        print("❌ 所有客户端登录态读取失败，请先在客户端中登录目标账号")
        return 1

    auth = info["auth"]
    refresh_token = str(auth.get("refreshToken", ""))
    user_id = str(auth.get("userId", ""))

    verify = None
    if not args.no_verify and refresh_token:
        verify = verify_refresh_token(
            refresh_token, user_id, auth.get("host", ""), client_id_hint(used_path)
        )

    if args.json:
        print(json.dumps({
            "refresh_token": refresh_token,
            "user_id": user_id,
            "device_id": info["device_id"],
            "machine_id": info["machine_id"],
            "ide_version": info["ide_version"],
            "client_dir": info["client_dir"],
            "verify": verify,
        }, ensure_ascii=False, indent=2))
        return 0

    print("=" * 60)
    print("  Trae 账号信息采集")
    print("=" * 60)
    print(f"客户端目录: {info['client_dir']}")
    print(f"客户端版本: {info['ide_version']}")
    print()
    print("── 粘贴到飞书多维表格「账号列表」的字段值 ──")
    print()
    print(f"RefreshToken: {refresh_token}")
    print(f"用户ID:       {user_id}")
    print(f"设备ID:       {info['device_id']}")
    print(f"机器ID:       {info['machine_id']}")
    print(f"客户端版本:   {info['ide_version']}")
    if not info["device_id"] or not info["machine_id"]:
        print()
        print("⚠️  设备ID或机器ID为空：签到状态按设备指纹隔离，缺失会导致多账号互相干扰")
    print()
    print("── 验证 ──")
    if verify is None:
        print("  （已跳过在线验证）")
    elif verify.get("ok"):
        print(f"  [✓] RefreshToken 有效（服务端: {verify.get('host', '')}，ClientID: {verify.get('client_id', '')}）")
        if verify.get("token_expire_at"):
            print(f"      换取的 Token 有效期至: {verify['token_expire_at']}")
        if verify.get("refresh_expire_at"):
            print(f"      RefreshToken 有效期至: {verify['refresh_expire_at']}")
    else:
        print(f"  [✗] RefreshToken 验证失败: {verify.get('error', '')}")
        print("      可能凭证已过期，请在客户端中重新登录后再运行本脚本")
    print()

    if args.push:
        print("── 写入多维表格 ──")
        if verify is not None and not verify.get("ok"):
            print("  [✗] RefreshToken 无效，已跳过写入（请在客户端重新登录后再采集）")
            return 1
        name = args.name.strip() or user_id or "未命名账号"
        if not push_to_bitable(name, {
            "refresh_token": refresh_token,
            "user_id": user_id,
            "device_id": info["device_id"],
            "machine_id": info["machine_id"],
            "ide_version": info["ide_version"],
        }):
            return 1
    else:
        print("💡 提示：加 --push --name 账号名 可把以上值一键写入多维表格（推荐）")
    print()
    print("⚠️  以上值包含敏感凭证，仅限粘贴到自己的多维表格，请勿外传。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
