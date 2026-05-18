import sqlite3
import json
import lz4.frame
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

def update_multimodel_to_vision():
    if check_server_running():
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 获取所有用户表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'u%'")
    tables = [row[0] for row in cursor.fetchall()]

    updated_count = 0

    try:
        cursor.execute("BEGIN")
        for table in tables:
            cursor.execute(f"SELECT id, compressed_message FROM {table} WHERE compressed_message IS NOT NULL")
            rows = cursor.fetchall()

            for row_id, compressed in rows:
                data = lz4.frame.decompress(compressed)
                chat_tree = json.loads(data.decode("utf-8"))

                if "root" in chat_tree and "multimodel" in chat_tree["root"]:
                    chat_tree["root"]["vision"] = chat_tree["root"].pop("multimodel")
                    new_data = json.dumps(chat_tree, ensure_ascii=False).encode("utf-8")
                    new_compressed = lz4.frame.compress(new_data)

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

if __name__ == "__main__":
    update_multimodel_to_vision()
