# usage: resolve_test.py <build_dir>   (nginx 1.27.3+, zone + resolve)
import json, os, re, subprocess, sys, time, urllib.request
S = os.path.dirname(os.path.abspath(__file__))
build = sys.argv[1]; inst = os.path.join(build, "inst"); nginx = os.path.join(inst, "sbin/nginx")
dynamic = os.path.exists(os.path.join(inst, "modules/ngx_http_upstream_check_module.so"))
NG, A, C, CTL, DNS = 19080, 19081, 19083, 19090, 19053
conf = """
%s
worker_processes 2;
error_log logs/error.log debug;
pid logs/nginx.pid;
events { worker_connections 1024; }
http {
    log_format ul '$upstream_addr $status';
    access_log logs/access.log ul;
    upstream rs {
        zone rs 64k;
        resolver 127.0.0.1:%d valid=1s;
        server 127.0.0.1:%d;
        server 127.0.0.1:%d;
        server dyn.test:%d resolve;
        check interval=300 rise=1 fall=1 timeout=500 type=http;
        check_http_send "GET /health HTTP/1.0\\r\\n\\r\\n";
    }
    server {
        listen %d;
        location / { proxy_pass http://rs; }
        location /status { check_status json; }
    }
}
""" % ('load_module modules/ngx_http_upstream_check_module.so;' if dynamic else '', DNS, A, C, C, NG)
open(os.path.join(inst, "conf/resolve.conf"), "w").write(conf)
for f in ("access.log", "error.log"):
    p = os.path.join(inst, "logs", f)
    if os.path.exists(p): os.unlink(p)
dns = subprocess.Popen([sys.executable, "-I", os.path.join(S, "dns.py"), str(DNS)])
be = subprocess.Popen([sys.executable, "-I", os.path.join(S, "backend.py"), str(CTL)], stderr=subprocess.DEVNULL)
time.sleep(0.5)
urllib.request.urlopen("http://127.0.0.1:%d/start?port=%d" % (CTL, A)).read()
fail = 0
try:
    subprocess.run([nginx, "-p", inst, "-c", "conf/resolve.conf"], check=True)
    time.sleep(2)
    for i in range(80):
        try: urllib.request.urlopen("http://127.0.0.1:%d/?i=%d" % (NG, i), timeout=3).read()
        except Exception as e: print("request error", e); fail = 1
        time.sleep(0.1)
    log = open(os.path.join(inst, "logs/error.log")).read()
    marks = re.findall(r"http check sync peer 127\.0\.0\.1:%d in upstream rs: down" % C, log)
    print("resolved peer re-marked down %d times" % len(marks))
    if len(marks) < 3: fail = 1
    acc = open(os.path.join(inst, "logs/access.log")).read()
    print("requests that tried C: %d of 80" % acc.count(":%d" % C))
    crit = [l for l in log.splitlines() if re.search(r"\[(alert|crit|emerg)\]", l)]
    print("alerts:", crit[:3]); fail |= bool(crit)
finally:
    subprocess.run([nginx, "-p", inst, "-c", "conf/resolve.conf", "-s", "stop"]); time.sleep(0.5)
    be.kill(); dns.kill()
print("RESOLVE", os.path.basename(build), "PASS" if not fail else "FAIL")
