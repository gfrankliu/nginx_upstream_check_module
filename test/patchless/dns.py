# Minimal DNS responder: answers A 127.0.0.1 (TTL 1) and NXDOMAIN alternately
# for A queries, so nginx keeps removing and re-creating the resolved peer.
import socket, struct, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("127.0.0.1", port))
n = 0
while True:
    data, addr = s.recvfrom(512)
    tid, flags, qd = struct.unpack("!HHH", data[:6])
    i = 12
    while data[i]: i += data[i] + 1
    q = data[12:i + 5]
    qtype = struct.unpack("!H", data[i + 1:i + 3])[0]
    if qtype != 1:
        s.sendto(struct.pack("!HHHHHH", tid, 0x8180, 1, 0, 0, 0) + q, addr); continue
    n += 1
    if n % 2 == 0:
        s.sendto(struct.pack("!HHHHHH", tid, 0x8183, 1, 0, 0, 0) + q, addr); continue
    ans = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 1, 4) + socket.inet_aton("127.0.0.1")
    s.sendto(struct.pack("!HHHHHH", tid, 0x8180, 1, 1, 0, 0) + q + ans, addr)
