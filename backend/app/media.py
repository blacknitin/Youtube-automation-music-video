"""Media responses with HTTP Range support (needed for <video> seeking)."""
import os
import re

from starlette.concurrency import iterate_in_threadpool
from starlette.responses import StreamingResponse

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 512 * 1024


def media_file_response(path: str, mime: str, filename: str | None = None):
    if not os.path.exists(path):
        from fastapi import HTTPException
        raise HTTPException(404, "File not found")
    return _RangeFileResponse(path, mime, filename)


class _RangeFileResponse(StreamingResponse):
    def __init__(self, path, mime, filename=None):
        self._path = path
        self._size = os.path.getsize(path)
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(self._size),
        }
        if filename:
            headers["Content-Disposition"] = f'inline; filename="{filename}"'
        super().__init__(iterate_in_threadpool(self._iter_range(0, self._size - 1)),
                         media_type=mime, headers=headers)

    def _iter_range(self, start: int, end: int):
        with open(self._path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    async def __call__(self, scope, receive, send):
        range_header = None
        for k, v in scope.get("headers", []):
            if k.decode().lower() == "range":
                range_header = v.decode()
                break
        if range_header:
            m = RANGE_RE.match(range_header)
            if m and (m.group(1) or m.group(2)):
                start = int(m.group(1) or 0)
                end = int(m.group(2)) if m.group(2) else self._size - 1
                end = min(end, self._size - 1)
                if start > end or start >= self._size:
                    resp = StreamingResponse(iter([b""]), status_code=416)
                    await resp(scope, receive, send)
                    return
                self.headers["Content-Range"] = f"bytes {start}-{end}/{self._size}"
                self.headers["Content-Length"] = str(end - start + 1)
                self.status_code = 206
                self.body_iterator = iterate_in_threadpool(self._iter_range(start, end))
        await super().__call__(scope, receive, send)
