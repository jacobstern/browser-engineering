import socket
import ssl
from typing import Optional

def parse_url(url: str) -> tuple[str, str, str]:
    scheme, url = url.split("://", 1)
    if "/" not in url: url = url + "/"
    host, path = url.split("/", 1)
    return (scheme, host, "/" + path)

def format_headers(headers: dict) -> bytes:
    lines = "".join("{}: {}\r\n".format(k, v) for k, v in headers.items())
    return lines.encode("utf8")

def request(url: str, headers: Optional[dict] = None) -> tuple[dict, str]:
    if headers is None:
        headers = {}

    scheme, host, path = parse_url(url)
    assert scheme in ["http", "https"], "Unknown scheme {}".format(scheme)
    port = 80 if scheme == "http" else 443
    if ":" in host:
        host, port_str = host.split(":", 1)
        port = int(port_str)

    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    if scheme == "https":
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)

    s.connect((host, port))
    
    headers['Host'] = host
    headers['Connection'] = 'close'
    headers.setdefault('User-Agent', 'MyBrowser/0.1')

    s.send("GET {} HTTP/1.1\r\n".format(path).encode("utf8") + 
        format_headers(headers) + b"\r\n")

    response = s.makefile("r", encoding="utf8", newline="\r\n")
    statusline = response.readline()
    _, status, explanation = statusline.split(" ", 2)
    assert status == "200", "{}: {}".format(status, explanation)

    headers = {}
    while True:
        line = response.readline()
        if line == "\r\n": break
        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()

    assert "transfer-encoding" not in headers
    assert "content-encoding" not in headers

    body = response.read()
    s.close()

    return headers, body

def show(body: str) -> None:
    in_angle = False
    for c in body:
        if c == "<":
            in_angle = True
        elif c == ">":
            in_angle = False
        elif not in_angle:
            print(c, end="")

def load(url: str) -> None:
    headers, body = request(url)
    show(body)

if __name__ == "__main__":
    import sys
    load(sys.argv[1])
