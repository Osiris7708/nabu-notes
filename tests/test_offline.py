"""The offline guarantee: once Nobu starts, it cannot reach the internet, but it can still
talk to itself on this computer (the one-copy-at-a-time check uses that)."""
import _here  # finds the app and keeps the test away from your real notes
import socket
import nobu_offline

OK = []
def check(name, cond, info=""):
    OK.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "   -> %s" % (info,)))

nobu_offline.install()
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3).close()
    blocked, why = False, "connected"
except ConnectionRefusedError:
    blocked, why = True, ""
except OSError as e:          # no network at all also counts, but say so
    blocked, why = True, ""
    print("note: no network here, so this check is weaker (%s)" % e)
check("connections to the internet are blocked", blocked, why)

s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
try:
    socket.create_connection(s.getsockname(), timeout=2).close(); local = True
except OSError as e:
    local = False
check("connections on this computer still work", local)
s.close()
print("RESULT %d/%d passed" % (sum(OK), len(OK)))
