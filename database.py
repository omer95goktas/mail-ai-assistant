import os
import aiosqlite
from pathlib import Path
import config

def get_db():
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return aiosqlite.connect(str(db_path), timeout=10.0)

async def init_db():
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA busy_timeout = 5000")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_address TEXT NOT NULL UNIQUE,
                imap_server TEXT NOT NULL,
                imap_port INTEGER NOT NULL DEFAULT 993,
                smtp_server TEXT NOT NULL,
                smtp_port INTEGER NOT NULL DEFAULT 587,
                app_password TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                check_interval_seconds INTEGER NOT NULL DEFAULT 60,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                message_id TEXT,
                sender TEXT NOT NULL,
                subject TEXT,
                incoming_snippet TEXT,
                gemini_summary TEXT,
                draft_reply TEXT,
                status TEXT CHECK(status IN ('PENDING', 'SENT', 'CANCELLED')) DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                message_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id, message_id)
            );
        """)

        # Performance indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_replies(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pending_account ON pending_replies(account_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_processed_acc_msg ON processed_messages(account_id, message_id)")

        await db.commit()

async def add_account(email_address: str, imap_server: str, imap_port: int,
                      smtp_server: str, smtp_port: int, app_password: str,
                      check_interval_seconds: int = 60) -> int:
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            INSERT INTO accounts (email_address, imap_server, imap_port, smtp_server, smtp_port, app_password, check_interval_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email_address) DO UPDATE SET
                imap_server=excluded.imap_server,
                imap_port=excluded.imap_port,
                smtp_server=excluded.smtp_server,
                smtp_port=excluded.smtp_port,
                app_password=excluded.app_password,
                is_active=1
        """, (email_address, imap_server, imap_port, smtp_server, smtp_port, app_password, check_interval_seconds))
        await db.commit()
        return cursor.lastrowid

async def get_accounts(active_only: bool = False):
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cursor = await db.execute("SELECT * FROM accounts WHERE is_active = 1")
        else:
            cursor = await db.execute("SELECT * FROM accounts ORDER BY id ASC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_account(account_id: int):
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def delete_account(account_id: int) -> bool:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()
        return cursor.rowcount > 0

async def toggle_account(account_id: int, is_active: int) -> bool:
    async with get_db() as db:
        cursor = await db.execute("UPDATE accounts SET is_active = ? WHERE id = ?", (is_active, account_id))
        await db.commit()
        return cursor.rowcount > 0

async def is_message_processed(account_id: int, message_id: str) -> bool:
    if not message_id:
        return False
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT 1 FROM processed_messages WHERE account_id = ? AND message_id = ?",
            (account_id, message_id)
        )
        return (await cursor.fetchone()) is not None

async def mark_message_processed(account_id: int, message_id: str):
    if not message_id:
        return
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO processed_messages (account_id, message_id) VALUES (?, ?)",
            (account_id, message_id)
        )
        await db.commit()

async def add_pending_reply(account_id: int, message_id: str, sender: str,
                              subject: str, incoming_snippet: str,
                              gemini_summary: str, draft_reply: str) -> int:
    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO pending_replies (account_id, message_id, sender, subject, incoming_snippet, gemini_summary, draft_reply, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """, (account_id, message_id, sender, subject, incoming_snippet, gemini_summary, draft_reply))
        await db.commit()
        return cursor.lastrowid

async def get_pending_reply(reply_id: int):
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT p.*, a.email_address, a.smtp_server, a.smtp_port, a.imap_server, a.imap_port, a.app_password
            FROM pending_replies p
            JOIN accounts a ON p.account_id = a.id
            WHERE p.id = ?
        """, (reply_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_latest_pending_reply():
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT p.*, a.email_address, a.smtp_server, a.smtp_port, a.imap_server, a.imap_port, a.app_password
            FROM pending_replies p
            JOIN accounts a ON p.account_id = a.id
            WHERE p.status = 'PENDING'
            ORDER BY p.id DESC
            LIMIT 1
        """)
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_reply_status(reply_id: int, status: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute("UPDATE pending_replies SET status = ? WHERE id = ?", (status, reply_id))
        await db.commit()
        return cursor.rowcount > 0

async def update_pending_draft(reply_id: int, new_draft: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute("UPDATE pending_replies SET draft_reply = ? WHERE id = ?", (new_draft, reply_id))
        await db.commit()
        return cursor.rowcount > 0

async def get_cancelled_replies(limit: int = 10):
    async with get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT p.*, a.email_address
            FROM pending_replies p
            JOIN accounts a ON p.account_id = a.id
            WHERE p.status = 'CANCELLED'
            ORDER BY p.id DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_stats():
    async with get_db() as db:
        cur_total_acc = await db.execute("SELECT COUNT(*) FROM accounts")
        total_acc = (await cur_total_acc.fetchone())[0]

        cur_active_acc = await db.execute("SELECT COUNT(*) FROM accounts WHERE is_active = 1")
        active_acc = (await cur_active_acc.fetchone())[0]

        cur_pending = await db.execute("SELECT COUNT(*) FROM pending_replies WHERE status = 'PENDING'")
        pending_cnt = (await cur_pending.fetchone())[0]

        cur_sent = await db.execute("SELECT COUNT(*) FROM pending_replies WHERE status = 'SENT'")
        sent_cnt = (await cur_sent.fetchone())[0]

        cur_cancelled = await db.execute("SELECT COUNT(*) FROM pending_replies WHERE status = 'CANCELLED'")
        cancelled_cnt = (await cur_cancelled.fetchone())[0]

        cur_processed = await db.execute("SELECT COUNT(*) FROM processed_messages")
        processed_cnt = (await cur_processed.fetchone())[0]

        db_file = Path(config.DB_PATH)
        db_size_kb = (db_file.stat().st_size / 1024) if db_file.exists() else 0

        return {
            "total_accounts": total_acc,
            "active_accounts": active_acc,
            "pending_count": pending_cnt,
            "sent_count": sent_cnt,
            "cancelled_count": cancelled_cnt,
            "processed_count": processed_cnt,
            "db_size_kb": round(db_size_kb, 2)
        }