# helpers shared by the runtime tests
import json, os, re, subprocess, sys, time, urllib.request

failures = []

def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg, flush=True)
    if not cond:
        failures.append(msg)

def get(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

class Nginx:
    def __init__(self, build, conf_name, port):
        self.inst = os.path.join(build, "inst")
        self.bin = os.path.join(self.inst, "sbin/nginx")
        self.dynamic = os.path.exists(os.path.join(self.inst, "modules/ngx_http_upstream_check_module.so"))
        self.conf = "conf/%s" % conf_name
        self.port = port
        os.makedirs(os.path.join(self.inst, "logs"), exist_ok=True)

    def load(self, *mods):
        if not self.dynamic:
            return ""
        return "".join("load_module modules/%s.so;\n" % m for m in mods)

    def write(self, text):
        open(os.path.join(self.inst, self.conf), "w").write(text)

    def log(self, name):
        p = os.path.join(self.inst, "logs", name)
        return open(p).read() if os.path.exists(p) else ""

    def start(self):
        for f in ("access.log", "error.log"):
            p = os.path.join(self.inst, "logs", f)
            if os.path.exists(p): os.unlink(p)
        t = subprocess.run([self.bin, "-p", self.inst, "-c", self.conf, "-t"], capture_output=True, text=True)
        if t.returncode:
            print(t.stderr); sys.exit(1)
        subprocess.run([self.bin, "-p", self.inst, "-c", self.conf], check=True)

    def signal(self, sig):
        subprocess.run([self.bin, "-p", self.inst, "-c", self.conf, "-s", sig])

    def status(self):
        d = json.loads(get("http://127.0.0.1:%d/status?format=json" % self.port)[1])
        return {(s["upstream"], s["name"]): s["status"] for s in d["servers"]["server"]}

    def wait_status(self, want, secs=8):
        """want maps (upstream, name) to "up", "down" or None (not listed)"""
        deadline = time.time() + secs
        st = {}
        while time.time() < deadline:
            try:
                st = self.status()
                if all(st.get(k) == v for k, v in want.items()):
                    return st
            except Exception:
                pass
            time.sleep(0.1)
        return st

    def burst(self, n, path="/"):
        start = len(self.log("access.log").splitlines())
        codes = [get("http://127.0.0.1:%d%s?k=%d" % (self.port, path, i))[0] for i in range(n)]
        time.sleep(0.3)
        ports = {}
        for l in self.log("access.log").splitlines()[start:]:
            for port in re.findall(r"127\.0\.0\.1:(\d+)", l):
                ports[int(port)] = ports.get(int(port), 0) + 1
        return codes, ports

    def alerts(self):
        return [l for l in self.log("error.log").splitlines()
                if re.search(r"\[(alert|crit|emerg)\]|signal \d+ .*exited on signal", l)]

class Backends:
    def __init__(self, here, ctl):
        self.ctl = ctl
        self.p = subprocess.Popen([sys.executable, "-I", os.path.join(here, "backend.py"), str(ctl)],
                                  stderr=subprocess.DEVNULL)
        time.sleep(0.5)

    def __call__(self, path):
        return json.loads(get("http://127.0.0.1:%d%s" % (self.ctl, path))[1])

    def kill(self):
        self.p.kill()

def done(name):
    print("RESULT %s: %s" % (name, "PASS" if not failures else "FAIL (%d)" % len(failures)))
    sys.exit(1 if failures else 0)
