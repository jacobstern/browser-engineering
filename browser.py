import os.path
import socket
import ssl
import time
import tkinter
import tkinter.font

from functools import wraps
from pathlib import Path
from typing import Literal, Optional

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100

def timed(name: str):
    def inner(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            end = time.perf_counter()
            print(f"Time to {name}: {(end - start) * 1000:.2f}ms")
            return result
        return wrapped
    return inner

FONTS = {}

def get_font(size, weight, slant):
    key = (size, weight, slant)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=slant)
        FONTS[key] = font
    return FONTS[key]

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

def load_file(path: str) -> str:
    path = os.path.normpath(path)
    return Path(path).read_text()

def load_document(url: str) -> str:
    scheme, rest = url.split("://", 1)
    assert scheme in ["http", "https", "file"], "Unknown scheme {scheme}"
    if scheme == "file":
        return load_file(rest)
    _, body = request(url)
    return body

def show(body: str) -> None:
    in_angle = False
    for c in body:
        if c == "<":
            in_angle = True
        elif c == ">":
            in_angle = False
        elif not in_angle:
            print(c, end="")

class Text:
    def __init__(self, text):
        self.text = text

class Tag:
    def __init__(self, tag):
        self.tag = tag

def lex(body: str) -> list[Tag | Text]:
    out: list[Tag | Text] = []
    text = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
            if text: out.append(Text(text))
            text = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(text))
            text = ""
        else:
            text += c
    if not in_tag and text:
        out.append(Text(text))
    return out

class Layout:
    display_list: list
    weight: Literal["normal" , "bold"]
    style: Literal["roman" , "italic"]
    cursor_x: float
    cursor_y: float
    line: list

    @timed("layout")
    def __init__(self, tokens: list[Tag | Text]) -> None:
        self.display_list = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight = "normal"
        self.style = "roman"
        self.size = 16
        self.line = []

        for tok in tokens:
            self.token(tok)
        self.flush()

    def text(self, tok: Text) -> None:
        font = get_font(self.size, self.weight, self.style)
        for word in tok.text.split():
            w = font.measure(word)
            if self.cursor_x + w > WIDTH - HSTEP:
                self.flush()
            self.line.append((self.cursor_x, word, font))
            self.cursor_x += w + font.measure(" ")

    def flush(self) -> None:
        if not self.line: return
        metrics = [font.metrics() for _, _, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        self.cursor_x = HSTEP
        self.line = []
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.25 * max_descent

    def token(self, tok: Tag | Text) -> None:
        if isinstance(tok, Text):
            self.text(tok)
        elif tok.tag == "i":
            self.style = "italic"
        elif tok.tag == "/i":
            self.style = "roman"
        elif tok.tag == "b":
            self.weight = "bold"
        elif tok.tag == "/b":
            self.weight = "normal"
        elif tok.tag == "small":
            self.size -= 2
        elif tok.tag == "/small":
            self.size += 2
        elif tok.tag == "big":
            self.size += 4
        elif tok.tag == "/big":
            self.size -= 4
        elif tok.tag == "br":
            self.flush()
        elif tok.tag == "/p":
            self.flush()
            self.cursor_y += VSTEP

class Browser:

    def __init__(self):
        self.display_list = None
        self.scroll = 0
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window, 
            width=WIDTH,
            height=HEIGHT
        )
        self.canvas.pack()
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw()

    def scrollup(self, e):
        if self.scroll > 0:
            self.scroll -= SCROLL_STEP
            self.draw()

    def load(self, url: str) -> None:
        document = load_document(url)
        tokens = lex(document)
        self.display_list = Layout(tokens).display_list
        self.draw()

    @timed("draw")
    def draw(self) -> None:
        self.canvas.delete("all")
        for x, y, word, font in self.display_list:
            if y > self.scroll + HEIGHT: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(
                x,
                y - self.scroll,
                text=word,
                font=font,
                anchor="nw"
            )

DEFAULT_URL = "file:///Users/jacob/src/browser-engineering/test.html"

if __name__ == "__main__":
    import sys
    Browser().load(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL)
    tkinter.mainloop()
