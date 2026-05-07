"""
Minimal Turso HTTP client — drop-in replacement for sqlite3 connections.
Uses Turso's /v2/pipeline HTTP API. No extra dependencies required.
"""
import json
import urllib.request


def _to_arg(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}   # hrana: integers as strings
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}        # hrana: integers as strings
    if isinstance(v, float):
        return {"type": "float", "value": v}               # hrana: floats as JSON numbers
    return {"type": "text", "value": str(v)}


class _Cursor:
    def __init__(self, result):
        cols = result.get("cols", [])
        self._names = [c["name"] for c in cols]
        self._rows  = result.get("rows", [])
        last = result.get("last_insert_rowid")
        self.lastrowid  = int(last) if last is not None else None
        self.description = [(n, None, None, None, None, None, None) for n in self._names]

    def _parse(self, raw):
        def val(cell):
            if cell["type"] == "null":
                return None
            v, t = cell["value"], cell["type"]
            if t == "integer":
                return int(v)
            if t == "float":
                return float(v)
            return v
        return {name: val(cell) for name, cell in zip(self._names, raw)}

    def fetchone(self):
        return self._parse(self._rows[0]) if self._rows else None

    def fetchall(self):
        return [self._parse(r) for r in self._rows]


class TursoConnection:
    def __init__(self, url, auth_token):
        base = url.replace("libsql://", "https://")
        self._endpoint  = base.rstrip("/") + "/v2/pipeline"
        self._token     = auth_token

    def _pipeline(self, stmts):
        requests = [{"type": "execute", "stmt": s} for s in stmts]
        requests.append({"type": "close"})
        body = json.dumps({"requests": requests}).encode()
        req  = urllib.request.Request(
            self._endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise Exception(f"Turso HTTP {e.code}: {body}")
        return data["results"]

    def execute(self, sql, params=()):
        stmt    = {"sql": sql, "args": [_to_arg(p) for p in (params or [])]}
        results = self._pipeline([stmt])
        r = results[0]
        if r["type"] == "error":
            raise Exception(r["error"]["message"])
        return _Cursor(r["response"]["result"])

    def executemany(self, sql, params_list):
        stmts = [{"sql": sql, "args": [_to_arg(p) for p in row]} for row in params_list]
        if not stmts:
            return
        results = self._pipeline(stmts)
        for r in results[:-1]:
            if r["type"] == "error":
                raise Exception(r["error"]["message"])

    # Turso auto-commits each HTTP pipeline — no explicit commit/rollback needed
    def commit(self):   pass
    def rollback(self): pass
    def close(self):    pass
