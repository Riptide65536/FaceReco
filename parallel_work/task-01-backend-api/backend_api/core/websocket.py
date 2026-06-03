from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading
import time
from typing import Any


_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def build_accept_value(sec_websocket_key: str) -> str:
    raw = (sec_websocket_key + _GUID).encode("utf-8")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")


class WebSocketClosed(Exception):
    pass


class WebSocketConnection:
    def __init__(self, sock: socket.socket, rfile, wfile) -> None:
        self.sock = sock
        self.rfile = rfile
        self.wfile = wfile
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        try:
            self.sock.settimeout(1.0)
        except OSError:
            pass

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def send_json(self, payload: Any) -> None:
        self.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    def send_text(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def send_ping(self) -> None:
        self._send_frame(0x9, b"")

    def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        payload = struct.pack("!H", int(code)) + reason.encode("utf-8")
        try:
            self._send_frame(0x8, payload)
        except Exception:
            pass
        self._closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.closed:
            raise WebSocketClosed()
        first = 0x80 | (opcode & 0x0F)
        length = len(payload)
        if length < 126:
            header = bytes([first, length])
        elif length < 65536:
            header = bytes([first, 126]) + struct.pack("!H", length)
        else:
            header = bytes([first, 127]) + struct.pack("!Q", length)
        with self._send_lock:
            try:
                self.wfile.write(header + payload)
                self.wfile.flush()
            except OSError as exc:
                self._closed.set()
                raise WebSocketClosed() from exc

    def wait_until_closed(self, ping_interval: float = 20.0) -> None:
        last_ping = time.monotonic()
        while not self.closed:
            now = time.monotonic()
            if now - last_ping >= ping_interval:
                try:
                    self.send_ping()
                except WebSocketClosed:
                    break
                last_ping = now

            try:
                frame = self._read_frame()
            except TimeoutError:
                continue
            except WebSocketClosed:
                break

            opcode, payload = frame
            if opcode == 0x8:
                break
            if opcode == 0x9:
                try:
                    self._send_frame(0xA, payload)
                except WebSocketClosed:
                    break
            elif opcode == 0xA:
                continue

        self.close()

    def _read_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size and not self.closed:
            try:
                chunk = self.rfile.read(size - len(chunks))
            except socket.timeout as exc:
                raise TimeoutError() from exc
            except OSError as exc:
                self._closed.set()
                raise WebSocketClosed() from exc
            if not chunk:
                self._closed.set()
                raise WebSocketClosed()
            chunks.extend(chunk)
        return bytes(chunks)

    def _read_frame(self) -> tuple[int, bytes]:
        try:
            head = self._read_exact(2)
        except TimeoutError:
            raise
        b1, b2 = head
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask_key = self._read_exact(4) if masked else b""
        payload = self._read_exact(length) if length else b""
        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        return opcode, payload

