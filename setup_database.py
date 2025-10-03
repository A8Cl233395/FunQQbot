import sqlite3
import os
# 检查是否存在数据库文件
if os.path.exists("database.db"):
    if input("数据库已存在，是否覆盖？(y/N)").lower() == "y":
        os.remove("database.db")
        print("成功删除")
    else:
        exit()


# SQL statements to create tables
create_tables_sql = [
    """
    CREATE TABLE `bsettings` (
        `owner` TEXT NULL DEFAULT NULL,
        `model` TEXT NULL DEFAULT NULL
    )
    """,
    """
    CREATE TABLE `csettings` (
        `owner` TEXT NULL DEFAULT NULL,
        `tools` TINYINT(1) NULL DEFAULT NULL
    )
    """,
    """
    CREATE TABLE `plugins` (
        `owner` TEXT NULL DEFAULT NULL,
        `code` TEXT NULL DEFAULT NULL,
        `data` TEXT NULL DEFAULT NULL
    )
    """,
    """
    CREATE TABLE `prompts` (
        `owner` TEXT NULL DEFAULT NULL,
        `prompt` TEXT NULL DEFAULT NULL
    )
    """,
    """
    CREATE TABLE `rsettings` (
        `owner` TEXT NULL DEFAULT NULL,
        `range1` INTEGER NULL DEFAULT NULL,
        `range2` INTEGER NULL DEFAULT NULL
    )
    """
]
def db(prompt, data):
    conn = sqlite3.connect('./database.db')
    cursor = conn.cursor()
    try:
        cursor.execute(prompt, data or ())
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
# Create or connect to the SQLite database
conn = sqlite3.connect('./database.db')
cursor = conn.cursor()

# Execute each CREATE TABLE statement
for sql in create_tables_sql:
    cursor.execute(sql)

# Commit changes and close connection
conn.commit()
conn.close()

print("Database created successfully with all tables at ./database.db")