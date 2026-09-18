"""upload_server.py — 接收 guest 通过 wget --post-file 回传的文件

用法: python tools/upload_server.py  (监听 0.0.0.0:8001, 保存到 runtime/collected/)
guest 侧: wget -q -O /dev/null --post-file=/tmp/vhal.log http://10.0.2.2:8001/upload
"""
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runtime", "collected")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        data = self.rfile.read(n) if n else b""
        name = time.strftime("%Y%m%d-%H%M%S")
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("filename="):
            name += "-" + ctype.split("=", 1)[1].strip().strip("'\"")
        elif self.path.startswith("/upload/"):
            name += "-" + os.path.basename(self.path[len("/upload/"):])
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, name)
        with open(path, "wb") as f:
            f.write(data)
        print("saved %s (%d bytes)" % (path, len(data)), flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_PUT(self):
        self.do_POST()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("upload server on :8001 -> %s" % OUT_DIR, flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
