#!/usr/bin/env python3
"""
TraeCode / TraeWork Token 提取工具

尝试从本地 TraeCode 客户端中提取登录态 token。
如果自动提取失败，请参考底部的「手动提取教程」。

用法：
  python3 extract_token.py
  python3 extract_token.py --json
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path


# TraeCode 本地存储路径
STORAGE_PATHS = [
    ("TraeCode CN", "~/Library/Application Support/Trae CN/User/globalStorage/storage.json"),
    ("TraeWork CN", "~/Library/Application Support/TRAE SOLO CN/User/globalStorage/storage.json"),
]

AUTH_KEY = "iCubeAuthInfo://icube.cloudide"


def find_storage_files():
    """查找所有存在的 storage.json 文件"""
    found = []
    for name, path_template in STORAGE_PATHS:
        path = Path(os.path.expanduser(path_template))
        if path.exists():
            found.append((name, path))
    return found


def read_storage(path: Path) -> dict:
    """读取 storage.json"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def try_decrypt_tc_v5(blob_b64: str) -> dict | None:
    """
    尝试解密 tc v5 格式的认证 blob。
    v5 格式: magic(2B) + version(1B) + iv_len(1B) + flags(2B) + iv(iv_len B) + hmac(32B) + ciphertext
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        import hashlib
        import hmac
    except ImportError:
        print("[提示] 请先安装 pycryptodome: pip install pycryptodome", file=sys.stderr)
        return None

    try:
        raw = base64.b64decode(blob_b64)
    except Exception:
        return None

    if len(raw) < 54:  # 最小头部大小
        return None

    magic = raw[:2]
    if magic != b"tc":
        return None

    version = raw[2]
    iv_len = raw[3]
    flags = raw[4:6]

    # 检查 IV 长度是否合理
    if iv_len not in (16, 32):
        return None

    header_end = 6 + iv_len
    if len(raw) < header_end + 32:
        return None

    iv = raw[6:header_end]
    hmac_sig = raw[header_end:header_end + 32]
    ciphertext = raw[header_end + 32:]

    # 尝试多种常见的密钥派生方式
    # 候选密码：设备ID、机器码、固定字符串等
    candidate_passwords = [
        b"icube.cloudide.trae.cn",
        b"trae.cn",
        b"icube",
        b"",
    ]

    # 尝试从 storage.json 中获取 device_id
    # (这里先留空，调用方可以传入)

    for pwd in candidate_passwords:
        try:
            # PBKDF2-HMAC-SHA512 派生密钥
            dk = hashlib.pbkdf2_hmac(
                "sha512",
                pwd,
                b"icube.cloudide.trae.cn",
                1000,
                dklen=16 + 32,
            )
            aes_key = dk[:16]
            hmac_key = dk[16:]

            # 校验 HMAC
            expected_hmac = hmac.new(hmac_key, iv + ciphertext, hashlib.sha256).digest()
            if not hmac.compare_digest(expected_hmac, hmac_sig):
                continue

            # AES-128-CBC 解密
            cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv)
            plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
            return json.loads(plaintext.decode("utf-8"))
        except Exception:
            continue

    return None


def try_extract_from_server_data(storage: dict) -> dict | None:
    """尝试从 iCubeServerData 中获取有用信息（通常不含 token）"""
    key = "iCubeServerData://icube.cloudide"
    if key not in storage:
        return None
    try:
        data = json.loads(storage[key])
        return data
    except Exception:
        return None


def extract_token_from_storage(name: str, path: Path) -> dict | None:
    """从指定 storage.json 中提取 token"""
    try:
        storage = read_storage(path)
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        return None

    if AUTH_KEY not in storage:
        print(f"  ⚠️  未找到登录态字段")
        return None

    blob = storage[AUTH_KEY]
    print(f"  加密登录态长度: {len(blob)} 字符")

    # 尝试解密
    print(f"  正在尝试解密...")
    auth_info = try_decrypt_tc_v5(blob)

    if auth_info:
        print(f"  ✅ 解密成功!")
        return {
            "source": name,
            "path": str(path),
            "accessToken": auth_info.get("accessToken") or auth_info.get("access_token", ""),
            "refreshToken": auth_info.get("refreshToken") or auth_info.get("refresh_token", ""),
            "expiresAt": auth_info.get("expiresAt") or auth_info.get("expires_at", 0),
            "userId": auth_info.get("userId") or auth_info.get("user_id", ""),
        }
    else:
        print(f"  ❌ 自动解密失败（加密格式可能已更新）")
        return None


def main():
    parser = argparse.ArgumentParser(description="TraeCode Token 提取工具")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    results = []

    if not args.json:
        print("🔍 正在查找 TraeCode 本地登录态...\n")

    storages = find_storage_files()

    if not storages:
        if not args.json:
            print("❌ 未找到任何 TraeCode / TraeWork 存储文件")
        return 1

    for name, path in storages:
        if not args.json:
            print(f"📦 {name}")
            print(f"   路径: {path}")

        result = extract_token_from_storage(name, path)
        if result:
            results.append(result)

        if not args.json:
            print()

    if args.json:
        print(json.dumps({
            "success": len(results) > 0,
            "count": len(results),
            "results": [
                {k: v for k, v in r.items() if k not in ("accessToken", "refreshToken")}
                for r in results
            ],
        }, ensure_ascii=False, indent=2))
        return 0 if results else 1

    if results:
        print("=" * 60)
        print("✅ 成功提取到 token!")
        print("=" * 60)
        for i, r in enumerate(results, 1):
            print(f"\n账号 {i} ({r['source']}):")
            print(f"  accessToken: {r['accessToken'][:30]}... (已截断)")
            print(f"  refreshToken: {r['refreshToken'][:30]}... (已截断)")
            if r.get("userId"):
                print(f"  userId: {r['userId']}")
        print("\n💡 提示: 请妥善保管 token，不要泄露给他人")
        print("💡 你可以将 refresh_token 配置到服务器上实现自动签到")
    else:
        print("=" * 60)
        print("⚠️  自动提取失败，请使用手动方式获取 token")
        print("=" * 60)
        print("""
📖 手动提取步骤（TraeWork 网页版）：

1. 打开 https://work.trae.cn 并登录你的账号
2. 按 F12 打开开发者工具
3. 切换到 Network（网络）面板
4. 刷新页面或进行任意操作
5. 在请求列表中找到任意一个 api.trae.cn 的请求
6. 点击该请求，在 Headers 中找到 Authorization
7. 复制 Bearer 后面的内容（这就是 accessToken）

📖 获取 refresh_token（更持久）：

方法 A：在开发者工具的 Application 面板中：
  - 左侧选择 Local Storage → https://work.trae.cn
  - 查找包含 refreshToken 或 auth 的 key
  - 复制对应的 value

方法 B：在 Console 中执行：
  - JSON.stringify(localStorage)
  - 在输出中查找 refreshToken

🔧 提取后，使用方式：
  TRAE_REFRESH_TOKEN=你的refresh_token python3 trae_checkin.py
""")

    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
