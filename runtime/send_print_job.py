"""send_print_job.py - 向 guest 内 mfp.afx 注入打印作业
用法:
  python runtime/send_print_job.py lpd 127.0.0.1 <port> runtime/pwg-job-1page.pwg
  python runtime/send_print_job.py raw 127.0.0.1 <port> runtime/pwg-job-1page.pwg
LPD 走 RFC1179 receive-job 流程; raw 直接发送文件字节(9100 风格)
"""
import socket
import sys
import time


def send_lpd(host, port, path, queue="lp"):
    data = open(path, "rb").read()
    hostn = "simhost"
    jobid = "001"
    cf = "cfA%s%s" % (jobid, hostn)
    df = "dfA%s%s" % (jobid, hostn)
    ctrl = ("H%s\nPsimuser\nJpwg-1page\nfdfA%s%s\nUdfA%s%s\nNpwg-1page.pwg\n"
            % (hostn, jobid, hostn, jobid, hostn)).encode()

    s = socket.create_connection((host, port), timeout=30)
    s.settimeout(30)

    def ack(expect=b"\x00", what=""):
        b = s.recv(1)
        print("ack(%s)=%r" % (what, b))
        return b == expect

    s.sendall(b"\x02" + queue.encode() + b"\n")
    if not ack(what="recv-job"):
        print("FAIL: queue rejected"); s.close(); return 1

    s.sendall(b"\x02%d %s\n" % (len(ctrl), cf))
    if not ack(what="ctrl-cmd"):
        print("FAIL: ctrl cmd rejected"); s.close(); return 1
    s.sendall(ctrl + b"\x00")
    if not ack(what="ctrl-data"):
        print("FAIL: ctrl data rejected"); s.close(); return 1

    s.sendall(b"\x03%d %s\n" % (len(data), df))
    if not ack(what="data-cmd"):
        print("FAIL: data cmd rejected"); s.close(); return 1
    # 分块发送
    for i in range(0, len(data), 65536):
        s.sendall(data[i:i + 65536])
    s.sendall(b"\x00")
    if not ack(what="data-data"):
        print("FAIL: data data rejected"); s.close(); return 1
    s.close()
    print("LPD job sent OK (%d bytes)" % len(data))
    return 0


def send_raw(host, port, path):
    data = open(path, "rb").read()
    s = socket.create_connection((host, port), timeout=30)
    for i in range(0, len(data), 65536):
        s.sendall(data[i:i + 65536])
    time.sleep(2)
    s.close()
    print("RAW job sent OK (%d bytes)" % len(data))
    return 0


if __name__ == "__main__":
    mode, host, port, path = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    sys.exit(send_lpd(host, port, path) if mode == "lpd" else send_raw(host, port, path))
