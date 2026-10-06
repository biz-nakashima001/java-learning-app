#!/usr/bin/env python3
"""Local-only Java runner for the Java learning app."""
from __future__ import annotations

import json
import subprocess
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8001
MAX_SOURCE_SIZE = 40_000


class LearningHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, status: int, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.path != "/execute":
            self._send_json(404, {"error": "このURLは使えません。"})
            return

        host = self.headers.get("Host", "")
        if host not in {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}:
            self._send_json(403, {"error": "localhostからのみ実行できます。"})
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > MAX_SOURCE_SIZE:
                self._send_json(413, {"error": "コードが空か、長すぎます。"})
                return
            body = json.loads(self.rfile.read(size))
            source = body.get("code", "")
            if not isinstance(source, str) or not source.strip():
                self._send_json(400, {"error": "Javaコードを入力してください。"})
                return

            with tempfile.TemporaryDirectory(prefix="java-learning-") as workdir:
                source_file = Path(workdir) / "Main.java"
                source_file.write_text(source, encoding="utf-8")
                compile_result = subprocess.run(
                    ["javac", "-encoding", "UTF-8", "-d", workdir, str(source_file)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if compile_result.returncode != 0:
                    self._send_json(200, {
                        "success": False,
                        "stderr": compile_result.stderr or compile_result.stdout,
                    })
                    return

                run_result = subprocess.run(
                    ["java", "-cp", workdir, "Main"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self._send_json(200, {
                    "success": run_result.returncode == 0,
                    "stdout": run_result.stdout,
                    "stderr": run_result.stderr or compile_result.stderr,
                })
        except FileNotFoundError:
            self._send_json(503, {"error": "Javaが見つかりません。JDKをインストールし、javacとjavaにPATHを通してください。"})
        except subprocess.TimeoutExpired:
            self._send_json(200, {"success": False, "stderr": "実行時間が長すぎます。無限ループになっていないか確認してください。"})
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "リクエストを読み取れませんでした。"})
        except BrokenPipeError:
            pass


if __name__ == "__main__":
    print(f"Javaの小さな教室: http://localhost:{PORT}")
    print("終了するには Ctrl+C を押してください。")
    ThreadingHTTPServer((HOST, PORT), LearningHandler).serve_forever()
