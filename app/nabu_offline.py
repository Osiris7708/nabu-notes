"""Keeps Nabu Notes offline.

Your recordings, transcripts and notes never leave this computer. To make sure of that, every
network connection from inside Nabu is blocked, except:
  * connections to this computer itself (127.0.0.1 - used so a second NabuNotes.exe can bring the
    open window to the front), and
  * the one-time download of the speech models (Settings / first start), which only downloads, and
  * free fonts from Google Fonts, when you paste text in a font you don't have (nabu_fontfetch; only the
    font's name is sent, never your text - Settings > Fonts can turn it off).
Blocked attempts are written to logs\\nabu.log as "BLOCKED network connection".
"""
import ipaddress
import logging
import os
import socket
import threading

log = logging.getLogger("nabu.offline")
_allow = threading.local()
_installed = False
blocked = []


def _is_local(address):
    try:
        host = address[0] if isinstance(address, tuple) else address
    except Exception:
        return False
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if not isinstance(host, str):   # e.g. AF_UNIX paths
        return True
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _check(address):
    if getattr(_allow, "on", False) or _is_local(address):
        return
    blocked.append(str(address))
    log.warning("BLOCKED network connection to %s (Nabu stays offline)", address)
    raise ConnectionRefusedError("Nabu Notes works offline - network access is blocked")


class allow_downloads:
    """with allow_downloads(): ...   (only used for the speech-model download)"""

    def __enter__(self):
        self.prev = getattr(_allow, "on", False)
        _allow.on = True
        os.environ.pop("HF_HUB_OFFLINE", None)

    def __exit__(self, *exc):
        _allow.on = self.prev
        os.environ["HF_HUB_OFFLINE"] = "1"


def install():
    global _installed
    if _installed:
        return
    _installed = True
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    orig_connect, orig_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _check(address)
        return orig_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _check(address)
        return orig_connect_ex(self, address)
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    log.info("offline guard on: only local connections allowed")
