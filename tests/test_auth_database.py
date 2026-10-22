import bcrypt


class _Cursor:
    def __init__(self, rows=None, row=None, rowcount=0):
        self.rows = rows or []
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Database:
    def __init__(self):
        self.users = {
            "admin": {
                "id": 1,
                "username": "admin",
                "password_hash": bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode(),
                "role": "admin",
                "department": "",
                "created_at": "now",
            }
        }

    def execute(self, sql, params=()):
        normalized = " ".join(sql.lower().split())
        if normalized.startswith("select password_hash from users"):
            user = self.users.get(params[0])
            return _Cursor(row={"password_hash": user["password_hash"]} if user else None)
        if normalized.startswith("select username, role, department from users"):
            user = self.users.get(params[0])
            return _Cursor(
                row={
                    "username": user["username"],
                    "role": user["role"],
                    "department": user["department"],
                }
                if user
                else None
            )
        if normalized.startswith("select id, username, role, department, created_at from users"):
            return _Cursor(rows=list(self.users.values()))
        if normalized.startswith("select id from users where username"):
            user = self.users.get(params[0])
            return _Cursor(row={"id": user["id"]} if user else None)
        if normalized.startswith("insert into users"):
            username, password_hash, role, department = params
            if username in self.users:
                raise RuntimeError("duplicate")
            self.users[username] = {
                "id": max(user["id"] for user in self.users.values()) + 1,
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "department": department or "",
                "created_at": "now",
            }
            return _Cursor()
        if normalized.startswith("delete from users where id"):
            user_id = params[0]
            usernames = [name for name, user in self.users.items() if user["id"] == user_id]
            for username in usernames:
                del self.users[username]
            return _Cursor(rowcount=len(usernames))
        raise AssertionError(f"Unhandled SQL: {sql}")

    def commit(self):
        return None

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_auth_crud_uses_database_and_survives_memory_reset(monkeypatch):
    from app.common import auth

    database = _Database()
    original_users = dict(auth._MEM_USERS)
    monkeypatch.setattr(auth, "psycopg", object())
    monkeypatch.setattr(auth, "_db_ready", True)
    monkeypatch.setattr(auth, "_raw_conn", lambda: database)
    auth._MEM_USERS.clear()

    try:
        assert auth.verify_password("admin", "admin123") is True
        ok, message = auth.create_user("staff_db", "staff123", role="staff", department="finance")
        assert ok is True, message
        assert auth.verify_password("staff_db", "staff123") is True
        assert auth.get_user("staff_db")["role"] == "staff"
        assert any(user["username"] == "staff_db" for user in auth.list_users())

        auth._MEM_USERS.clear()
        assert auth.verify_password("staff_db", "staff123") is True

        staff_id = database.users["staff_db"]["id"]
        assert auth.delete_user(staff_id) is True
        assert auth.get_user("staff_db") is None
    finally:
        auth._MEM_USERS.clear()
        auth._MEM_USERS.update(original_users)
