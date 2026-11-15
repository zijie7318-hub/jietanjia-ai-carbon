#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ht_api.py — 账户与碳迹记录接口（复用原有记录归档底座）

不依赖任何餐饮或外部业务服务，只依赖 Flask + 标准库。在 app.py 里注册：

    from ht_api import ht_bp
    app.register_blueprint(ht_bp)

接口（全部返回 {success, ...}）：
    POST   /api/auth/register      {username, password}
    POST   /api/auth/login         {username, password}
    POST   /api/auth/logout
    GET    /api/auth/me
    GET    /api/carbon-entries
    POST   /api/carbon-entries     {inputText, content, scene}
    DELETE /api/carbon-entries/<id>

数据存 SQLite：默认 ~/.jietanjia/records.db（可用环境变量 HT_DB_PATH 指定），
刻意不放在应用目录里——应用目录会随发布一起上传，DB 放那儿会被本地旧副本覆盖；
用户目录与系统临时目录不可写时再退到应用目录，避免整个应用起不来。
密码用 pbkdf2_hmac-sha256 + 每个用户独立随机盐；登录态是随机 token，存 sessions 表。
大模型 Key 只在单次请求内存里用，不落盘、不写日志。
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

ht_bp = Blueprint("ht", __name__)

HERE = Path(__file__).resolve().parent
_LOCK = threading.Lock()
_DB_PATH = None
_DB_ERROR = ""
_RUNTIME_SECRET = secrets.token_bytes(32)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  username   TEXT NOT NULL UNIQUE,
  pw_salt    TEXT NOT NULL,
  pw_hash    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS carbon_entries(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL,
  scene      TEXT,
  input_text TEXT,
  content    TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_carbon_user ON carbon_entries(user_id, id DESC);
CREATE TABLE IF NOT EXISTS revoked(
  token      TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
"""


# ---------- 基础工具 ----------

def _db_path() -> Path:
    """选一个可写的落盘位置（环境变量 > 用户目录 > 应用目录/data > 系统临时目录）。

    用户目录排在应用目录之前，是为了避开「发布时上传本地副本、把线上数据覆盖回去」
    这个坑：应用目录会随代码一起上传，DB 放那里每次发布都可能被旧数据盖掉。
    """
    global _DB_PATH, _DB_ERROR
    if _DB_PATH:
        return _DB_PATH
    env = (os.environ.get("HT_DB_PATH") or "").strip()
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path.home() / ".jietanjia" / "records.db")
    candidates.append(HERE / "data" / "records.db")
    candidates.append(Path(tempfile.gettempdir()) / "jietanjia_records.db")
    last_err = None
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(p), timeout=8)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("CREATE TABLE IF NOT EXISTS _probe(id INTEGER)")
                conn.execute("DROP TABLE IF EXISTS _probe")
                conn.commit()
            finally:
                conn.close()
            _DB_PATH = p
            return p
        except Exception as e:  # 换下一个候选
            last_err = e
            continue
    _DB_ERROR = str(last_err or "没有可写的数据库目录")
    raise RuntimeError("碳迹数据库不可用：" + _DB_ERROR)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               salt.encode("utf-8"), 120000).hex()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


# ---------- 签名 token（不依赖 sessions 表跨请求读，抗多实例/临时盘） ----------
# 格式：v1.<user_id>.<过期时间戳>.<签名>，签名 = HMAC-SHA256(secret, "user_id.exp")
_TOKEN_TTL = 30 * 24 * 3600  # 30 天


def _token_secret() -> bytes:
    """签名密钥：必须来自独立的 HT_TOKEN_SECRET；未配置时仅使用进程级随机密钥。

    不再从任何第三方 Token 或公开固定字符串派生。随机密钥会让服务重启后
    旧登录态失效，生产环境应显式配置至少 32 字符的高熵密钥。
    """
    raw = (os.environ.get("HT_TOKEN_SECRET") or "").strip()
    return raw.encode("utf-8") if raw else _RUNTIME_SECRET


def _sign(payload: str) -> str:
    import hmac
    return hmac.new(_token_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _make_signed_token(user_id: int) -> str:
    exp = int(datetime.now(timezone.utc).timestamp()) + _TOKEN_TTL
    payload = "v1.%d.%d" % (int(user_id), exp)
    return payload + "." + _sign(payload)


def _verify_signed_token(token: str):
    """校验签名与有效期，通过返回 user_id，否则 None。"""
    import hmac
    parts = (token or "").split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    try:
        uid = int(parts[1])
        exp = int(parts[2])
    except ValueError:
        return None
    if not hmac.compare_digest(_sign("v1.%d.%d" % (uid, exp)), parts[3]):
        return None
    if exp < int(datetime.now(timezone.utc).timestamp()):
        return None
    return uid


def _init_db():
    try:
        conn = _conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:
        global _DB_ERROR
        _DB_ERROR = str(e)
        return False


def _auth():
    """取当前用户：签名 token 自校验 + 回查用户行；也兼容老的 sessions 表 token。

    注意：发布平台会给每个请求注入它自己的 `Authorization: Bearer ...`，
    所以自定义头 X-HT-Token 必须优先读取，否则永远读不到我们自己的 token。
    """
    token = (request.headers.get("X-HT-Token") or "").strip()
    if not token:
        raw = (request.headers.get("Authorization") or "").strip()
        if raw.lower().startswith("bearer "):
            token = raw[7:].strip()
    if not token:
        return None
    try:
        conn = _conn()
    except Exception:
        return None
    try:
        uid = _verify_signed_token(token)
        if uid is not None:
            try:
                if conn.execute("SELECT 1 FROM revoked WHERE token = ?", (token,)).fetchone():
                    return None
            except Exception:
                return None  # 无法确认是否已吊销时失败关闭，避免失效令牌继续可用
            row = conn.execute("SELECT id, username FROM users WHERE id = ?", (uid,)).fetchone()
            return dict(row) if row else None
        # 兼容旧 token（存在 sessions 表里的随机串）
        row = conn.execute(
            "SELECT u.id AS id, u.username AS username FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _issue_token(user_id: int) -> str:
    """签发自包含的签名 token；同时写一条 sessions 记录（便于服务端登出/审计）。"""
    token = _make_signed_token(user_id)
    try:
        conn = _conn()
        try:
            with _LOCK:
                conn.execute("INSERT OR IGNORE INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                             (token, user_id, _now()))
                conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # 记录失败不影响登录：token 自己是有效的
    return token


# ---------- 账户 ----------

@ht_bp.route("/api/auth/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not re.fullmatch(r"[\w\u4e00-\u9fa5\-]{2,20}", username):
        return _fail("用户名需 2~20 个字符，可用中文、字母、数字、下划线")
    if len(password) < 6:
        return _fail("密码至少 6 位")
    if len(password) > 128:
        return _fail("密码太长了")
    salt = secrets.token_hex(16)
    conn = _conn()
    try:
        with _LOCK:
            try:
                cur = conn.execute(
                    "INSERT INTO users(username, pw_salt, pw_hash, created_at) VALUES(?,?,?,?)",
                    (username, salt, _hash_pw(password, salt), _now()))
                conn.commit()
            except sqlite3.IntegrityError:
                return _fail("这个用户名已被占用，换一个或直接登录", 409)
        uid = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"success": True, "token": _issue_token(uid),
                    "user": {"id": uid, "username": username}})


@ht_bp.route("/api/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username or not password:
        return _fail("请填写用户名和密码")
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, username, pw_salt, pw_hash FROM users WHERE username = ?",
            (username,)).fetchone()
    finally:
        conn.close()
    if not row or not secrets.compare_digest(_hash_pw(password, row["pw_salt"]), row["pw_hash"]):
        return _fail("用户名或密码不对", 401)
    return jsonify({"success": True, "token": _issue_token(row["id"]),
                    "user": {"id": row["id"], "username": row["username"]}})


@ht_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    token = (request.headers.get("X-HT-Token") or "").strip()
    if not token:
        raw = (request.headers.get("Authorization") or "").strip()
        token = raw[7:].strip() if raw.lower().startswith("bearer ") else ""
    if token:
        try:
            conn = _conn()
            try:
                with _LOCK:
                    conn.execute("INSERT OR IGNORE INTO revoked(token, created_at) VALUES(?,?)",
                                 (token, _now()))
                    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
    return jsonify({"success": True})


@ht_bp.route("/api/auth/me")
def me():
    user = _auth()
    if not user:
        return _fail("未登录或登录已失效", 401)
    return jsonify({"success": True, "user": user})


# ---------- 碳迹记录 ----------

@ht_bp.route("/api/carbon-entries")
def list_carbon_entries():
    user = _auth()
    if not user:
        return _fail("登录后才能查看碳迹", 401)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, scene, input_text, content, created_at FROM carbon_entries "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 200", (user["id"],)).fetchall()
    finally:
        conn.close()
    return jsonify({"success": True, "items": [{
        "id": r["id"], "scene": r["scene"] or "", "inputText": r["input_text"] or "",
        "content": r["content"], "createdAt": r["created_at"]
    } for r in rows]})


@ht_bp.route("/api/carbon-entries", methods=["POST"])
def add_carbon_entry():
    user = _auth()
    if not user:
        return _fail("登录后才能保存碳迹", 401)
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or "").strip()
    input_text = str(body.get("inputText") or "").strip()[:200]
    scene = str(body.get("scene") or "").strip()[:40]
    if not content:
        return _fail("内容不能为空")
    if len(content) > 2000:
        return _fail("内容太长了（最多 2000 字）")
    created = _now()
    conn = _conn()
    try:
        with _LOCK:
            cur = conn.execute(
                "INSERT INTO carbon_entries(user_id, scene, input_text, content, created_at) "
                "VALUES(?,?,?,?,?)", (user["id"], scene, input_text, content, created))
            conn.commit()
        entry_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify({"success": True, "item": {
        "id": entry_id, "scene": scene, "inputText": input_text,
        "content": content, "createdAt": created}})


@ht_bp.route("/api/carbon-entries/<int:entry_id>", methods=["DELETE"])
def del_carbon_entry(entry_id: int):
    user = _auth()
    if not user:
        return _fail("登录后才能删除", 401)
    conn = _conn()
    try:
        with _LOCK:
            conn.execute("DELETE FROM carbon_entries WHERE id = ? AND user_id = ?",
                         (entry_id, user["id"]))
            conn.commit()
    finally:
        conn.close()
    return jsonify({"success": True})


_init_db()
