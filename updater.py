import sqlite3
import json
import lz4.frame
import zstandard
import os
import sys

DB_FILE = "chatdata.db"

def check_server_running():
    """检测数据库是否被其他进程（服务器）占用"""
    lock_files = [
        f"{DB_FILE}-shm",
        f"{DB_FILE}-wal"
    ]
    for lf in lock_files:
        if os.path.exists(lf):
            print(f"错误：检测到 {lf} 存在，服务器可能仍在运行。")
            print("请先停止服务器再运行此脚本。")
            return True
    return False

def _try_decompress(compressed: bytes) -> tuple[dict, str]:
    """尝试用 zstd 和 lz4 解压，返回 (数据, 格式)"""
    try:
        data = zstandard.decompress(compressed)
        return json.loads(data.decode("utf-8")), "zstd"
    except Exception:
        pass
    try:
        data = lz4.frame.decompress(compressed)
        return json.loads(data.decode("utf-8")), "lz4"
    except Exception:
        pass
    raise Exception("无法解压数据（既不是 zstd 也不是 lz4）")

def _compress_zstd(data: dict) -> bytes:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return zstandard.compress(raw)

def update_multimodel_to_vision():
    """将 JSON 中的 multimodel 字段重命名为 vision，同时输出改为 zstd 格式"""
    if check_server_running():
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'u%'")
    tables = [row[0] for row in cursor.fetchall()]

    updated_count = 0

    try:
        cursor.execute("BEGIN")
        for table in tables:
            cursor.execute(f"SELECT id, compressed_message FROM {table} WHERE compressed_message IS NOT NULL")
            rows = cursor.fetchall()

            for row_id, compressed in rows:
                chat_tree, _ = _try_decompress(compressed)

                if "root" in chat_tree and "multimodel" in chat_tree["root"]:
                    chat_tree["root"]["vision"] = chat_tree["root"].pop("multimodel")
                    new_compressed = _compress_zstd(chat_tree)

                    cursor.execute(f"UPDATE {table} SET compressed_message = ? WHERE id = ?", (new_compressed, row_id))
                    updated_count += 1
                    print(f"更新 {table} 记录 {row_id}")

        conn.commit()
        print(f"完成，共更新 {updated_count} 条记录")
    except Exception as e:
        conn.rollback()
        print(f"错误：迁移失败，已回滚所有更改。原因：{e}")
        sys.exit(1)
    finally:
        conn.close()

def migrate_lz4_to_zstd():
    """将所有 lz4 压缩的数据迁移为 zstd 格式（不修改 JSON 内容）"""
    if check_server_running():
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'u%'")
    tables = [row[0] for row in cursor.fetchall()]

    migrated_count = 0
    skipped_count = 0

    try:
        cursor.execute("BEGIN")
        for table in tables:
            cursor.execute(f"SELECT id, compressed_message FROM {table} WHERE compressed_message IS NOT NULL")
            rows = cursor.fetchall()

            for row_id, compressed in rows:
                chat_tree, fmt = _try_decompress(compressed)

                if fmt == "zstd":
                    skipped_count += 1
                    continue

                new_compressed = _compress_zstd(chat_tree)
                cursor.execute(f"UPDATE {table} SET compressed_message = ? WHERE id = ?", (new_compressed, row_id))
                migrated_count += 1
                print(f"迁移 {table} 记录 {row_id} (lz4 → zstd)")

        conn.commit()
        print(f"完成，迁移 {migrated_count} 条，跳过 {skipped_count} 条（已是 zstd）")
    except Exception as e:
        conn.rollback()
        print(f"错误：迁移失败，已回滚所有更改。原因：{e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 40)
    print("数据库迁移工具")
    print("=" * 40)
    print("1) 更新 JSON 定义（multimodel → vision）")
    print("2) lz4 → zstd 压缩格式迁移")
    print("3) 两个都执行")
    print("0) 退出")
    print()

    choice = input("请选择操作 [0-3]: ").strip()

    if choice == "1":
        update_multimodel_to_vision()
    elif choice == "2":
        migrate_lz4_to_zstd()
    elif choice == "3":
        print("\n--- 步骤 1: 更新 JSON 定义 ---")
        update_multimodel_to_vision()
        print("\n--- 步骤 2: lz4 → zstd 迁移 ---")
        migrate_lz4_to_zstd()
    elif choice == "0":
        print("已退出")
    else:
        print("无效选择")
        sys.exit(1)

    if choice in ("1", "2", "3"):
        trim = input("\n是否执行 VACUUM 回收空间？(y/N): ").strip().lower()
        if trim == "y":
            print("正在 VACUUM...")
            conn = sqlite3.connect(DB_FILE)
            conn.execute("VACUUM")
            conn.close()
            new_size = os.path.getsize(DB_FILE)
            print(f"完成，当前数据库大小: {new_size:,} bytes")
