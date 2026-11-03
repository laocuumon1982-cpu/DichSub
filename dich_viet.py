#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dịch Việt by Duy Anh v3.1 — dịch phụ đề và sách/truyện sang tiếng Việt, tạo phụ đề từ video/âm thanh.
Giao diện web chạy trong cửa sổ riêng (Edge/Chrome), backend Python.
- Phụ đề: .srt .ass .ssa .vtt — giữ nguyên timeline và thẻ định dạng.
- Sách: .epub .docx .txt .pdf .md .html .mobi .prc .azw .azw3 — chia chương, dịch theo đoạn, xuất lại đúng định dạng
  (Kindle xuất ra EPUB), hoặc TXT / EPUB. Từ điển tên riêng, văn phong, lưu tiến độ để dịch tiếp.
- Dịch vụ: GTX API (Free), Edge API (Free), Gemini, OpenAI, DeepSeek, Groq, OpenRouter, API tùy chỉnh,
  Ollama, LM Studio, HachimiMT (Trung -> Việt, chạy offline bằng GPU/CPU).
- Giọng nói ra phụ đề: Whisper (faster-whisper) chạy offline bằng GPU/CPU, hoặc Groq / OpenAI Whisper.
Một phần cách gọi GTX/Edge tham khảo từ rockbenben/subtitle-translator (MIT License).
"""
import base64
import html
import io
import json
import os
import posixpath
import queue
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_VERSION = "3.1.0"
APP_NAME = "Dịch Việt by Duy Anh v3.1"
GITHUB_REPO = "laocuumon1982-cpu/DichSub"     # nơi đăng bản mới (GitHub Releases)
PORT = 47863
HOME = os.path.expanduser("~")
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
# Bản portable: có file portable.ini cạnh exe -> mọi dữ liệu nằm trong thư mục data cạnh exe
PORTABLE = os.path.isfile(os.path.join(APP_DIR, "portable.ini"))
_LOCAL = os.environ.get("LOCALAPPDATA") or HOME
if PORTABLE:
    DATA_DIR = os.path.join(APP_DIR, "data")
    CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
    MODELS_DIR = os.path.join(DATA_DIR, "models")
    CUDA_DIR = os.path.join(DATA_DIR, "cuda")
else:
    DATA_DIR = os.path.join(_LOCAL, "DichViet") if sys.platform == "win32" else os.path.join(HOME, ".dich_viet")
    CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
    # dùng chung model HachimiMT và thư viện GPU với Dịch Sub, không phải tải lại
    _SHARED = os.path.join(_LOCAL, "DichSub") if sys.platform == "win32" else os.path.join(HOME, ".dich_sub")
    MODELS_DIR = os.path.join(_SHARED, "models")
    CUDA_DIR = os.path.join(_SHARED, "cuda")
LOG_PATH = os.path.join(DATA_DIR, "dichviet.log")
BOOKS_DIR = os.path.join(DATA_DIR, "books")
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
START_TIME = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")


def log_file(msg):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > 2_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + msg + "\n")
    except Exception:
        pass


NUM_LINE_RE = re.compile(r"^\s*\**\s*\[(\d+)\]\s*\**\s?(.*)$")
BR_RE = re.compile(r"\s*<br\s*/?>\s*", re.I)
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
TAG_WRAP_RE = re.compile(r"^((?:\s*(?:\{[^}]*\}|<[^>]+>))*)(.*?)((?:<[^>]+>\s*)*)$", re.S)
CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
KANA_RE = re.compile(r"[぀-ヿ]")
HANGUL_RE = re.compile(r"[가-힯]")
LATIN_RE = re.compile(r"[A-Za-z]")
WIRE_BR = " <br> "

LANG_NAMES = {
    "auto": "the source language", "en": "English", "zh-CN": "Simplified Chinese", "zh-TW": "Traditional Chinese",
    "ja": "Japanese", "ko": "Korean", "th": "Thai", "fr": "French", "de": "German", "es": "Spanish",
    "ru": "Russian", "id": "Indonesian", "pt": "Portuguese", "it": "Italian", "vi": "Vietnamese",
}
LANG_VI = {
    "auto": "Tự nhận", "en": "Tiếng Anh", "zh-CN": "Tiếng Trung", "zh-TW": "Tiếng Trung (phồn thể)",
    "ja": "Tiếng Nhật", "ko": "Tiếng Hàn", "th": "Tiếng Thái", "fr": "Tiếng Pháp", "de": "Tiếng Đức",
    "es": "Tiếng Tây Ban Nha", "ru": "Tiếng Nga", "id": "Tiếng Indonesia", "pt": "Tiếng Bồ Đào Nha",
    "it": "Tiếng Ý", "vi": "Tiếng Việt",
}

GTX_ENDPOINT = "https://translate-pa.googleapis.com/v1/translateHtml"
GTX_LEGACY = "https://translate.googleapis.com/translate_a/single"
GTX_PUBLIC_KEY = "AIzaSyATBXajvzQLTDHEQbcpq0Ihe0vWDHmO520"  # khóa công khai của Google Translate Element
EDGE_ENDPOINT = "https://edge.microsoft.com/translate/translatetext"
HF_BASE = "https://huggingface.co"
IS_WIN = sys.platform == "win32"
PYPI_BASE = "https://pypi.org"


# ================================================================ đọc / ghi sách

class Seg:
    """Một đoạn văn (hoặc tiêu đề) cần dịch."""
    __slots__ = ("src", "vi", "kind", "time", "line")

    def __init__(self, src, kind="p"):
        self.src = src      # nguyên văn (có thể có \n bên trong)
        self.vi = None      # bản dịch (None = chưa dịch)
        self.kind = kind    # p = đoạn văn, h = tiêu đề, s = dòng phụ đề
        self.time = None    # timeline (phụ đề)
        self.line = None    # vị trí dòng Dialogue (ASS)


class Book:
    def __init__(self, mode, segs, chapters, title, ext, **extra):
        self.mode = mode            # txt | md | html | epub | docx | pdf
        self.segs = segs
        self.chapters = chapters    # [{"title", "start", "end"}]
        self.title = title
        self.ext = ext
        self.extra = extra

    @property
    def kind(self):
        return "sub" if self.mode in SUB_MODES else "book"


CHAP_RE = re.compile(
    r"^\s*(?:第\s*[\d零〇一二三四五六七八九十百千万两]+\s*[章节節回卷集部篇幕]|序章|序言|楔子|引子|尾声|尾聲|后记|後記|番外|"
    r"(?:chương|chuong|hồi|quyển|phần|tập|chapter|part|book|volume|prologue|epilogue)\b\s*[\dIVXLC]*|"
    r"卷\s*[\d一二三四五六七八九十]+|[\d]{1,4}\s*[\.、:：]\s*\S{0,30}$)", re.I)
BLOCK_TAGS = r"p|h[1-6]|li|blockquote|dd|dt|figcaption|td|th|caption|div|pre"
BLOCK_RE = re.compile(
    r"(<(%s)\b[^>]*>)((?:(?!<(?:%s)\b|</(?:%s)\s*>).)*?)(</\2\s*>)" % (BLOCK_TAGS, BLOCK_TAGS, BLOCK_TAGS),
    re.S | re.I)
INLINE_TAG_RE = re.compile(r"<[^>]+>")
SENT_END_RE = re.compile(r"[.!?。！？…”\"」』:：]\s*$")


def read_text_bytes(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "gb18030", "big5", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def clean_line(s):
    return s.replace("　", " ").replace("\xa0", " ").strip()


def is_heading_text(s):
    return len(s) <= 80 and bool(CHAP_RE.match(s))


def make_chapters(segs, starts=None, chunk=120):
    """Chia chương: theo tiêu đề (đoạn kind h) và các điểm bắt đầu cho sẵn (mỗi file trong EPUB)."""
    marks = {}
    for st, title in (starts or []):
        if st < len(segs):
            marks.setdefault(st, title)
    for i, s in enumerate(segs):
        if s.kind == "h":
            marks[i] = None
    if not marks:
        marks = {k: f"Phần {k // chunk + 1}" for k in range(0, len(segs), chunk)}
    elif 0 not in marks:
        marks[0] = "Mở đầu"
    chs = []
    keys = sorted(marks)
    for n, k in enumerate(keys):
        end = keys[n + 1] if n + 1 < len(keys) else len(segs)
        if end <= k:
            continue
        title = marks[k] if marks[k] else segs[k].src.replace("\n", " ").strip()[:80]
        chs.append({"title": title or f"Chương {len(chs) + 1}", "start": k, "end": end})
    # chương quá dài không có tiêu đề bên trong -> chia nhỏ để dễ đọc
    out = []
    for c in chs:
        n = c["end"] - c["start"]
        if n > chunk * 4:
            for k in range(c["start"], c["end"], chunk * 2):
                part = (k - c["start"]) // (chunk * 2) + 1
                out.append({"title": f"{c['title']} ({part})", "start": k, "end": min(c["end"], k + chunk * 2)})
        else:
            out.append(c)
    return out


# ---------- TXT / Markdown

def parse_txt(text, md=False):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    segs, entries, fence = [], [], False
    for line in text.split("\n"):
        if md and line.strip().startswith("```"):
            fence = not fence
            entries.append(("raw", line))
            continue
        s = clean_line(line)
        if fence or not s:
            entries.append(("raw", line if fence else ""))
            continue
        prefix = ""
        if md:
            m = re.match(r"^(\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)+)", line)
            if m:
                prefix = m.group(1)
                s = line[len(prefix):].strip()
                if not s:
                    entries.append(("raw", line))
                    continue
            if re.fullmatch(r"[-*_=]{3,}|!\[.*\]\(.*\)", s):
                entries.append(("raw", line))
                continue
        kind = "h" if (md and prefix.strip().startswith("#")) or is_heading_text(s) else "p"
        entries.append(("seg", len(segs), prefix))
        segs.append(Seg(s, kind))
    return segs, entries


def build_txt(book, content):
    lines = []
    for e in book.extra["entries"]:
        if e[0] == "raw":
            lines.append(e[1])
            continue
        seg, prefix = book.segs[e[1]], e[2]
        for k, t in enumerate(seg_out(seg, content)):
            lines.append((prefix if k == 0 or book.mode == "md" else "") + t)
    return "\n".join(lines).rstrip("\n") + "\n"


def seg_out(seg, content):
    """Danh sách các khối văn bản xuất ra cho một đoạn, theo kiểu nội dung."""
    vi = seg.vi if seg.vi is not None else seg.src
    if content == "vi" or seg.vi is None or seg.vi == seg.src:
        return [vi]
    return [vi, seg.src] if content == "vi_src" else [seg.src, vi]


# ---------- HTML / XHTML (dùng cho EPUB và file .html)

def _html_text(inner):
    t = BR_RE.sub("\n", inner)
    t = INLINE_TAG_RE.sub("", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\r\f\v 　]+", " ", t)
    return "\n".join(x.strip() for x in t.split("\n") if x.strip())


def parse_html_doc(text, segs):
    """Tách các khối văn bản trong 1 file HTML. Trả về danh sách phần: chuỗi giữ nguyên hoặc tuple đoạn."""
    parts, pos = [], 0
    m_body = re.search(r"<body\b[^>]*>", text, re.I)
    start = m_body.end() if m_body else 0
    for m in BLOCK_RE.finditer(text, start):
        inner = m.group(3)
        if re.search(r"<(?:img|svg|image|math|table|script|style)\b", inner, re.I):
            continue
        plain = _html_text(inner)
        if not plain or not re.search(r"\w", plain):
            continue
        tag = m.group(2).lower()
        pre, core, suf = TAG_WRAP_RE.match(inner).groups()
        if INLINE_TAG_RE.search(BR_RE.sub("", core)):
            pre = suf = ""          # có thẻ định dạng ở giữa câu -> bỏ định dạng, giữ chữ
        parts.append(text[pos:m.start()])
        parts.append((len(segs), m.group(1), pre, suf, m.group(4), inner))
        segs.append(Seg(plain, "h" if tag in ("h1", "h2", "h3") else "p"))
        pos = m.end()
    parts.append(text[pos:])
    return parts


def build_html_doc(parts, segs, content):
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
            continue
        idx, open_tag, pre, suf, close, inner = p
        seg = segs[idx]
        blocks = seg_out(seg, content)
        for k, t in enumerate(blocks):
            if seg.vi is None or (t is seg.src and len(blocks) == 1):
                out.append(open_tag + inner + close)
                continue
            body = "<br/>".join(html.escape(x, quote=False) for x in t.split("\n"))
            if t is seg.src:   # bản gốc trong chế độ song ngữ: giữ nguyên định dạng, làm mờ
                ot = open_tag if "style=" in open_tag.lower() else open_tag[:-1].rstrip("/") + ' style="opacity:.62">'
                out.append(ot + inner + close)
            else:
                out.append(open_tag + pre + body + suf + close)
    return "".join(out)


def parse_html_file(text, name):
    segs = []
    parts = parse_html_doc(text, segs)
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    title = html.unescape(m.group(1)).strip() if m else os.path.splitext(name)[0]
    return Book("html", segs, make_chapters(segs), title, ".html", parts=parts)


# ---------- EPUB

def _attrs(tag):
    return {k.lower(): (v1 if v1 is not None and v1 != "" else v2) for k, v1, v2 in
            re.findall(r'([\w:.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', tag)}


def parse_epub(data, name):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    container = z.read("META-INF/container.xml").decode("utf-8", "replace")
    opf_path = re.search(r'full-path\s*=\s*"([^"]+)"', container).group(1)
    opf = z.read(opf_path).decode("utf-8", "replace")
    base = posixpath.dirname(opf_path)
    manifest = {}
    for tag in re.findall(r"<(?:\w+:)?item\b[^>]*>", opf):
        a = _attrs(tag)
        if a.get("id") and a.get("href"):
            manifest[a["id"]] = (a["href"], a.get("media-type", ""), a.get("properties", ""))
    spine = [_attrs(t).get("idref") for t in re.findall(r"<(?:\w+:)?itemref\b[^>]*>", opf)]
    m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf, re.S | re.I)
    title = html.unescape(m.group(1)).strip() if m else os.path.splitext(name)[0]
    segs, docs, starts = [], {}, []
    for idref in spine:
        if idref not in manifest:
            continue
        href, mtype, _ = manifest[idref]
        path = posixpath.normpath(posixpath.join(base, urllib.parse.unquote(href.split("#")[0])))
        if path not in names or path in docs or "html" not in (mtype or "html"):
            continue
        text = read_text_bytes(z.read(path))
        st = len(segs)
        docs[path] = parse_html_doc(text, segs)
        if len(segs) > st:
            starts.append((st, None if segs[st].kind == "h" else f"Phần {len(starts) + 1}"))
    if not segs:
        raise ValueError("EPUB không có nội dung chữ (có thể là truyện tranh/ảnh).")
    return Book("epub", segs, make_chapters(segs, starts), title, ".epub", raw=data, opf_path=opf_path, docs=docs)


def build_epub_orig(book, content, tgt):
    src = zipfile.ZipFile(io.BytesIO(book.extra["raw"]))
    titles = {}
    for s in book.segs:
        if s.kind == "h" and s.vi:
            titles[re.sub(r"\s+", " ", s.src).strip()] = s.vi.replace("\n", " ")

    def tr_title(m):
        t = re.sub(r"\s+", " ", html.unescape(INLINE_TAG_RE.sub("", m.group(2)))).strip()
        return m.group(1) + html.escape(titles[t], quote=False) + m.group(3) if t in titles else m.group(0)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        out.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for info in src.infolist():
            if info.filename == "mimetype":
                continue
            data = src.read(info.filename)
            if info.filename in book.extra["docs"]:
                data = build_html_doc(book.extra["docs"][info.filename], book.segs, content).encode("utf-8")
            elif info.filename == book.extra["opf_path"]:
                t = data.decode("utf-8", "replace")
                t = re.sub(r"(<dc:language[^>]*>)(.*?)(</dc:language>)", lambda m: m.group(1) + tgt + m.group(3), t, flags=re.S)
                data = t.encode("utf-8")
            elif titles and info.filename.lower().endswith((".ncx", "nav.xhtml", "toc.xhtml")):
                t = data.decode("utf-8", "replace")
                t = re.sub(r"(<text>)(.*?)(</text>)", tr_title, t, flags=re.S)
                t = re.sub(r"(<a\b[^>]*>)(.*?)(</a>)", tr_title, t, flags=re.S)
                data = t.encode("utf-8")
            out.writestr(info, data)
    return buf.getvalue()


def build_epub_new(book, content, tgt, title):
    """Tạo EPUB mới từ các chương (dùng khi xuất TXT/DOCX/PDF... sang EPUB)."""
    uid = "urn:uuid:" + str(uuid.uuid4())
    esc = lambda s: html.escape(s, quote=True)
    chap_files = []
    for n, ch in enumerate(book.chapters, 1):
        segs = book.segs[ch["start"]:ch["end"]]
        head = segs[0] if segs and segs[0].kind == "h" else None
        ch_title = (head.vi or head.src) if head else ch["title"]
        body = [f"<h2>{esc(ch_title.replace(chr(10), ' '))}</h2>"]
        for s in (segs[1:] if head else segs):
            blocks = seg_out(s, content)
            for k, t in enumerate(blocks):
                cls = ' class="goc"' if len(blocks) == 2 and t is s.src else ""
                tag = "h3" if s.kind == "h" else "p"
                body.append(f"<{tag}{cls}>" + "<br/>".join(esc(x) for x in t.split("\n")) + f"</{tag}>")
        fname = f"ch{n:04d}.xhtml"
        chap_files.append((fname, ch_title))
        doc = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
               f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{tgt}" xml:lang="{tgt}"><head><meta charset="utf-8"/>'
               f'<title>{esc(ch_title)}</title><link rel="stylesheet" href="style.css"/></head><body>'
               + "\n".join(body) + "</body></html>")
        chap_files[-1] = (fname, ch_title, doc)
    css = ("body{font-family:serif;line-height:1.6;margin:0 4%} h2{text-align:center;margin:1.2em 0}"
           " p{text-indent:1.5em;margin:.4em 0} p.goc{opacity:.62;font-size:.92em}")
    items = "\n".join(f'<item id="c{n}" href="{f}" media-type="application/xhtml+xml"/>' for n, (f, _, _) in enumerate(chap_files, 1))
    spine = "\n".join(f'<itemref idref="c{n}"/>' for n in range(1, len(chap_files) + 1))
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{uid}</dc:identifier><dc:title>{esc(title)}</dc:title><dc:language>{tgt}</dc:language>
<dc:creator>Dịch Truyện by Duy Anh</dc:creator><meta property="dcterms:modified">{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="css" href="style.css" media-type="text/css"/>
{items}
</manifest>
<spine toc="ncx">
{spine}
</spine>
</package>"""
    nav = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops"><head><meta charset="utf-8"/><title>Mục lục</title></head><body>'
           '<nav epub:type="toc"><h1>Mục lục</h1><ol>'
           + "".join(f'<li><a href="{f}">{esc(t)}</a></li>' for f, t, _ in chap_files) + "</ol></nav></body></html>")
    ncx = (f'<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content="{uid}"/></head><docTitle><text>{esc(title)}</text></docTitle><navMap>'
           + "".join(f'<navPoint id="n{n}" playOrder="{n}"><navLabel><text>{esc(t)}</text></navLabel><content src="{f}"/></navPoint>'
                     for n, (f, t, _) in enumerate(chap_files, 1)) + "</navMap></ncx>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:'
                   'opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/style.css", css)
        for f, _, doc in chap_files:
            z.writestr("OEBPS/" + f, doc)
    return buf.getvalue()


# ---------- DOCX

DOCX_P_RE = re.compile(r"<w:p(?:\s[^>]*[^/])?>(?:(?!<w:p[\s>]).)*?</w:p>", re.S)
DOCX_T_RE = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.S)


def parse_docx(data, name):
    z = zipfile.ZipFile(io.BytesIO(data))
    xml = z.read("word/document.xml").decode("utf-8")
    segs, parts, pos = [], [], 0
    for m in DOCX_P_RE.finditer(xml):
        p = m.group(0)
        text = "".join(html.unescape(t.group(2)) for t in DOCX_T_RE.finditer(p))
        text = clean_line(text)
        if not text or not re.search(r"\w", text):
            continue
        st = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        heading = bool(st and re.search(r"(?i)heading|title|tieude|berschrift|titre", st.group(1))) or is_heading_text(text)
        parts.append(xml[pos:m.start()])
        parts.append((len(segs), p))
        segs.append(Seg(text, "h" if heading else "p"))
        pos = m.end()
    parts.append(xml[pos:])
    if not segs:
        raise ValueError("File Word không có chữ.")
    return Book("docx", segs, make_chapters(segs), os.path.splitext(name)[0], ".docx", raw=data, parts=parts)


def _docx_fill(p, text):
    first = [True]

    def rep(m):
        if first[0]:
            first[0] = False
            ot = m.group(1)
            if "xml:space" not in ot:
                ot = ot[:-1] + ' xml:space="preserve">'
            return ot + html.escape(text.replace("\n", " "), quote=False) + m.group(3)
        return m.group(1) + m.group(3)
    return DOCX_T_RE.sub(rep, p)


def build_docx(book, content):
    out_xml = []
    for part in book.extra["parts"]:
        if isinstance(part, str):
            out_xml.append(part)
            continue
        idx, p = part
        seg = book.segs[idx]
        for t in seg_out(seg, content):
            out_xml.append(p if (seg.vi is None or t is seg.src) else _docx_fill(p, t))
    src = zipfile.ZipFile(io.BytesIO(book.extra["raw"]))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            data = "".join(out_xml).encode("utf-8") if info.filename == "word/document.xml" else src.read(info.filename)
            z.writestr(info, data)
    return buf.getvalue()


# ---------- PDF (cần thư viện pypdf, bản exe đã kèm)

def parse_pdf(data, name):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("Cần thư viện pypdf để đọc PDF (bản .exe đã kèm sẵn; chạy bằng Python thì gõ: pip install pypdf).")
    reader = PdfReader(io.BytesIO(data))
    lines = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        lines.extend(t.replace("\r", "\n").split("\n"))
        lines.append("")
    if sum(len(x.strip()) for x in lines) < 20:
        raise ValueError("PDF này là ảnh scan, không có chữ để dịch. Cần chuyển sang chữ (OCR) trước.")
    # ghép các dòng bị ngắt giữa câu thành đoạn văn
    paras, cur = [], ""
    for raw in lines:
        s = clean_line(raw)
        if not s:
            if cur:
                paras.append(cur)
                cur = ""
            continue
        if re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", s):   # số trang
            continue
        if is_heading_text(s):
            if cur:
                paras.append(cur)
            paras.append(s)
            cur = ""
            continue
        if not cur:
            cur = s
        else:
            joiner = "" if CJK_RE.search(cur[-1:]) or cur.endswith("-") else " "
            cur = (cur[:-1] if cur.endswith("-") and not CJK_RE.search(cur[-2:-1]) else cur) + joiner + s
        if SENT_END_RE.search(s) and len(s) < 40:
            paras.append(cur)
            cur = ""
    if cur:
        paras.append(cur)
    segs = [Seg(p, "h" if is_heading_text(p) else "p") for p in paras]
    entries = [("seg", i, "") for i in range(len(segs))]
    return Book("pdf", segs, make_chapters(segs), os.path.splitext(name)[0], ".txt", entries=entries)


# ---------- chung

def parse_book(data, name, cache_dir=None):
    book = _parse_book(data, name, cache_dir)
    book.src_ext = os.path.splitext(name)[1].lower() or book.ext
    return book


def _parse_book(data, name, cache_dir=None):
    ext = os.path.splitext(name)[1].lower()
    if ext in OFFICE_EXTS:
        return parse_docx(office_to_docx(data, name, cache_dir), name)
    if ext == ".pdf" and word_available():
        try:
            return parse_docx(office_to_docx(data, name, cache_dir), name)   # Word đọc PDF, giữ bố cục tốt hơn
        except Exception as e:
            log_file(f"Word không đọc được PDF {name}, dùng cách đọc chữ thường: {e}")
    if ext in (".srt", ".vtt", ".ass", ".ssa"):
        return parse_sub(read_text_bytes(data), name)
    if ext in KINDLE_EXTS:
        return parse_mobi(data, name)
    if ext == ".epub":
        return parse_epub(data, name)
    if ext == ".docx":
        return parse_docx(data, name)
    if ext == ".pdf":
        return parse_pdf(data, name)
    text = read_text_bytes(data)
    if ext in (".html", ".htm", ".xhtml"):
        return parse_html_file(text, name)
    md = ext in (".md", ".markdown")
    if not md and sum(1 for l in text[:200000].splitlines() if SUB_TIME_RE.match(l)) >= 3:
        return parse_sub(text, os.path.splitext(name)[0] + ".srt")   # file .txt thực ra là phụ đề
    segs, entries = parse_txt(text, md)
    if not segs:
        raise ValueError("File không có chữ.")
    return Book("md" if md else "txt", segs, make_chapters(segs), os.path.splitext(name)[0],
                ".md" if md else ".txt", entries=entries)


def detect_lang(segs):
    s = "".join(x.src for x in segs[:400])[:20000]
    latin, cjk = len(LATIN_RE.findall(s)), len(CJK_RE.findall(s))
    kana, hangul = len(KANA_RE.findall(s)), len(HANGUL_RE.findall(s))
    if hangul * 2 > latin and hangul > 10:
        return "ko"
    if kana >= 5 and kana >= cjk * 0.3:
        return "ja"
    if cjk and cjk * 3 >= latin:
        return "zh-CN"
    return "en"


def export_book(book, fmt, content, tgt):
    """Trả về (bytes, đuôi file). fmt: orig (giữ định dạng gốc) | epub | docx | pdf | txt."""
    if book.kind == "sub":
        if fmt == "txt":
            text = "\n".join("\n".join(seg_out(s, content)) for s in book.segs if s.src.strip()) + "\n"
            return text.replace("\n", "\r\n").encode("utf-8-sig"), ".txt"
        return build_sub(book, content).replace("\n", "\r\n").encode("utf-8-sig"), "." + book.mode
    src_ext = getattr(book, "src_ext", book.ext)
    if fmt == "orig":
        if src_ext in KINDLE_EXTS:
            return build_mobi(book, content, tgt), (".mobi" if src_ext == ".pdb" else src_ext)
        if book.mode == "epub":
            return build_epub_orig(book, content, tgt), ".epub"
        if book.mode == "docx":
            data = build_docx(book, content)
            if src_ext in (".docx", ""):
                return data, ".docx"
            try:
                return docx_to_office(data, src_ext), src_ext      # .doc .rtf .odt .pdf qua Word
            except Exception as e:
                log_file(f"Không lưu lại được {src_ext}: {e}")
                if src_ext == ".pdf":
                    return build_pdf_new(book, content, tgt), ".pdf"
                return data, ".docx"
        if book.mode == "pdf":
            return build_pdf_new(book, content, tgt), ".pdf"
        if book.mode == "html":
            return build_html_doc(book.extra["parts"], book.segs, content).encode("utf-8"), ".html"
        if book.mode in ("txt", "md"):
            return build_txt(book, content).replace("\n", "\r\n").encode("utf-8-sig"), book.ext
    if fmt == "epub":
        if book.mode == "epub":
            return build_epub_orig(book, content, tgt), ".epub"
        return build_epub_new(book, content, tgt, book.title), ".epub"
    if fmt == "docx":
        if book.mode == "docx":
            return build_docx(book, content), ".docx"
        return build_docx_new(book, content, tgt), ".docx"
    if fmt == "pdf":
        if book.mode == "docx" and word_available():
            try:
                return docx_to_office(build_docx(book, content), ".pdf"), ".pdf"
            except Exception as e:
                log_file(f"Word không xuất được PDF: {e}")
        return build_pdf_new(book, content, tgt), ".pdf"
    # TXT cho mọi định dạng
    if book.mode in ("txt", "md", "pdf"):
        if book.mode == "pdf":
            text = "\n\n".join("\n".join(seg_out(s, content)) for s in book.segs)
        else:
            text = build_txt(book, content)
    else:
        out = []
        for ch in book.chapters:
            for s in book.segs[ch["start"]:ch["end"]]:
                out.append("\n".join(seg_out(s, content)))
                if s.kind == "h":
                    out.append("")
            out.append("")
        text = "\n".join(out)
    return text.replace("\n", "\r\n").encode("utf-8-sig"), ".txt"


# ================================================================ phụ đề (SRT / VTT / ASS)

SUB_TIME_RE = re.compile(r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3}\s*-->\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{1,3}")
SUB_MODES = ("srt", "vtt", "ass")


def _drop_index_line(body):
    while body and not body[-1].strip():
        body.pop()
    if body and body[-1].strip().isdigit():
        body.pop()


def _parse_timed(lines, vtt):
    groups, header = [], []
    for line in lines:
        if SUB_TIME_RE.match(line):
            if groups:
                _drop_index_line(groups[-1][1])
            elif vtt and header and header[-1].strip() and not header[-1].lstrip("﻿").startswith("WEBVTT"):
                header.pop()
            groups.append((line.strip(), []))
        elif groups:
            groups[-1][1].append(line)
        else:
            header.append(line)
    cues = []
    for t, body in groups:
        if vtt:
            text = []
            for l in body:
                if not l.strip():
                    break
                text.append(l.strip())
        else:
            text = [l.strip() for l in body if l.strip()]
        cues.append((t, "\n".join(text), None, False))
    return cues, header


def _parse_ass(lines):
    cues, in_events, text_idx = [], False, 9
    for k, l in enumerate(lines):
        s = l.strip()
        if s.startswith("["):
            in_events = s.lower() == "[events]"
        elif in_events and s.lower().startswith("format:"):
            fields = [f.strip().lower() for f in s[7:].split(",")]
            if "text" in fields:
                text_idx = fields.index("text")
        elif in_events and s.startswith("Dialogue:"):
            head, body = l.split(":", 1)
            parts = body.split(",", text_idx)
            if len(parts) <= text_idx:
                continue
            prefix = head + ":" + ",".join(parts[:text_idx]) + ","
            txt = parts[text_idx]
            t = f"{parts[1].strip()} --> {parts[2].strip()}" if len(parts) > 2 else ""
            drawing = bool(re.search(r"\{[^}]*\\p[1-9]", txt))
            cues.append((t, txt.replace("\\N", "\n").replace("\\n", "\n"), (k, prefix), drawing))
    return cues


def _short_time(t):
    m = re.match(r"\s*((?:\d{1,2}:)?\d{1,2}:\d{2})", t or "")
    return m.group(1) if m else ""


def parse_sub(text, name):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    ext = os.path.splitext(name)[1].lower()
    extra = {}
    if ext in (".ass", ".ssa") or ("[Events]" in text and "Dialogue:" in text):
        mode, cues = "ass", _parse_ass(lines)
        extra["lines"] = lines
    elif ext == ".vtt" or text.lstrip("﻿").startswith("WEBVTT"):
        cues, header = _parse_timed(lines, True)
        mode, extra["header"] = "vtt", header or ["WEBVTT"]
    else:
        mode, (cues, _) = "srt", _parse_timed(lines, False)
    if not cues:
        raise ValueError("Không tìm thấy dòng phụ đề nào.")
    segs = []
    for t, src, line, drawing in cues:
        s = Seg(src, "s")
        s.time, s.line = t, line
        if drawing:
            s.vi = src
        segs.append(s)
    chapters = []
    for k in range(0, len(segs), 100):
        part = segs[k:k + 100]
        chapters.append({"title": f"{_short_time(part[0].time)} – {_short_time(part[-1].time)}",
                         "start": k, "end": k + len(part)})
    return Book(mode, segs, chapters, os.path.splitext(name)[0], "." + mode, **extra)


def build_sub(book, content):
    def body(s):
        return "\n".join(seg_out(s, content))
    if book.mode == "ass":
        lines = list(book.extra["lines"])
        for s in book.segs:
            k, prefix = s.line
            lines[k] = prefix + body(s).replace("\n", "\\N")
        return "\n".join(lines).rstrip("\n") + "\n"
    blocks = []
    for n, s in enumerate(book.segs, 1):
        head = f"{n}\n{s.time}" if book.mode == "srt" else s.time
        blocks.append(f"{head}\n{body(s)}".rstrip("\n") + "\n")
    out = "\n".join(blocks)
    if book.mode == "vtt":
        out = ("\n".join(book.extra.get("header") or []).strip("\n") or "WEBVTT") + "\n\n" + out
    return out


# ================================================================ Kindle: MOBI / PRC / AZW / AZW3

def _palmdoc_decompress(data):
    out, i, n = bytearray(), 0, len(data)
    while i < n:
        c = data[i]
        i += 1
        if 1 <= c <= 8:
            out += data[i:i + c]
            i += c
        elif c <= 0x7F:
            out.append(c)
        elif c >= 0xC0:
            out += b" "
            out.append(c ^ 0x80)
        else:
            if i >= n:
                break
            c = (c << 8) | data[i]
            i += 1
            dist, length = (c >> 3) & 0x07FF, (c & 7) + 3
            if dist == 0 or dist > len(out):
                continue
            for _ in range(length):
                out.append(out[-dist])
    return bytes(out)


def _trailing_size(rec, flags):
    """Số byte 'trailing entries' ở cuối mỗi bản ghi văn bản MOBI (theo cờ extra_flags)."""
    def entry_size(size):
        bitpos = result = 0
        while size > 0:
            v = rec[size - 1]
            result |= (v & 0x7F) << bitpos
            bitpos += 7
            size -= 1
            if (v & 0x80) or bitpos >= 28:
                break
        return result
    num, f = 0, flags >> 1
    while f:
        if f & 1:
            num += entry_size(len(rec) - num)
        f >>= 1
    if flags & 1 and len(rec) - num - 1 >= 0:
        num += (rec[len(rec) - num - 1] & 0x3) + 1
    return num


def parse_mobi(data, name):
    if len(data) < 86 or data[60:68] not in (b"BOOKMOBI", b"TEXtREAd"):
        raise ValueError("Không phải file MOBI/PRC/AZW hợp lệ.")
    nrec = struct.unpack(">H", data[76:78])[0]
    offs = [struct.unpack(">I", data[78 + 8 * i:82 + 8 * i])[0] for i in range(nrec)] + [len(data)]
    rec0 = data[offs[0]:offs[1]]
    compression, _, text_len, rec_count = struct.unpack(">HHIH", rec0[:10])
    encryption = struct.unpack(">H", rec0[12:14])[0]
    if encryption:
        raise ValueError("Sách có DRM (khoá bản quyền Kindle) nên không đọc được.")
    if compression == 17480:
        raise ValueError("Sách Kindle này nén kiểu HUFF/CDIC, app chưa đọc được. "
                         "Hãy mở bằng Calibre và chuyển sang EPUB rồi thêm lại.")
    if compression not in (1, 2):
        raise ValueError(f"Kiểu nén MOBI {compression} chưa hỗ trợ.")
    enc, flags, title = "cp1252", 0, os.path.splitext(name)[0]
    if rec0[16:20] == b"MOBI":
        hlen = struct.unpack(">I", rec0[20:24])[0]
        enc = "utf-8" if struct.unpack(">I", rec0[28:32])[0] == 65001 else "cp1252"
        if hlen >= 0xE4 and len(rec0) >= 0xF4:
            flags = struct.unpack(">H", rec0[0xF2:0xF4])[0]
        t_off, t_len = struct.unpack(">II", rec0[0x54:0x5C])
        if 0 < t_len < 1000 and t_off + t_len <= len(rec0):
            title = rec0[t_off:t_off + t_len].decode(enc, "replace").strip() or title
    chunks = []
    for i in range(1, min(rec_count, nrec - 1) + 1):
        rec = data[offs[i]:offs[i + 1]]
        if flags:
            cut = _trailing_size(rec, flags)
            rec = rec[:len(rec) - cut] if 0 < cut <= len(rec) else rec
        chunks.append(_palmdoc_decompress(rec) if compression == 2 else rec)
    raw = b"".join(chunks)[:text_len] if text_len else b"".join(chunks)
    text = raw.decode(enc, "replace")
    if data[60:68] == b"TEXtREAd" or not re.search(r"<(?:p|div|h\d)\b", text, re.I):
        segs, entries = parse_txt(re.sub(r"<[^>]+>", "", text))
        if not segs:
            raise ValueError("Không tìm thấy chữ trong sách Kindle này.")
        return Book("txt", segs, make_chapters(segs), title, ".txt", entries=entries)
    text = re.sub(r"<mbp:pagebreak\s*/?>", "<hr/>", text, flags=re.I)
    if "<body" not in text.lower():
        text = "<html><body>" + text + "</body></html>"
    segs = []
    parts = parse_html_doc(text, segs)
    if not segs:
        raise ValueError("Không tìm thấy chữ trong sách Kindle này.")
    return Book("mobi", segs, make_chapters(segs), title, ".epub", parts=parts)


# ================================================================ Microsoft Word / LibreOffice (đọc .doc .rtf .odt, đọc và xuất PDF)

OFFICE_EXTS = (".doc", ".rtf", ".odt", ".docm", ".dot", ".dotx", ".dotm", ".wps")
KINDLE_EXTS = (".mobi", ".prc", ".azw", ".azw3", ".pdb")
WORD_FMT = {".docx": 16, ".doc": 0, ".rtf": 6, ".odt": 23, ".pdf": 17, ".docm": 13, ".dot": 1, ".dotx": 14, ".dotm": 15}
SOFFICE_FILTER = {".docx": "docx:MS Word 2007 XML", ".doc": "doc:MS Word 97", ".rtf": "rtf", ".odt": "odt",
                  ".pdf": "pdf:writer_pdf_Export", ".docm": "docx:MS Word 2007 XML"}
_OFFICE = {}


def _run_ps(script, timeout):
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def word_available():
    if not IS_WIN:
        return False
    if "word" not in _OFFICE:
        try:
            code, out = _run_ps("[bool]([type]::GetTypeFromProgID('Word.Application'))", 40)
            _OFFICE["word"] = "True" in out
        except Exception:
            _OFFICE["word"] = False
        log_file(f"Microsoft Word: {'có' if _OFFICE['word'] else 'không có'}")
    return _OFFICE["word"]


def soffice_path():
    if "soffice" not in _OFFICE:
        cands = [shutil.which("soffice"), shutil.which("libreoffice")]
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                cands.append(os.path.join(base, "LibreOffice", "program", "soffice.exe"))
        _OFFICE["soffice"] = next((c for c in cands if c and os.path.exists(c)), None)
    return _OFFICE["soffice"]


def office_info():
    return {"word": word_available(), "libreoffice": bool(soffice_path())}


def _ps_str(path):
    return "'" + path.replace("'", "''") + "'"


def office_convert(src, dst, timeout=1800):
    """Chuyển đổi tài liệu bằng Microsoft Word (ưu tiên) hoặc LibreOffice. Ném ValueError nếu không làm được."""
    ext_in, ext_out = os.path.splitext(src)[1].lower(), os.path.splitext(dst)[1].lower()
    errs = []
    if word_available() and ext_out in WORD_FMT:
        script = f"""
$ErrorActionPreference = 'Stop'
try {{ New-Item -Path 'HKCU:\\Software\\Microsoft\\Office\\16.0\\Word\\Options' -Force | Out-Null;
      Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Office\\16.0\\Word\\Options' -Name DisableConvertPdfWarning -Value 1 -Type DWord }} catch {{}}
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {{
  $d = $w.Documents.Open({_ps_str(src)}, $false, $true, $false)
  $d.SaveAs2({_ps_str(dst)}, {WORD_FMT[ext_out]})
  $d.Close(0)
  Write-Output 'OK'
}} finally {{ $w.Quit() }}
"""
        try:
            code, out = _run_ps(script, timeout)
            if os.path.isfile(dst) and os.path.getsize(dst) > 0:
                return
            errs.append("Word: " + out.strip()[-300:])
        except subprocess.TimeoutExpired:
            errs.append("Word: quá thời gian chờ")
        except Exception as e:
            errs.append(f"Word: {e}")
    so = soffice_path()
    if so and ext_out in SOFFICE_FILTER and ext_in != ".pdf":
        out_dir = os.path.dirname(dst)
        try:
            p = subprocess.run([so, "--headless", "--norestore", "--convert-to", SOFFICE_FILTER[ext_out], "--outdir", out_dir, src],
                               capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
            made = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ext_out)
            if os.path.isfile(made):
                if made != dst:
                    os.replace(made, dst)
                return
            errs.append("LibreOffice: " + ((p.stdout or "") + (p.stderr or "")).strip()[-300:])
        except Exception as e:
            errs.append(f"LibreOffice: {e}")
    if not errs:
        raise ValueError(f"Cần Microsoft Word (hoặc LibreOffice) trên máy để đọc/ghi file {ext_in if ext_in != '.docx' else ext_out}.")
    log_file("Chuyển đổi Office lỗi: " + " | ".join(errs))
    raise ValueError("Không chuyển đổi được bằng Word/LibreOffice: " + " | ".join(errs))


def office_to_docx(data, name, cache_dir=None):
    """Đọc .doc/.rtf/.odt/.pdf bằng Word: trả về bytes .docx (có lưu cache để lần sau không phải chuyển lại)."""
    if cache_dir:
        cached = os.path.join(cache_dir, "converted.docx")
        if os.path.isfile(cached):
            with open(cached, "rb") as f:
                return f.read()
    import tempfile
    ext = os.path.splitext(name)[1].lower()
    with tempfile.TemporaryDirectory(prefix="dichviet_") as tmp:
        src = os.path.join(tmp, "input" + ext)
        dst = os.path.join(tmp, "converted.docx")
        with open(src, "wb") as f:
            f.write(data)
        office_convert(src, dst)
        with open(dst, "rb") as f:
            out = f.read()
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "converted.docx"), "wb") as f:
            f.write(out)
    return out


def docx_to_office(docx_bytes, ext):
    import tempfile
    with tempfile.TemporaryDirectory(prefix="dichviet_") as tmp:
        src = os.path.join(tmp, "output.docx")
        dst = os.path.join(tmp, "output" + ext)
        with open(src, "wb") as f:
            f.write(docx_bytes)
        office_convert(src, dst)
        with open(dst, "rb") as f:
            return f.read()


# ================================================================ tạo Word (.docx) mới

def build_docx_new(book, content, tgt):
    x = lambda t: html.escape(t, quote=False)

    def para(text, style=None, gray=False):
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        rpr = '<w:rPr><w:color w:val="808080"/><w:sz w:val="20"/></w:rPr>' if gray else ""
        runs = '<w:r>' + rpr + '<w:br/>'.join(f'<w:t xml:space="preserve">{x(l)}</w:t>' for l in text.split("\n")) + '</w:r>'
        return f"<w:p>{ppr}{runs}</w:p>"
    body = [para(book.title, "Title")]
    for n, ch in enumerate(book.chapters):
        segs = book.segs[ch["start"]:ch["end"]]
        if n:
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        for s in segs:
            blocks = seg_out(s, content)
            for t in blocks:
                body.append(para(t, "Heading1" if s.kind == "h" else None, gray=(len(blocks) == 2 and t is s.src)))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1418" '
           'w:bottom="1418" w:left="1418" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
              'w:eastAsia="SimSun" w:cs="Times New Roman"/><w:sz w:val="26"/><w:lang w:val="' + tgt + '"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="312" w:lineRule="auto"/><w:jc w:val="both"/>'
              '<w:ind w:firstLine="425"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:jc w:val="center"/><w:ind w:firstLine="0"/><w:spacing w:before="2400" w:after="600"/></w:pPr>'
              '<w:rPr><w:b/><w:sz w:val="44"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
              '<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:jc w:val="center"/><w:ind w:firstLine="0"/>'
              '<w:spacing w:before="240" w:after="240"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
              '</w:styles>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   '</Relationships>')
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", styles)
    return buf.getvalue()


# ================================================================ tạo PDF mới (ReportLab, nhúng font có dấu tiếng Việt)

def _font_dirs():
    d = []
    if IS_WIN:
        d.append(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
        d.append(os.path.join(_LOCAL, "Microsoft", "Windows", "Fonts"))
    d += ["/usr/share/fonts", "/Library/Fonts", "/System/Library/Fonts", os.path.join(HOME, ".fonts")]
    return d


def _find_font(names):
    for base in _font_dirs():
        if not os.path.isdir(base):
            continue
        for name in names:
            p = os.path.join(base, name)
            if os.path.isfile(p):
                return p
        for root, _, files in os.walk(base):
            low = {f.lower(): f for f in files}
            for name in names:
                if name.lower() in low:
                    return os.path.join(root, low[name.lower()])
    return None


_PDF_FONTS = {}


def _pdf_fonts():
    if _PDF_FONTS:
        return _PDF_FONTS
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pairs = [("times.ttf", "timesbd.ttf"), ("arial.ttf", "arialbd.ttf"), ("segoeui.ttf", "segoeuib.ttf"),
             ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf"), ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf"),
             ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")]
    for reg, bold in pairs:
        r = _find_font([reg])
        if r:
            pdfmetrics.registerFont(TTFont("Body", r))
            b = _find_font([bold])
            pdfmetrics.registerFont(TTFont("Body-Bold", b or r))
            _PDF_FONTS["body"] = "Body"
            _PDF_FONTS["bold"] = "Body-Bold"
            break
    if not _PDF_FONTS:
        raise ValueError("Không tìm thấy font chữ có dấu tiếng Việt trên máy để tạo PDF.")
    for name in ("msyh.ttc", "simsun.ttc", "msjh.ttc", "simhei.ttf", "YuGothM.ttc", "msgothic.ttc", "malgun.ttf",
                 "wqy-zenhei.ttc", "wqy-microhei.ttc", "fonts-japanese-gothic.ttf"):
        p = _find_font([name])
        if not p:
            continue
        try:
            pdfmetrics.registerFont(TTFont("CJK", p, subfontIndex=0) if p.lower().endswith(".ttc") else TTFont("CJK", p))
            _PDF_FONTS["cjk"] = "CJK"
            break
        except Exception as e:
            log_file(f"Font {p} không dùng được cho PDF: {e}")
    return _PDF_FONTS


def build_pdf_new(book, content, tgt):
    """PDF mới bằng ReportLab; thiếu thư viện thì nhờ Word/LibreOffice chuyển từ DOCX."""
    try:
        import reportlab.platypus, PIL  # noqa: F401
    except ImportError as e:
        log_file(f"Thiếu thư viện tạo PDF ({e}), chuyển qua Word/LibreOffice")
        try:
            return docx_to_office(build_docx_new(book, content, tgt), ".pdf")
        except Exception as e2:
            raise RuntimeError("Không tạo được PDF: máy thiếu thư viện reportlab/pillow và không có Word hay LibreOffice. "
                               "Hãy chọn xuất Word (DOCX) hoặc build lại exe bằng Tao_file_EXE.bat.") from e2
    return _build_pdf_rl(book, content, tgt)


def _build_pdf_rl(book, content, tgt):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
    fonts = _pdf_fonts()
    body = ParagraphStyle("b", fontName=fonts["body"], fontSize=11.5, leading=17.5, firstLineIndent=16,
                          spaceAfter=5, alignment=TA_JUSTIFY)
    head = ParagraphStyle("h", fontName=fonts["bold"], fontSize=16, leading=22, alignment=TA_CENTER,
                          spaceBefore=6, spaceAfter=14)
    title = ParagraphStyle("t", parent=head, fontSize=24, leading=32, spaceBefore=7 * cm)
    gray = ParagraphStyle("g", parent=body, textColor="#777777", fontSize=10.5, leading=15)

    def P(text, style):
        t = html.escape(text, quote=False).replace("\n", "<br/>")
        if CJK_RE.search(text) and fonts.get("cjk"):
            style = ParagraphStyle("c" + style.name, parent=style, fontName=fonts["cjk"], wordWrap="CJK")
        return Paragraph(t, style)
    story = [P(book.title, title), PageBreak()]
    for n, ch in enumerate(book.chapters):
        if n:
            story.append(PageBreak())
        for s in book.segs[ch["start"]:ch["end"]]:
            blocks = seg_out(s, content)
            for t in blocks:
                st = head if s.kind == "h" else (gray if len(blocks) == 2 and t is s.src else body)
                story.append(P(t, st))

    def page_no(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonts["body"], 9)
        canvas.drawCentredString(A4[0] / 2, 1.2 * cm, str(doc.page))
        canvas.restoreState()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2.2 * cm,
                            bottomMargin=2.2 * cm, title=book.title, author="Dịch Việt by Duy Anh")
    doc.build(story, onLaterPages=page_no)
    return buf.getvalue()


# ================================================================ tạo sách Kindle (MOBI / PRC / AZW3)

def build_mobi(book, content, tgt):
    e = lambda t: html.escape(t, quote=False).replace("\n", "<br/>")
    parts = ["<html><head><guide></guide></head><body>"]
    for n, ch in enumerate(book.chapters):
        if n:
            parts.append("<mbp:pagebreak/>")
        for s in book.segs[ch["start"]:ch["end"]]:
            blocks = seg_out(s, content)
            for t in blocks:
                if s.kind == "h":
                    parts.append(f'<h2 align="center">{e(t)}</h2>')
                elif len(blocks) == 2 and t is s.src:
                    parts.append(f'<p><font color="#777777">{e(t)}</font></p>')
                else:
                    parts.append(f"<p>{e(t)}</p>")
    parts.append("</body></html>")
    text = "".join(parts).encode("utf-8")
    recs, i = [], 0
    while i < len(text):            # bản ghi 4096 byte, không cắt giữa ký tự UTF-8
        j = min(i + 4096, len(text))
        while j < len(text) and j > i and (text[j] & 0xC0) == 0x80:
            j -= 1
        recs.append(text[i:j])
        i = j
    title = book.title.encode("utf-8")

    def exth_rec(t, data):
        return struct.pack(">II", t, 8 + len(data)) + data
    ex = exth_rec(100, "Dịch Việt by Duy Anh".encode("utf-8")) + exth_rec(503, title) + exth_rec(524, tgt.encode())
    exth = b"EXTH" + struct.pack(">II", 12 + len(ex), 3) + ex
    exth += b"\0" * ((4 - len(exth) % 4) % 4)
    mobi = bytearray(232)
    struct.pack_into(">4sIIII", mobi, 0, b"MOBI", 232, 2, 65001, int(time.time()) & 0x7FFFFFFF)
    struct.pack_into(">I", mobi, 20, 6)
    for off in range(24, 64, 4):
        struct.pack_into(">I", mobi, off, 0xFFFFFFFF)
    struct.pack_into(">IIIIIIII", mobi, 64, len(recs) + 1, 16 + 232 + len(exth), len(title),
                     0x2A if tgt == "vi" else 9, 0, 0, 6, 0xFFFFFFFF)
    struct.pack_into(">I", mobi, 112, 0x40)                      # có EXTH
    struct.pack_into(">II", mobi, 148, 0xFFFFFFFF, 0xFFFFFFFF)   # DRM: không
    struct.pack_into(">HHI", mobi, 176, 1, len(recs), 1)
    struct.pack_into(">II", mobi, 184, 0xFFFFFFFF, 0)
    struct.pack_into(">II", mobi, 192, 0xFFFFFFFF, 0)
    struct.pack_into(">III", mobi, 208, 0xFFFFFFFF, 0, 0xFFFFFFFF)
    struct.pack_into(">I", mobi, 220, 0xFFFFFFFF)
    struct.pack_into(">II", mobi, 224, 0, 0xFFFFFFFF)
    palmdoc = struct.pack(">HHIHHHH", 1, 0, len(text), len(recs), 4096, 0, 0)
    rec0 = palmdoc + bytes(mobi) + exth + title + b"\0\0"
    rec0 += b"\0" * ((4 - len(rec0) % 4) % 4)
    records = [rec0] + recs + [b"\xe9\x8e\x0d\x0a"]
    n = len(records)
    name = re.sub(r"[^A-Za-z0-9]+", "_", html.unescape(book.title).encode("ascii", "ignore").decode())[:31] or "book"
    now = int(time.time())
    head = struct.pack(">32sHHIIIIII4s4sIIH", name.encode().ljust(32, b"\0")[:31] + b"\0", 0, 0, now, now, 0, 0, 0, 0,
                       b"BOOK", b"MOBI", 2 * n - 1, 0, n)
    off = len(head) + 8 * n + 2
    lst = b""
    for k, r in enumerate(records):
        lst += struct.pack(">II", off, 2 * k)
        off += len(r)
    return head + lst + b"\0\0" + b"".join(records)


# ---------- tiện ích dịch

def to_wire(text):
    return text.replace("\n", WIRE_BR)


def from_wire(text):
    return "\n".join(p for p in BR_RE.split(text.strip()) if p.strip())


def parse_numbered(resp, expected):
    """Đọc kết quả dạng '[N] text'. expected = {N: số dòng của đoạn gốc}."""
    resp = THINK_RE.sub("", resp or "")
    out, last = {}, None
    for raw in resp.split("\n"):
        line = raw.strip().strip("`")
        if not line:
            continue
        m = NUM_LINE_RE.match(line)
        if m and int(m.group(1)) in expected:
            last = int(m.group(1))
            out[last] = m.group(2).strip()
        elif last is not None and out.get(last):
            if len(BR_RE.split(out[last])) < expected.get(last, 1):
                out[last] += WIRE_BR + line
    return out


def expected_of(segs, idxs):
    return {i + 1: segs[i].src.count("\n") + 1 for i in idxs}


def prepare_todo(segs):
    todo = []
    for i, c in enumerate(segs):
        if c.vi is None:
            if c.src.strip():
                todo.append(i)
            else:
                c.vi = c.src
    return todo


def remaining_count(segs):
    return sum(1 for c in segs if c.vi is None and c.src.strip())


def split_piece(text, maxlen):
    """Cắt câu dài thành các mẩu <= maxlen ký tự (theo dấu câu) cho máy dịch."""
    if len(text) <= maxlen:
        return [text]
    out, buf = [], ""
    for tok in re.split(r"(?<=[。！？!?…；;.])", text):
        if buf and len(buf) + len(tok) > maxlen:
            out.append(buf)
            buf = ""
        buf += tok
    if buf:
        out.append(buf)
    res = []
    for p in out:
        if len(p) <= maxlen:
            res.append(p)
            continue
        b = ""
        for tok in re.split(r"(?<=[，,、：:])", p):
            if b and len(b) + len(tok) > maxlen:
                res.append(b)
                b = ""
            while len(tok) > maxlen:
                res.append(tok[:maxlen])
                tok = tok[maxlen:]
            b += tok
        if b:
            res.append(b)
    return [r for r in res if r.strip()]


def parse_pairs(text):
    """Đọc danh sách 'nguyên văn = bản dịch' (mỗi dòng một cặp)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.split(r"\s*(?:=>|→|->|=|\t)\s*", line, maxsplit=1)
        if len(m) == 2 and m[0].strip():
            out.append((m[0].strip(), m[1].strip()))   # vế phải rỗng = xoá chữ đó
    return sorted(out, key=lambda x: -len(x[0]))


def apply_pairs(text, pairs):
    for a, b in pairs:
        text = text.replace(a, b)
    return text


# ================================================================ mạng

class FatalError(Exception):
    pass


class Stopped(Exception):
    pass


def http_request(url, body=None, headers=None, api_key=None, timeout=600):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    if body is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    if api_key:
        h["Authorization"] = "Bearer " + api_key
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def list_models(kind, base_url, api_key=None):
    base = base_url.rstrip("/")
    if kind == "ollama":
        data = http_request(base + "/api/tags", timeout=15)
        return [m["name"] for m in data.get("models", [])]
    data = http_request(base + "/models", api_key=api_key, timeout=20)
    ids = [m.get("id", "") for m in data.get("data", [])]
    return sorted(i[len("models/"):] if i.startswith("models/") else i for i in ids if i)


def _gcode(lang):
    return lang or "auto"


def gtx_translate(lines, sl, tl, endpoint=GTX_ENDPOINT):
    if "/translate_a/" in endpoint:
        out = []
        for l in lines:
            url = f"{endpoint}?client=gtx&sl={_gcode(sl)}&tl={_gcode(tl)}&dt=t"
            data = http_request(url, urllib.parse.urlencode({"q": l}).encode(),
                                {"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
            if not isinstance(data, list) or not isinstance(data[0], list):
                raise RuntimeError("GTX trả về dữ liệu không hợp lệ")
            out.append("".join(p[0] for p in data[0] if isinstance(p, list) and isinstance(p[0], str)))
        return out
    payload = [html.escape(l, quote=False) for l in lines]
    data = http_request(endpoint, [[payload, _gcode(sl), _gcode(tl)], "te_lib"],
                        {"Content-Type": "application/json+protobuf", "X-Goog-API-Key": GTX_PUBLIC_KEY}, timeout=60)
    if not isinstance(data, list) or not isinstance(data[0], list) or len(data[0]) != len(lines):
        raise RuntimeError("GTX trả về dữ liệu không hợp lệ")
    if not all(isinstance(t, str) for t in data[0]):
        raise RuntimeError("GTX thiếu bản dịch cho một số dòng")
    return [html.unescape(t) for t in data[0]]


def _ecode(lang):
    return {"auto": "", "zh-CN": "zh-Hans", "zh-TW": "zh-Hant"}.get(lang, lang)


def edge_translate(lines, sl, tl):
    url = (f"{EDGE_ENDPOINT}?from={urllib.parse.quote(_ecode(sl))}&to={urllib.parse.quote(_ecode(tl))}"
           "&isEnterpriseClient=false")
    data = http_request(url, list(lines), timeout=60)
    out = [d.get("translations", [{}])[0].get("text") for d in data] if isinstance(data, list) else []
    if len(out) != len(lines) or not all(isinstance(t, str) for t in out):
        if len(lines) == 1:
            raise RuntimeError("Edge trả về dữ liệu không hợp lệ")
        return [edge_translate([l], sl, tl)[0] for l in lines]
    return out


# ================================================================ engine AI (LLM)

class LLMEngine:
    def __init__(self, kind, base_url, api_key, model, batch_size, delay, note, src, tgt, stop, post):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = model.strip()
        self.batch_size = max(1, int(batch_size))
        self.delay = max(0.0, float(delay))
        self.note, self.src, self.tgt = note, src, tgt
        self.stop, self.post = stop, post
        self.cues = []

    def _sleep(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if self.stop.is_set():
                raise Stopped()
            time.sleep(0.2)

    def chat(self, messages):
        if self.kind == "ollama":
            url = self.base_url + "/api/chat"
            body = {"model": self.model, "messages": messages, "stream": False, "think": False,
                    "options": {"temperature": 0.3, "num_ctx": 8192}}
        else:
            url = self.base_url + "/chat/completions"
            body = {"model": self.model, "messages": messages, "temperature": 0.3}
        for attempt in range(6):
            if self.stop.is_set():
                raise Stopped()
            try:
                data = http_request(url, body, api_key=self.api_key)
                if self.kind == "ollama":
                    content = data.get("message", {}).get("content", "")
                else:
                    content = data["choices"][0]["message"].get("content") or ""
                return THINK_RE.sub("", content)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                if e.code in (429, 500, 502, 503, 504):
                    wait = min(60, 5 * 2 ** attempt)
                    self.post("log", f"Máy chủ báo {e.code} (giới hạn/quá tải), chờ {wait}s rồi thử lại...")
                    self._sleep(wait)
                    continue
                if e.code in (401, 403):
                    raise FatalError(f"API key không hợp lệ hoặc không có quyền (HTTP {e.code}).\n{detail}")
                if e.code == 404:
                    raise FatalError(f"Không tìm thấy model '{self.model}' hoặc sai API URL (HTTP 404).\n{detail}")
                raise FatalError(f"Lỗi HTTP {e.code}: {detail}")
            except (urllib.error.URLError, OSError) as e:
                refused = "10061" in str(e) or "refused" in str(e).lower()
                if refused and self.kind == "ollama":
                    raise FatalError("Ollama chưa chạy trên máy.\n1. Cài Ollama tại https://ollama.com/download\n"
                                     "2. Mở Ollama từ Start Menu (icon con lạc đà ở khay đồng hồ)\n"
                                     f"3. Mở CMD gõ:  ollama pull {self.model}\n4. Bấm Dịch lại.")
                if refused and ("localhost" in url or "127.0.0.1" in url):
                    raise FatalError("LM Studio chưa bật server. Tải model rồi bật 'Start Server' ở tab Developer.")
                if attempt >= 2:
                    raise FatalError(f"Không kết nối được {url}\n{e}")
                self.post("log", f"Lỗi kết nối ({e}), thử lại...")
                self._sleep(5)
            except (KeyError, IndexError, ValueError) as e:
                raise RuntimeError(f"Phản hồi không đúng định dạng: {e}")
        raise FatalError("Bị giới hạn tốc độ hoặc hết quota quá lâu. Đợi một lúc rồi bấm Dịch tiếp, "
                         "hoặc tăng thời gian nghỉ giữa các lần.")

    def run(self, cues):
        self.cues = cues
        todo = prepare_todo(cues)
        self.post("log", f"Dịch {len(todo)} dòng bằng {self.model} (mỗi lần {self.batch_size} dòng).")
        for s in range(0, len(todo), self.batch_size):
            if self.stop.is_set():
                raise Stopped()
            self._batch(todo[s:s + self.batch_size], 0)
            if self.delay and s + self.batch_size < len(todo):
                self._sleep(self.delay)

    def _batch(self, idxs, depth):
        res = {}
        try:
            messages = [{"role": "system", "content": system_prompt(self.src, self.tgt)},
                        {"role": "user", "content": build_user_prompt(self.cues, idxs, self.note, self.tgt)}]
            res = parse_numbered(self.chat(messages), expected_of(self.cues, idxs))
        except (Stopped, FatalError):
            raise
        except Exception as e:
            self.post("log", f"Lô dòng {idxs[0] + 1}-{idxs[-1] + 1} lỗi: {e}")
        missing = []
        for i in idxs:
            t = res.get(i + 1, "").strip()
            if t:
                self.cues[i].vi = from_wire(t)
                self.post("cue", i)
            else:
                missing.append(i)
        if not missing:
            return
        if depth >= 3:
            self.post("log", "Không dịch được dòng: " + ", ".join(str(i + 1) for i in missing) + " (giữ câu gốc).")
            return
        self.post("log", f"Thiếu {len(missing)} dòng, dịch lại phần thiếu...")
        if len(missing) == 1:
            self._batch(missing, depth + 1)
        else:
            half = (len(missing) + 1) // 2
            self._batch(missing[:half], depth + 1)
            self._batch(missing[half:], depth + 1)



# ================================================================ prompt dịch truyện

STYLE_PROMPTS = {
    "tu_nhien": ("natural, fluent modern Vietnamese literary prose, the way a skilled Vietnamese translator of novels "
                 "writes: smooth Vietnamese word order, rich vocabulary, vivid narration, never word-for-word"),
    "kiem_hiep": ("Vietnamese in the classic kiếm hiệp / tiên hiệp / cổ trang register used by Vietnamese translators of "
                  "Chinese novels: Hán Việt for names, titles, sects, martial arts, techniques, cultivation realms, "
                  "artifacts and places (e.g. 筑基 → Trúc Cơ, 宗门 → tông môn, 师尊 → sư tôn); pronouns such as ta, ngươi, "
                  "hắn, nàng, lão phu, tại hạ, các hạ, huynh, đệ, tỷ, muội, sư phụ, đồ nhi as fits; elegant, slightly archaic narration"),
    "ngon_tinh": ("Vietnamese in the ngôn tình (romance novel) style: emotional, soft, lyrical prose; modern settings use "
                  "anh/em, cô/cậu, tôi/cậu as fits; historical settings use ta/chàng/nàng, thiếp/chàng"),
    "sat_nghia": ("accurate Vietnamese that follows the original meaning and sentence structure closely while staying "
                  "grammatical and readable"),
}


def book_system_prompt(src, tgt, style, glossary):
    sname, tname = LANG_NAMES.get(src, "the source language"), LANG_NAMES.get(tgt, "Vietnamese")
    style_txt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["tu_nhien"]) if tgt == "vi" else f"natural, fluent literary {tname}"
    if src.startswith("zh") and tgt == "vi":
        names = ("Chinese names of people, places, sects and titles: use Sino-Vietnamese (Hán Việt) readings, "
                 "e.g. 李云龙 → Lý Vân Long, and keep them identical every time they appear.")
    else:
        names = f"Keep names of people and places as in the original (or their established {tname} forms), consistently."
    gl = ""
    if glossary:
        gl = ("\n\nGlossary — ALWAYS translate these terms exactly like this:\n" +
              "\n".join(f"{a} → {b}" for a, b in glossary))
    return f"""You are a professional literary translator of novels and books. Translate {sname} text into {style_txt}.

Rules:
1. Input paragraphs look like "[N] text". Output EXACTLY one line per input paragraph, starting with the same "[N] ". Never merge, split, skip or reorder paragraphs.
2. "<br>" marks a line break inside a paragraph: keep it.
3. Translate everything completely, including dialogue, poems, letters and sound effects. Do not summarize, shorten, censor or add anything.
4. {names}
5. Keep forms of address and pronouns consistent with the characters' relationships across the whole book.
6. Use Vietnamese punctuation and quotation marks (“ ”) naturally.
7. Output only the translated paragraphs. No explanations, no notes, no extra text.{gl}"""


def book_user_prompt(segs, idxs, note="", tgt="vi", context_n=3):
    parts = []
    if note.strip():
        parts.append("About this book / notes from the user: " + note.strip())
    first = idxs[0]
    ctx = [segs[j] for j in range(max(0, first - context_n), first) if segs[j].vi and segs[j].src.strip()]
    if ctx:
        parts.append("Previous paragraphs, for context only (do NOT output them):\n" +
                     "\n".join(f"SRC: {to_wire(c.src)}\nOUT: {to_wire(c.vi)}" for c in ctx))
    parts.append(f"Translate these {len(idxs)} paragraphs to {LANG_NAMES.get(tgt, 'Vietnamese')}:\n" +
                 "\n".join(f"[{i + 1}] {to_wire(segs[i].src)}" for i in idxs))
    return "\n\n".join(parts)


def sub_system_prompt(src, tgt, style, glossary):
    sname, tname = LANG_NAMES.get(src, "the source language"), LANG_NAMES.get(tgt, "Vietnamese")
    if tgt == "vi":
        tone = ("natural, fluent Vietnamese as people really speak in movies (văn nói tự nhiên, hợp ngữ cảnh)")
        pron = ("Choose Vietnamese pronouns (anh/em, tôi/cậu, mày/tao, con/bố, cháu/ông, ta/ngươi...) that fit the "
                "characters' relationship and the film's setting, and keep them consistent.")
        if style and style != "tu_nhien":
            tone += ". Register: " + STYLE_PROMPTS.get(style, "")
    else:
        tone = f"natural, fluent {tname} as people really speak in movies"
        pron = "Choose forms of address that fit the characters' relationship and keep them consistent."
    names = ("Chinese names of people, places, sects and martial-arts terms: use Sino-Vietnamese (Hán Việt) readings, "
             "e.g. 李云龙 -> Lý Vân Long, and keep them consistent.") if src.startswith("zh") and tgt == "vi" \
        else "Keep names of people and places as they are."
    gl = ("\n\nGlossary — ALWAYS translate these terms exactly like this:\n" +
          "\n".join(f"{a} → {b}" for a, b in glossary)) if glossary else ""
    return f"""You are a professional film subtitle translator. Translate {sname} subtitles into {tone}, not word-for-word.

Rules:
1. Input lines look like "[N] text". Output EXACTLY one line per input line, starting with the same "[N] ". Never merge, split, skip or reorder lines, even if a sentence continues on the next line.
2. "<br>" marks a line break inside one subtitle: keep it in the translation.
3. Keep formatting tags such as <i>, </i>, <b>, <font ...>, {{\\an8}} unchanged.
4. {pron}
5. Keep it short and easy to read on screen. {names} Translate idioms, jokes and slang by meaning.
6. Output only the translated lines. No explanations, no notes, no extra text.{gl}"""


def sub_user_prompt(segs, idxs, note="", tgt="vi", context_n=4):
    parts = []
    if note.strip():
        parts.append("Film info / notes from the user: " + note.strip())
    first = idxs[0]
    ctx = [segs[j] for j in range(max(0, first - context_n), first) if segs[j].vi and segs[j].src.strip()]
    if ctx:
        parts.append("Previous lines, for context only (do NOT output them):\n" +
                     "\n".join(f"SRC: {to_wire(c.src)}\nOUT: {to_wire(c.vi)}" for c in ctx))
    parts.append(f"Translate these {len(idxs)} subtitle lines to {LANG_NAMES.get(tgt, 'Vietnamese')}:\n" +
                 "\n".join(f"[{i + 1}] {to_wire(segs[i].src)}" for i in idxs))
    return "\n\n".join(parts)


# ================================================================ engine dịch truyện

class BookLLMEngine(LLMEngine):
    """Gửi nhiều đoạn văn một lần (theo số ký tự), giữ ngữ cảnh đoạn trước, tự gửi lại đoạn bị sót."""

    def __init__(self, kind, base_url, api_key, model, batch_size, delay, note, src, tgt, stop, post,
                 style="tu_nhien", glossary=(), max_chars=2500, sub=False):
        super().__init__(kind, base_url, api_key, model, batch_size, delay, note, src, tgt, stop, post)
        self.style, self.glossary, self.max_chars = style, list(glossary), max(300, int(max_chars or 2500))
        self.sub = sub
        self.unit = "dòng" if sub else "đoạn"

    def run(self, segs):
        self.cues = segs
        todo = prepare_todo(segs)
        batches, cur, n = [], [], 0
        for i in todo:
            L = len(segs[i].src)
            if cur and (n + L > self.max_chars or len(cur) >= self.batch_size):
                batches.append(cur)
                cur, n = [], 0
            cur.append(i)
            n += L
        if cur:
            batches.append(cur)
        self.post("log", f"Dịch {len(todo)} {self.unit} bằng {self.model} ({len(batches)} lượt gửi).")
        for k, b in enumerate(batches):
            if self.stop.is_set():
                raise Stopped()
            self._batch(b, 0)
            if self.delay and k < len(batches) - 1:
                self._sleep(self.delay)

    def _messages(self, idxs):
        text = "\n".join(self.cues[i].src for i in idxs)
        gl = [(a, b) for a, b in self.glossary if a in text][:200]
        if self.sub:
            return [{"role": "system", "content": sub_system_prompt(self.src, self.tgt, self.style, gl)},
                    {"role": "user", "content": sub_user_prompt(self.cues, idxs, self.note, self.tgt)}]
        return [{"role": "system", "content": book_system_prompt(self.src, self.tgt, self.style, gl)},
                {"role": "user", "content": book_user_prompt(self.cues, idxs, self.note, self.tgt)}]

    def _batch(self, idxs, depth):
        res = {}
        try:
            res = parse_numbered(self.chat(self._messages(idxs)), expected_of(self.cues, idxs))
        except (Stopped, FatalError):
            raise
        except Exception as e:
            self.post("log", f"Lô {self.unit} {idxs[0] + 1}-{idxs[-1] + 1} lỗi: {e}")
        missing = []
        for i in idxs:
            t = res.get(i + 1, "").strip()
            if t:
                self.cues[i].vi = from_wire(t)
                self.post("cue", i)
            else:
                missing.append(i)
        if not missing:
            return
        if depth >= 3:
            self.post("log", f"Không dịch được {self.unit}: " + ", ".join(str(i + 1) for i in missing[:30]) + " (giữ nguyên văn).")
            return
        self.post("log", f"Thiếu {len(missing)} {self.unit}, dịch lại phần thiếu...")
        if len(missing) == 1:
            self._batch(missing, depth + 1)
        else:
            half = (len(missing) + 1) // 2
            self._batch(missing[:half], depth + 1)
            self._batch(missing[half:], depth + 1)


class BookMTEngine:
    """Máy dịch (GTX / Edge / HachimiMT): cắt đoạn dài thành câu, gửi theo lô, ghép lại đúng đoạn."""

    def __init__(self, name, fn, items, chars, workers, delay, stop, post, loader=None, maxlen=1500, pre=None):
        self.name, self.fn, self.loader = name, fn, loader
        self.items, self.chars, self.workers, self.delay = items, chars, workers, delay
        self.stop, self.post, self.maxlen, self.pre = stop, post, maxlen, pre
        self.fails, self.abort, self.lock = 0, None, threading.Lock()
        self.unit = "đoạn"

    def run(self, segs):
        fn = self.fn or self.loader(self.post)
        todo = prepare_todo(segs)
        chunks, cur, n, chars = [], [], 0, 0
        for i in todo:
            lines = []
            for l in segs[i].src.split("\n"):
                if not l.strip():
                    continue
                pre, core, suf = TAG_WRAP_RE.match(l).groups()
                lines.append((pre, split_piece(core.strip(), self.maxlen) if core.strip() else [], suf))
            k = sum(len(x[1]) for x in lines)
            L = sum(len(p) for x in lines for p in x[1])
            if cur and (n + k > self.items or chars + L > self.chars):
                chunks.append(cur)
                cur, n, chars = [], 0, 0
            cur.append((i, lines))
            n += k
            chars += L
        if cur:
            chunks.append(cur)
        self.post("log", f"Dịch {len(todo)} {self.unit} bằng {self.name} ({len(chunks)} lượt gửi).")
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(lambda ch: self._do(fn, segs, ch), chunks))
        if self.abort:
            raise FatalError(self.abort)
        if self.stop.is_set():
            raise Stopped()

    def _wait(self, sec):
        end = time.time() + sec
        while time.time() < end and not self.stop.is_set():
            time.sleep(0.2)

    def _do(self, fn, segs, ch):
        if self.stop.is_set() or self.abort:
            return
        cores = [p for _, lines in ch for line in lines for p in line[1]]
        if self.pre:
            cores = [self.pre(p) for p in cores]
        outs, err = None, ""
        for attempt in range(5):
            if self.stop.is_set() or self.abort:
                return
            try:
                outs = fn(cores) if cores else []
                if len(outs) != len(cores):
                    raise RuntimeError("số câu trả về không khớp")
                break
            except urllib.error.HTTPError as e:
                outs, err = None, f"HTTP {e.code}"
                if e.code in (429, 500, 502, 503, 504):
                    wait = min(60, 3 * 2 ** attempt)
                    self.post("log", f"{self.name} báo {e.code} (giới hạn tốc độ), chờ {wait}s...")
                    self._wait(wait)
                    continue
                break
            except (FatalError, Stopped):
                raise
            except Exception as e:
                outs, err = None, str(e)
                if attempt >= 2:
                    break
                self._wait(2)
        if outs is None:
            self.post("log", f"Lượt gửi đoạn {ch[0][0] + 1}–{ch[-1][0] + 1} lỗi: {err}")
            with self.lock:
                self.fails += 1
                if self.fails >= 4 and not self.abort:
                    self.abort = (f"{self.name} liên tục lỗi ({err}). Có thể dịch vụ đang chặn IP của bạn hoặc mất mạng. "
                                  "Hãy thử dịch vụ khác (vd. Edge API Free) rồi bấm Dịch tiếp.")
            return
        with self.lock:
            self.fails = 0
        it = iter(outs)
        for i, lines in ch:
            segs[i].vi = "\n".join(pre + " ".join(next(it).strip() for _ in pieces) + suf for pre, pieces, suf in lines)
            self.post("cue", i)
        if self.delay:
            self._wait(self.delay)


# ---------------------------------------------------------------- HachimiMT chạy offline
# Model chạy trong một TIẾN TRÌNH RIÊNG (--hachimi-worker): nếu thư viện GPU/CUDA bị lỗi, treo
# hoặc crash thì app chính vẫn chạy bình thường, tự chuyển sang CPU và báo lỗi rõ ràng.

HACHIMI_MODELS = {
    "HachimiMT-60-QT": {"repo": "ngocdang83/HachimiMT-60-QT",
                        "desc": "Giọng cổ trang (ta, ngươi, hắn, nàng) — phim kiếm hiệp, tiên hiệp"},
    "HachimiMT-60-zh-vi": {"repo": "ngocdang83/HachimiMT-60-zh-vi",
                           "desc": "Xưng hô tự nhiên theo ngữ cảnh — phim hiện đại"},
    "HachimiMT-30-zh-vi": {"repo": "ngocdang83/HachimiMT-30-zh-vi",
                           "desc": "Bản nhỏ, nhanh hơn, chất lượng thấp hơn một chút"},
}
CT2_SUBDIR = "ct2-int8_float32"
SPECIAL_TOKENS = {"</s>", "<pad>", "<unk>", "<s>"}
LIBS_MSG = ("Chưa có thư viện chạy HachimiMT (ctranslate2, sentencepiece). "
            "Bấm 'Cài thư viện' trong phần HachimiMT, hoặc dùng bản .exe (đã kèm sẵn).")
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def model_dir(name):
    return os.path.join(MODELS_DIR, name)


def model_ready(name):
    d = model_dir(name)
    return all(os.path.isfile(os.path.join(d, f)) for f in ("model.bin", "source.spm", "target.spm")) and \
        os.path.isfile(os.path.join(d, ".complete"))


def dir_size(d):
    total = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def libs_status():
    """Chỉ kiểm tra có thư viện hay không, KHÔNG import (import ctranslate2 có thể treo nếu CUDA lỗi)."""
    import importlib.util
    importlib.invalidate_caches()
    return {m: bool(importlib.util.find_spec(m)) for m in ("ctranslate2", "sentencepiece")}


def setup_cuda_path():
    """Cho ctranslate2 tìm thấy các DLL CUDA mà app đã tải về."""
    if not os.path.isdir(CUDA_DIR):
        return
    if CUDA_DIR not in os.environ.get("PATH", ""):
        os.environ["PATH"] = CUDA_DIR + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(CUDA_DIR)
        except OSError:
            pass


_GPU_CACHE = {}


def nvidia_gpu():
    """Tên card NVIDIA và VRAM (MB), hoặc None. Kết quả được nhớ lại."""
    if "v" in _GPU_CACHE:
        return _GPU_CACHE["v"]
    res = None
    exe = shutil.which("nvidia-smi")
    if not exe and sys.platform == "win32":
        p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
        exe = p if os.path.exists(p) else None
    if exe:
        try:
            out = subprocess.run([exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW,
                                 stdin=subprocess.DEVNULL).stdout.strip().splitlines()
            if out:
                parts = [x.strip() for x in out[0].split(",")]
                try:
                    vram = int(float(parts[1]))
                except (ValueError, IndexError):
                    vram = 0
                res = {"name": parts[0], "vram": vram, "driver": parts[2] if len(parts) > 2 else ""}
        except Exception as e:
            log_file(f"nvidia-smi lỗi: {e}")
    _GPU_CACHE["v"] = res
    return res


def cuda_files_present():
    if not os.path.isdir(CUDA_DIR):
        return False
    names = {f.lower() for f in os.listdir(CUDA_DIR)}
    return any(n.startswith("cublas64_12") for n in names) and any(n.startswith("cudart64_12") for n in names)


# ---------- tiến trình phụ chạy model

def worker_cmd(port):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--hachimi-worker", str(port)]
    return [sys.executable, os.path.abspath(__file__), "--hachimi-worker", str(port)]


class HachimiWorker:
    def __init__(self):
        self.proc = self.sock = self.rf = None

    def start(self, timeout=120):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(1.0)
        port = srv.getsockname()[1]
        os.makedirs(DATA_DIR, exist_ok=True)
        logf = open(LOG_PATH, "ab")
        try:
            self.proc = subprocess.Popen(worker_cmd(port), stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
                                         creationflags=NO_WINDOW, cwd=APP_DIR)
        finally:
            logf.close()
        conn, end = None, time.time() + timeout
        try:
            while conn is None:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    if self.proc.poll() is not None:
                        raise RuntimeError(f"bộ dịch thoát ngay khi khởi động (mã {self.proc.returncode})")
                    if time.time() > end:
                        raise RuntimeError("bộ dịch không khởi động được (quá thời gian chờ)")
        except Exception:
            self.kill()
            raise
        finally:
            srv.close()
        self.sock = conn
        self.rf = conn.makefile("rb")

    def alive(self):
        return self.proc is not None and self.proc.poll() is None and self.sock is not None

    def call(self, msg, timeout):
        if not self.alive():
            raise RuntimeError("bộ dịch đã dừng")
        self.sock.settimeout(timeout)
        try:
            self.sock.sendall((json.dumps(msg) + "\n").encode("ascii"))
            line = self.rf.readline()
        except socket.timeout:
            self.kill()
            raise RuntimeError(f"bộ dịch không phản hồi sau {int(timeout)} giây (bị treo), đã tắt")
        except OSError as e:
            code = self.proc.poll() if self.proc else None
            self.kill()
            raise RuntimeError(f"bộ dịch bị tắt đột ngột (mã {code}): {e}")
        if not line:
            time.sleep(0.3)
            code = self.proc.poll() if self.proc else None
            self.kill()
            raise RuntimeError(f"bộ dịch bị tắt đột ngột (mã {code}) — thường do lỗi thư viện GPU/CUDA")
        r = json.loads(line.decode("ascii"))
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "lỗi không rõ")
        return r

    def kill(self):
        for x in (self.rf, self.sock):
            try:
                x and x.close()
            except Exception:
                pass
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.rf = self.sock = None


def worker_main(port):
    """Chạy trong tiến trình phụ: nạp model và dịch theo yêu cầu qua socket."""
    s = socket.create_connection(("127.0.0.1", port))
    rf = s.makefile("rb")

    def send(o):
        s.sendall((json.dumps(o) + "\n").encode("ascii"))

    setup_cuda_path()
    state = {}
    for raw in rf:
        try:
            m = json.loads(raw.decode("ascii"))
            cmd = m.get("cmd")
            if cmd == "probe":
                import ctranslate2
                import sentencepiece
                n = 0
                err = ""
                try:
                    n = ctranslate2.get_cuda_device_count()
                except Exception as e:
                    err = str(e)
                send({"ok": 1, "cuda": n, "err": err, "ct2": getattr(ctranslate2, "__version__", ""),
                      "sp": getattr(sentencepiece, "__version__", "")})
            elif cmd == "load":
                import ctranslate2
                import sentencepiece as spm
                d, dev = m["dir"], m["device"]
                sp_src = spm.SentencePieceProcessor(model_file=os.path.join(d, "source.spm"))
                sp_tgt = spm.SentencePieceProcessor(model_file=os.path.join(d, "target.spm"))
                vocab = set()
                for vf in ("shared_vocabulary.json", "vocab.json"):
                    p = os.path.join(d, vf)
                    if os.path.isfile(p):
                        with open(p, encoding="utf-8") as fh:
                            v = json.load(fh)
                        if v:
                            vocab = set(v if isinstance(v, list) else v.keys())
                            break
                if dev == "cuda":
                    tr = ctranslate2.Translator(d, device="cuda", compute_type="auto")
                else:
                    tr = ctranslate2.Translator(d, device="cpu", compute_type="auto",
                                                intra_threads=max(1, int(m.get("threads") or 4)))
                state.update(tr=tr, sp_src=sp_src, sp_tgt=sp_tgt, vocab=vocab)
                t0 = time.time()
                test = _worker_translate(state, ["你好"])  # chạy thử để chắc GPU thật sự dùng được
                send({"ok": 1, "device": dev, "test": test[0], "ms": int((time.time() - t0) * 1000)})
            elif cmd == "translate":
                send({"ok": 1, "out": _worker_translate(state, m["lines"])})
            elif cmd == "quit":
                break
            else:
                send({"ok": 0, "error": f"lệnh lạ: {cmd}"})
        except Exception as e:
            try:
                send({"ok": 0, "error": f"{type(e).__name__}: {e}"})
            except Exception:
                break
    s.close()


def _worker_translate(state, lines):
    if "tr" not in state:
        raise RuntimeError("chưa nạp model")
    vocab, sp_src, sp_tgt = state["vocab"], state["sp_src"], state["sp_tgt"]

    def encode(text):
        pieces = sp_src.encode(text, out_type=str)[:255]
        if vocab:
            pieces = [p if p in vocab else "<unk>" for p in pieces]
        return pieces + ["</s>"]

    res = state["tr"].translate_batch([encode(x) for x in lines], beam_size=4, max_decoding_length=256)
    out = []
    for r in res:
        toks = [t for t in r.hypotheses[0] if t not in SPECIAL_TOKENS]
        out.append(sp_tgt.decode(toks).replace("\u2581", " ").strip())
    return out


# ---------- kiểm tra GPU (chạy nền, có giới hạn thời gian)

_PROBE = {"state": "idle", "cuda": 0, "err": "", "at": 0}
_PROBE_LOCK = threading.Lock()


def probe_async(force=False):
    with _PROBE_LOCK:
        if _PROBE["state"] == "running" or (_PROBE["state"] == "done" and not force):
            return
        _PROBE.update(state="running", err="")

    def run():
        w = HachimiWorker()
        try:
            w.start(timeout=90)
            r = w.call({"cmd": "probe"}, timeout=60)
            _PROBE.update(state="done", cuda=int(r.get("cuda") or 0), err=r.get("err") or "",
                          ct2=r.get("ct2"), sp=r.get("sp"))
            log_file(f"Kiểm tra GPU: cuda={r.get('cuda')} ctranslate2={r.get('ct2')} sentencepiece={r.get('sp')} "
                     f"gpu={nvidia_gpu()} {r.get('err') or ''}")
        except Exception as e:
            _PROBE.update(state="done", cuda=0, err=str(e))
            log_file(f"Kiểm tra GPU lỗi: {e}")
        finally:
            try:
                w.call({"cmd": "quit"}, 5)
            except Exception:
                pass
            w.kill()
            _PROBE["at"] = time.time()
    threading.Thread(target=run, daemon=True).start()


class Tasks:
    """Các việc chạy nền: tải model, tải CUDA, cài thư viện."""

    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def start(self, key, label, fn):
        with self.lock:
            t = self.items.get(key)
            if t and t["state"] == "running":
                return False
            self.items[key] = {"key": key, "label": label, "state": "running", "done": 0, "total": 0,
                               "msg": "Đang bắt đầu...", "cancel": False}

        def run():
            t = self.items[key]
            try:
                msg = fn(t)
                t["state"], t["msg"] = "done", msg or "Xong"
            except Stopped:
                t["state"], t["msg"] = "cancelled", "Đã huỷ"
            except Exception as e:
                t["state"], t["msg"] = "error", str(e)
            if STATE is not None:
                STATE.log(f"{label}: {t['msg']}")
        threading.Thread(target=run, daemon=True).start()
        return True

    def cancel(self, key):
        t = self.items.get(key)
        if t:
            t["cancel"] = True

    def public(self):
        return {k: {x: v[x] for x in ("label", "state", "done", "total", "msg")} for k, v in self.items.items()}


TASKS = Tasks()


def download_file(url, dest, task, base_done=0):
    tmp = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while True:
            if task["cancel"]:
                raise Stopped()
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            base_done += len(chunk)
            task["done"] = base_done
    os.replace(tmp, dest)
    return base_done


def download_model_task(name):
    repo = HACHIMI_MODELS[name]["repo"]

    def fn(task):
        task["msg"] = "Đang lấy danh sách file..."
        files = http_request(f"{HF_BASE}/api/models/{repo}/tree/main/{CT2_SUBDIR}", timeout=30)
        files = [f for f in files if f.get("type") == "file"]
        if not any(f["path"].endswith("model.bin") for f in files):
            raise RuntimeError("Model này chưa có bản CTranslate2 trên Hugging Face.")
        task["total"] = sum(int(f.get("size") or 0) for f in files)
        dest = model_dir(name)
        os.makedirs(dest, exist_ok=True)
        try:
            os.remove(os.path.join(dest, ".complete"))
        except OSError:
            pass
        done = 0
        for f in files:
            fname = f["path"].split("/")[-1]
            task["msg"] = f"Đang tải {fname}"
            url = f"{HF_BASE}/{repo}/resolve/main/{urllib.parse.quote(f['path'])}"
            done = download_file(url, os.path.join(dest, fname), task, done)
        with open(os.path.join(dest, ".complete"), "w") as fh:
            fh.write(repo)
        release_worker()
    return fn


def pypi_win_wheel(package):
    data = http_request(f"{PYPI_BASE}/pypi/{package}/json", timeout=30)
    files = [u for u in data.get("urls", []) if u["filename"].endswith("win_amd64.whl")]
    if not files:
        for ver in sorted(data.get("releases", {}), key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split(".")],
                          reverse=True):
            files = [u for u in data["releases"][ver] if u["filename"].endswith("win_amd64.whl")]
            if files:
                break
    if not files:
        raise RuntimeError(f"Không tìm thấy {package} cho Windows trên PyPI.")
    return files[0]


def download_cuda_task():
    def fn(task):
        if not IS_WIN:
            raise RuntimeError("Tải CUDA tự động chỉ hỗ trợ Windows. Trên Linux hãy cài CUDA 12 theo hướng dẫn NVIDIA.")
        task["msg"] = "Đang tìm thư viện CUDA 12 trên PyPI..."
        wheels = [pypi_win_wheel("nvidia-cuda-runtime-cu12"), pypi_win_wheel("nvidia-cublas-cu12")]
        task["total"] = sum(int(w.get("size") or 0) for w in wheels)
        os.makedirs(CUDA_DIR, exist_ok=True)
        done = 0
        for w in wheels:
            task["msg"] = f"Đang tải {w['filename']}"
            whl = os.path.join(CUDA_DIR, w["filename"])
            done = download_file(w["url"], whl, task, done)
            task["msg"] = "Đang giải nén DLL..."
            with zipfile.ZipFile(whl) as z:
                for member in z.namelist():
                    if member.lower().endswith(".dll"):
                        with z.open(member) as src, open(os.path.join(CUDA_DIR, os.path.basename(member)), "wb") as out:
                            shutil.copyfileobj(src, out)
            os.remove(whl)
        release_worker()
        probe_async(force=True)
        return "Xong. Đang kiểm tra lại GPU..."
    return fn


def install_libs_task():
    def fn(task):
        if getattr(sys, "frozen", False):
            raise RuntimeError("Bản .exe đã kèm sẵn thư viện. Nếu vẫn báo thiếu, hãy build lại exe bằng Tao_file_EXE.bat.")
        task["msg"] = "Đang cài ctranslate2, sentencepiece, pypdf (1–3 phút)..."
        py = sys.executable
        if py.lower().endswith("pythonw.exe"):
            py = py[:-len("pythonw.exe")] + "python.exe"
        p = subprocess.run([py, "-m", "pip", "install", "-U", "ctranslate2", "sentencepiece", "pypdf"],
                           capture_output=True, text=True, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        if p.returncode != 0:
            raise RuntimeError("pip báo lỗi:\n" + (p.stderr or p.stdout)[-600:])
        probe_async(force=True)
        return "Đã cài xong."
    return fn


def hachimi_status():
    libs = libs_status()
    have_libs = all(libs.values())
    if have_libs:
        probe_async()
    models = []
    for name, m in HACHIMI_MODELS.items():
        ready = model_ready(name)
        models.append({"name": name, "repo": m["repo"], "desc": m["desc"], "ready": ready,
                       "size": dir_size(model_dir(name)) if ready else 0})
    w = _WORKER.get("info")
    return {"libs": libs, "haveLibs": have_libs, "frozen": bool(getattr(sys, "frozen", False)),
            "gpu": nvidia_gpu(), "cudaFiles": cuda_files_present(),
            "probe": {k: _PROBE.get(k) for k in ("state", "cuda", "err")},
            "cudaDevices": _PROBE.get("cuda", 0), "models": models, "worker": w,
            "modelsDir": MODELS_DIR, "dataDir": DATA_DIR, "logPath": LOG_PATH, "portable": PORTABLE,
            "tasks": TASKS.public(), "windows": IS_WIN}


_WORKER = {"w": None, "key": None, "dev": None, "info": None}
_WORKER_LOCK = threading.Lock()


def release_worker():
    with _WORKER_LOCK:
        if _WORKER["w"] is not None:
            _WORKER["w"].kill()
        _WORKER.update(w=None, key=None, dev=None, info=None)


def _start_worker(name, dev, post):
    w = HachimiWorker()
    label = "GPU" if dev == "cuda" else "CPU"
    post("log", f"Đang khởi động {name} trên {label}...")
    w.start(timeout=120)
    r = w.call({"cmd": "load", "dir": model_dir(name), "device": dev,
                "threads": max(1, (os.cpu_count() or 4) // 2)}, timeout=240)
    post("log", f"{name} chạy bằng {label} (thử dịch '你好' → '{r.get('test')}', {r.get('ms')} ms).")
    return w


def hachimi_loader(name, device_pref="auto"):
    def load(post):
        if not all(libs_status().values()):
            raise FatalError(LIBS_MSG)
        if not model_ready(name):
            raise FatalError(f"Chưa tải model {name} về máy. Bấm 'Tải về máy' ở phần HachimiMT rồi dịch lại.")
        key = (name, device_pref)
        with _WORKER_LOCK:
            if _WORKER["key"] != key or _WORKER["w"] is None or not _WORKER["w"].alive():
                if _WORKER["w"] is not None:
                    _WORKER["w"].kill()
                    _WORKER.update(w=None, info=None)
                devices = ["cpu"]
                if device_pref == "gpu" or (device_pref == "auto" and (nvidia_gpu() or _PROBE.get("cuda"))):
                    devices = ["cuda", "cpu"]
                w, dev, errs = None, None, []
                for dv in devices:
                    try:
                        w, dev = _start_worker(name, dv, post), dv
                        break
                    except Exception as e:
                        errs.append(f"{'GPU' if dv == 'cuda' else 'CPU'}: {e}")
                        post("log", f"Không chạy được trên {'GPU' if dv == 'cuda' else 'CPU'}: {e}")
                        log_file(f"Khởi động {name} trên {dv} lỗi: {e}")
                if w is None:
                    raise FatalError("Không chạy được HachimiMT.\n" + "\n".join(errs) +
                                     f"\nChi tiết trong file log: {LOG_PATH}")
                _WORKER.update(w=w, key=key, dev=dev, info={"model": name, "device": "GPU" if dev == "cuda" else "CPU"})

        def fn(lines):
            with _WORKER_LOCK:
                w = _WORKER["w"]
                if w is None or not w.alive():
                    raise RuntimeError("bộ dịch đã dừng")
                try:
                    return w.call({"cmd": "translate", "lines": lines}, timeout=90 + 4 * len(lines))["out"]
                except RuntimeError as e:
                    if w.alive():
                        raise
                    # tiến trình dịch chết (thường do GPU) -> chuyển sang CPU rồi dịch lại lô này
                    log_file(f"Bộ dịch {_WORKER['dev']} dừng: {e}")
                    if _WORKER["dev"] != "cuda":
                        _WORKER.update(w=None, key=None, info=None)
                        raise
                    post("log", f"GPU gặp lỗi ({e}), chuyển sang CPU...")
                    w2 = _start_worker(name, "cpu", post)
                    _WORKER.update(w=w2, dev="cpu", info={"model": name, "device": "CPU"})
                    return w2.call({"cmd": "translate", "lines": lines}, timeout=90 + 6 * len(lines))["out"]
        return fn
    return load



# ================================================================ Nhận giọng nói -> phụ đề SRT (Whisper)
# Whisper chạy offline bằng faster-whisper (CTranslate2, dùng chung thư viện GPU với HachimiMT) trong một
# TIẾN TRÌNH RIÊNG (--stt-worker), hoặc gọi Groq / OpenAI Whisper qua mạng.

MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m2ts", ".mts", ".mpg", ".mpeg",
              ".m4v", ".3gp", ".vob", ".rmvb", ".rm", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus",
              ".wma", ".amr", ".ac3", ".dts", ".mka", ".aiff", ".aif"}
STT_DIR = os.path.join(DATA_DIR, "stt")
STT_MODELS = {
    "large-v3-turbo": {"repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "size": 1620,
                       "desc": "Khuyên dùng: nhanh, chính xác. GPU từ 4 GB chạy rất nhanh"},
    "large-v3": {"repo": "Systran/faster-whisper-large-v3", "size": 3090,
                 "desc": "Chính xác nhất, nhất là tiếng Trung, Nhật, Hàn. Chậm hơn, nên có GPU từ 6 GB"},
    "medium": {"repo": "Systran/faster-whisper-medium", "size": 1530,
               "desc": "Cân bằng, chạy được bằng CPU mạnh"},
    "small": {"repo": "Systran/faster-whisper-small", "size": 484,
              "desc": "Nhẹ, cho máy không có GPU. Kém chính xác hơn"},
}
STT_FILES = ("config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.json",
             "vocabulary.txt")
STT_LANGS = {"auto": "Tự nhận", "zh": "Tiếng Trung", "ja": "Tiếng Nhật", "ko": "Tiếng Hàn", "en": "Tiếng Anh",
             "vi": "Tiếng Việt"}
# mã ngôn ngữ Whisper -> mã dùng khi dịch
STT_TO_APP = {"zh": "zh-CN", "yue": "zh-CN", "ja": "ja", "ko": "ko", "en": "en", "vi": "vi"}
CJK_LANGS = ("zh", "yue", "ja")
# câu Whisper hay "bịa" ra ở đoạn im lặng (học từ phụ đề trên mạng)
HALLU_RE = re.compile(
    r"(字幕(由|提供|制作|製作|by)|请不吝点赞|請不吝點贊|订阅.*(转发|打赏)|明镜与点点|Amara\.org|"
    r"ご視聴ありがとうございま|チャンネル登録|시청해\s*주셔서\s*감사|구독.*좋아요|MBC\s*뉴스|"
    r"thanks?\s+for\s+watching|please\s+subscribe|subtitles?\s+by|transcribed\s+by|"
    r"hãy\s+subscribe|đăng\s+ký\s+kênh|ghiền\s+mì\s+gõ|cảm\s+ơn\s+các\s+bạn\s+đã\s+(theo\s+dõi|xem))",
    re.I)
STT_SIZES = {"short": (32, 6.0), "medium": (40, 7.0), "long": (48, 8.0)}  # độ rộng 1 dòng (chữ Trung/Nhật/Hàn tính 2), giây
SENT_END = tuple("。！？!?…") + (".", "」", "』")
SOFT_END = tuple("，,、；;：:")


def stt_model_dir(name):
    return os.path.join(MODELS_DIR, "whisper-" + name)


def stt_model_ready(name):
    d = stt_model_dir(name)
    return os.path.isfile(os.path.join(d, "model.bin")) and os.path.isfile(os.path.join(d, ".complete"))


def stt_libs_status():
    import importlib.util
    importlib.invalidate_caches()
    return {m: bool(importlib.util.find_spec(m)) for m in ("faster_whisper", "av", "onnxruntime", "ctranslate2")}


def cudnn_present():
    if not os.path.isdir(CUDA_DIR):
        return False
    names = {f.lower() for f in os.listdir(CUDA_DIR)}
    return any(n.startswith("cudnn64_9") for n in names) and any(n.startswith("cudnn_ops") for n in names)


def stt_gpu_ready():
    return bool(nvidia_gpu()) and cuda_files_present() and cudnn_present()


def download_stt_model_task(name):
    repo = STT_MODELS[name]["repo"]

    def fn(task):
        task["msg"] = "Đang lấy danh sách file..."
        files = http_request(f"{HF_BASE}/api/models/{repo}/tree/main", timeout=30)
        files = [f for f in files if f.get("type") == "file" and f["path"] in STT_FILES]
        if not any(f["path"] == "model.bin" for f in files):
            raise RuntimeError("Không tìm thấy model trên Hugging Face.")
        task["total"] = sum(int(f.get("size") or 0) for f in files)
        dest = stt_model_dir(name)
        os.makedirs(dest, exist_ok=True)
        try:
            os.remove(os.path.join(dest, ".complete"))
        except OSError:
            pass
        done = 0
        for f in sorted(files, key=lambda f: f["path"] == "model.bin"):
            task["msg"] = f"Đang tải {f['path']}"
            p = os.path.join(dest, f["path"])
            size = int(f.get("size") or 0)
            if size and os.path.isfile(p) and os.path.getsize(p) == size:   # tải tiếp, bỏ qua file đã đủ
                done += size
                task["done"] = done
                continue
            done = download_file(f"{HF_BASE}/{repo}/resolve/main/{f['path']}", p, task, done)
        with open(os.path.join(dest, ".complete"), "w") as fh:
            fh.write(repo)
    return fn


def download_stt_gpu_task():
    """Thư viện GPU cho Whisper: CUDA 12 (cuBLAS, runtime) như HachimiMT + cuDNN 9."""
    def fn(task):
        if not IS_WIN:
            raise RuntimeError("Tải tự động chỉ hỗ trợ Windows. Trên Linux hãy cài CUDA 12 và cuDNN 9.")
        task["msg"] = "Đang tìm thư viện GPU trên PyPI..."
        pkgs = ([] if cuda_files_present() else ["nvidia-cuda-runtime-cu12", "nvidia-cublas-cu12"]) + \
            ([] if cudnn_present() else ["nvidia-cudnn-cu12"])
        if not pkgs:
            return "Đã có đủ thư viện GPU."
        wheels = [pypi_win_wheel(p) for p in pkgs]
        task["total"] = sum(int(w.get("size") or 0) for w in wheels)
        os.makedirs(CUDA_DIR, exist_ok=True)
        done = 0
        for w in wheels:
            task["msg"] = f"Đang tải {w['filename']}"
            whl = os.path.join(CUDA_DIR, w["filename"])
            done = download_file(w["url"], whl, task, done)
            task["msg"] = "Đang giải nén DLL..."
            with zipfile.ZipFile(whl) as z:
                for member in z.namelist():
                    if member.lower().endswith(".dll"):
                        with z.open(member) as src, open(os.path.join(CUDA_DIR, os.path.basename(member)), "wb") as out:
                            shutil.copyfileobj(src, out)
            os.remove(whl)
        release_worker()
        probe_async(force=True)
        return "Xong. Lần nhận giọng sau sẽ chạy bằng GPU."
    return fn


def install_stt_libs_task():
    def fn(task):
        if getattr(sys, "frozen", False):
            raise RuntimeError("Bản .exe phải kèm sẵn thư viện. Hãy build lại exe bằng Tao_file_EXE.bat.")
        task["msg"] = "Đang cài faster-whisper (1–3 phút)..."
        py = sys.executable
        if py.lower().endswith("pythonw.exe"):
            py = py[:-len("pythonw.exe")] + "python.exe"
        p = subprocess.run([py, "-m", "pip", "install", "-U", "faster-whisper", "opencc-python-reimplemented"],
                           capture_output=True, text=True, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        if p.returncode != 0:
            raise RuntimeError("pip báo lỗi:\n" + (p.stderr or p.stdout)[-600:])
        return "Đã cài xong."
    return fn


def stt_info():
    libs = stt_libs_status()
    have = all(libs.values())
    if libs.get("ctranslate2"):
        probe_async()
    models = []
    for name, m in STT_MODELS.items():
        ready = stt_model_ready(name)
        models.append({"name": name, "desc": m["desc"], "approx": m["size"], "ready": ready,
                       "size": dir_size(stt_model_dir(name)) if ready else 0})
    return {"libs": libs, "haveLibs": have, "frozen": bool(getattr(sys, "frozen", False)), "gpu": nvidia_gpu(),
            "cudaFiles": cuda_files_present(), "cudnn": cudnn_present(), "cudaDevices": _PROBE.get("cuda", 0),
            "probe": {k: _PROBE.get(k) for k in ("state", "cuda", "err")}, "models": models,
            "tasks": TASKS.public(), "windows": IS_WIN, "dataDir": DATA_DIR, "modelsDir": MODELS_DIR}


# ---------- đọc âm thanh từ video / file nhạc (16 kHz, mono)

def load_audio16k(path, progress=None):
    """Tự giải mã bằng PyAV (không dùng decode_audio của faster-whisper vì nó lỗi với PyAV mới)."""
    import av
    import numpy as np
    try:
        container = av.open(path, mode="r", metadata_errors="ignore")
    except TypeError:
        container = av.open(path, mode="r")
    bad = tuple(x for x in (getattr(getattr(av, "error", None), "InvalidDataError", None),
                            getattr(av, "InvalidDataError", None)) if x) or (ValueError,)
    parts, last = [], time.time()
    with container:
        if not container.streams.audio:
            raise ValueError("File không có âm thanh")
        st = container.streams.audio[0]
        dur = float(container.duration) / 1e6 if container.duration else 0.0
        rs = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = container.decode(st)
        while True:
            try:
                fr = next(frames)
            except StopIteration:
                break
            except bad:
                continue
            t = fr.time
            fr.pts = None
            for o in rs.resample(fr) or []:
                parts.append(o.to_ndarray().reshape(-1).copy())
            if progress and dur and t and time.time() - last > 1:
                last = time.time()
                progress(min(1.0, t / dur))
        try:
            for o in rs.resample(None) or []:
                parts.append(o.to_ndarray().reshape(-1).copy())
        except Exception:
            pass
    if not parts:
        raise ValueError("Không đọc được âm thanh trong file")
    return np.concatenate(parts).astype(np.float32) / 32768.0


# ---------- tiến trình phụ chạy Whisper

def stt_worker_cmd(port):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--stt-worker", str(port)]
    return [sys.executable, os.path.abspath(__file__), "--stt-worker", str(port)]


def _fake_transcribe(path, opts, send):
    """Chỉ dùng khi kiểm thử (DICHVIET_STT_FAKE=1): giải mã âm thanh thật, sinh câu giả có mốc thời gian từng chữ."""
    audio = load_audio16k(path)
    dur = len(audio) / 16000
    lang = opts.get("language") or "zh"
    send({"ev": "lang", "lang": lang, "prob": 0.99, "duration": dur, "device": opts["device"]})
    t, k = 0.5, 0
    words_zh = list("我们今天去哪里吃饭呢，你说吧。") + list("好的，我知道了！")
    while t < dur - 1:
        k += 1
        ws, tt = [], t
        src = words_zh if lang in CJK_LANGS else [" Hello", " there,", " this", " is", " line", f" {k}."]
        for w in src:
            ws.append([round(tt, 2), round(tt + 0.25, 2), w])
            tt += 0.27
        send({"ev": "seg", "s": ws[0][0], "e": ws[-1][1], "t": "".join(w[2] for w in ws), "w": ws})
        if k == 3:
            send({"ev": "seg", "s": tt + 0.5, "e": tt + 2, "t": "字幕由Amara.org社区提供", "w": []})
        t = tt + 1.2
        time.sleep(float(os.environ.get("DICHVIET_STT_FAKE_DELAY", "0")))
    send({"ev": "done"})


def stt_worker_main(port):
    s = socket.create_connection(("127.0.0.1", port))
    rf = s.makefile("rb")

    def send(o):
        s.sendall((json.dumps(o, ensure_ascii=True) + "\n").encode("ascii"))

    try:
        opts = json.loads(rf.readline().decode("ascii"))
        setup_cuda_path()
        if os.environ.get("DICHVIET_STT_FAKE"):
            return _fake_transcribe(opts["path"], opts, send)
        from faster_whisper import WhisperModel
        dev = opts["device"]
        send({"ev": "stage", "msg": f"Đang nạp model {opts['model']} trên {'GPU' if dev == 'cuda' else 'CPU'}..."})
        types = (["int8_float16", "int8", "float32"] if (opts.get("vram") or 0) < 7000 else
                 ["float16", "int8_float16", "int8", "float32"]) if dev == "cuda" else ["int8", "float32"]
        model, err = None, None
        for ct in types:
            try:
                model = WhisperModel(opts["dir"], device=dev, compute_type=ct,
                                     cpu_threads=int(opts.get("threads") or 4), num_workers=1)
                send({"ev": "stage", "msg": f"Đã nạp model ({ct})."})
                break
            except Exception as e:      # kiểu số không hỗ trợ trên card này -> thử kiểu khác
                err = e
        if model is None:
            raise err
        lang = opts.get("language") or None
        prompt = None
        if lang in ("zh", None) and opts.get("zhPrompt"):
            prompt = "以下是普通话的句子，使用简体中文和标点符号。" if opts.get("zhScript") != "t" else "以下是普通話的句子，使用標點符號。"
        send({"ev": "stage", "msg": "Đang đọc âm thanh..."})
        audio = load_audio16k(opts["path"], lambda f: send({"ev": "stage", "msg": f"Đang đọc âm thanh... {int(f * 100)}%"}))
        segments, info = model.transcribe(
            audio, language=lang, task="transcribe", beam_size=int(opts.get("beam") or 5),
            word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 250, "threshold": 0.45},
            condition_on_previous_text=False, initial_prompt=prompt,
            hotwords=(opts.get("hotwords") or None), hallucination_silence_threshold=2.0,
            no_speech_threshold=0.6, compression_ratio_threshold=2.4)
        send({"ev": "lang", "lang": info.language, "prob": round(info.language_probability, 3),
              "duration": info.duration, "device": dev})
        for sg in segments:
            send({"ev": "seg", "s": sg.start, "e": sg.end, "t": sg.text,
                  "w": [[w.start, w.end, w.word] for w in (sg.words or [])]})
        send({"ev": "done"})
    except Exception as e:
        try:
            send({"ev": "error", "msg": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    finally:
        try:
            s.close()
        except Exception:
            pass


# ---------- chia câu thành dòng phụ đề đúng thời gian

def _is_cjk_text(t):
    return len(CJK_RE.findall(t)) + len(KANA_RE.findall(t)) > len(t) * 0.3


WIDE_RE = re.compile(r"[\u1100-\u11ff\u2e80-\ua4cf\uac00-\ud7af\uf900-\ufaff\uff00-\uff60\u3000-\u303f]")


def text_width(t):
    return len(t) + len(WIDE_RE.findall(t))


def _wrap2(text, per_line, cjk):
    """Bẻ một dòng dài thành 2 dòng cân đối."""
    if text_width(text) <= per_line:
        return text
    mid = len(text) // 2
    if cjk:
        best = None
        for i, ch in enumerate(text[:-1]):
            if ch in "，、；：,;: " and abs(i + 1 - mid) <= len(text) // 3:
                if best is None or abs(i + 1 - mid) < abs(best - mid):
                    best = i + 1
        cut = best or mid
        return text[:cut].rstrip() + "\n" + text[cut:].lstrip()
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return text
    half = text_width(text) / 2
    cut = min(spaces, key=lambda i: abs(text_width(text[:i]) - half))
    return text[:cut] + "\n" + text[cut + 1:]


def _clean_text(t):
    t = re.sub(r"\s+", " ", t or "").strip()
    t = re.sub(r"\s+([,.!?;:，。！？；：、])", r"\1", t)
    return t


def make_cues(segments, lang=None, size="medium", zh_conv=None):
    """segments: [{"s","e","t","w":[[s,e,word],...]}] -> danh sách cue [start, end, text]."""
    per_line, max_dur = STT_SIZES.get(size, STT_SIZES["medium"])
    raw = []
    for sg in segments:
        words = [w for w in (sg.get("w") or []) if (w[2] or "").strip()]
        text_all = _clean_text(sg.get("t", ""))
        cjk = (lang in CJK_LANGS) if lang else _is_cjk_text(text_all)
        limit = per_line * 2
        if not words:
            if text_all:
                raw.append([float(sg["s"]), float(sg["e"]), text_all, cjk])
            continue
        cur = []

        def flush(ws):
            if ws:
                t = _clean_text("".join(w[2] for w in ws))
                if t:
                    raw.append([float(ws[0][0]), float(ws[-1][1]), t, cjk])

        for w in words:
            if cur:
                cur_text = "".join(x[2] for x in cur)
                gap = w[0] - cur[-1][1]
                too_long = text_width(_clean_text(cur_text + w[2])) > limit
                too_slow = w[1] - cur[0][0] > max_dur
                if gap > 0.8:
                    flush(cur)
                    cur = []
                elif too_long or too_slow:
                    # lùi về dấu phẩy gần nhất (nếu không quá sớm) để ngắt câu tự nhiên
                    k = max((i for i, x in enumerate(cur[:-1]) if x[2].strip().endswith(SOFT_END + SENT_END)
                             and i + 1 >= max(2, len(cur) / 4)), default=None)
                    if k is not None:
                        flush(cur[:k + 1])
                        cur = cur[k + 1:]
                    else:
                        flush(cur)
                        cur = []
            cur.append(w)
            t = "".join(x[2] for x in cur).strip()
            if t.endswith(SENT_END) and cur[-1][1] - cur[0][0] >= 1.2 and text_width(t) >= limit * 0.3:
                flush(cur)
                cur = []
        flush(cur)
    # lọc câu ảo giác và câu lặp
    cues = []
    for s, e, t, cjk in raw:
        if zh_conv and cjk:
            t = zh_conv(t)
        if HALLU_RE.search(t) or not re.search(r"\w", t):
            continue
        if len(cues) >= 2 and cues[-1][2] == t and cues[-2][2] == t and s - cues[-1][1] < 0.6:
            continue        # Whisper bị lặp (một câu lặp liền nhau nhiều lần) -> bỏ phần lặp
        cues.append([s, max(e, s + 0.3), t, cjk])
    # chỉnh thời gian: tối thiểu dễ đọc, không chồng lên dòng sau
    for i, c in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else c[1] + 5
        want = c[0] + max(1.0, min(text_width(c[2]) * 0.04, 2.0))
        end = max(c[1] + 0.15, want)
        c[1] = round(max(c[0] + 0.3, min(end, nxt - 0.04)), 3)
    return [[round(c[0], 3), c[1], _wrap2(c[2], per_line, c[3])] for c in cues]


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def cues_to_srt(cues):
    return "".join(f"{i}\n{srt_time(s)} --> {srt_time(e)}\n{t}\n\n" for i, (s, e, t) in enumerate(cues, 1))


def zh_converter(script):
    if script not in ("s", "t"):
        return None
    target = "zh-cn" if script == "s" else "zh-tw"
    try:
        import opencc       # gói opencc-python-reimplemented (thuần Python)
        cc = opencc.OpenCC("t2s" if script == "s" else "s2t")
        return cc.convert
    except Exception:
        pass
    try:
        import zhconv
        return lambda t: zhconv.convert(t, target)
    except ImportError:
        return None


# ---------- Whisper qua mạng (Groq / OpenAI)

def _multipart(fields, file_field, filename, data, ctype):
    bnd = "----dichviet" + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields:
        out.write(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    out.write(f'--{bnd}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
              f'Content-Type: {ctype}\r\n\r\n'.encode("utf-8"))
    out.write(data)
    out.write(f"\r\n--{bnd}--\r\n".encode("ascii"))
    return out.getvalue(), f"multipart/form-data; boundary={bnd}"


def _wav_bytes(samples):
    import wave
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return b.getvalue()


def plan_chunks(audio, max_len=480.0):
    """Cắt âm thanh dài thành đoạn <= max_len giây, cắt ở chỗ im lặng (VAD)."""
    sr = 16000
    dur = len(audio) / sr
    try:
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        sp = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=500, speech_pad_ms=250,
                                                     max_speech_duration_s=max_len - 30))
        sp = [(x["start"] / sr, x["end"] / sr) for x in sp]
    except Exception as e:
        log_file(f"VAD lỗi, cắt đều: {e}")
        sp = None
    if not sp:      # VAD không thấy lời (nhạc nền to...) -> vẫn gửi cả file, cắt đều
        n = max(1, int(dur // max_len) + 1)
        return [(i * dur / n, (i + 1) * dur / n) for i in range(n)]
    chunks, cs, ce = [], None, None
    for a, b in sp:
        if cs is None:
            cs, ce = a, b
        elif b - cs > max_len:
            chunks.append((cs, ce))
            cs, ce = a, b
        else:
            ce = b
    if cs is not None:
        chunks.append((cs, ce))
    return [(max(0.0, a - 0.2), min(dur, b + 0.2)) for a, b in chunks]


def api_transcribe(path, opts, send, stop):
    """Gửi từng đoạn âm thanh lên Groq / OpenAI Whisper, nhận mốc thời gian từng chữ."""
    send({"ev": "stage", "msg": "Đang đọc âm thanh..."})
    audio = load_audio16k(path, lambda f: send({"ev": "stage", "msg": f"Đang đọc âm thanh... {int(f * 100)}%"}))
    dur = len(audio) / 16000
    send({"ev": "lang", "lang": opts.get("language") or "", "prob": 0, "duration": dur, "device": "API"})
    chunks = plan_chunks(audio)
    url = (opts.get("url") or "").rstrip("/") + "/audio/transcriptions"
    send({"ev": "stage", "msg": f"Gửi {len(chunks)} đoạn âm thanh lên {opts.get('name')}..."})
    langs = {}
    for ci, (a, b) in enumerate(chunks):
        if stop.is_set():
            raise Stopped()
        wav = _wav_bytes(audio[int(a * 16000):int(b * 16000)])
        fields = [("model", opts["model"]), ("response_format", "verbose_json"),
                  ("timestamp_granularities[]", "segment"), ("timestamp_granularities[]", "word"),
                  ("temperature", "0")]
        if opts.get("language"):
            fields.append(("language", opts["language"]))
        if opts.get("hotwords"):
            fields.append(("prompt", opts["hotwords"][:800]))
        body, ctype = _multipart(fields, "file", f"chunk{ci}.wav", wav, "audio/wav")
        res = None
        for attempt in range(6):
            if stop.is_set():
                raise Stopped()
            try:
                req = urllib.request.Request(url, data=body, method="POST", headers={
                    "Content-Type": ctype, "Authorization": "Bearer " + opts.get("key", ""), "User-Agent": UA})
                with urllib.request.urlopen(req, timeout=600) as r:
                    res = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")[:300]
                if e.code in (401, 403):
                    raise FatalError(f"API key không đúng hoặc không có quyền ({e.code}): {msg}")
                if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                    wait = int(e.headers.get("retry-after") or 0) or min(90, 10 * 2 ** attempt)
                    send({"ev": "stage", "msg": f"Dịch vụ báo {e.code} (giới hạn), chờ {wait} giây..."})
                    end = time.time() + wait
                    while time.time() < end and not stop.is_set():
                        time.sleep(0.3)
                    continue
                raise RuntimeError(f"HTTP {e.code}: {msg}")
            except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
                if attempt >= 3:
                    raise RuntimeError(f"Lỗi mạng: {e}")
                time.sleep(3)
        if res is None:
            raise RuntimeError("Không nhận được kết quả")
        if res.get("language"):
            langs[res["language"]] = langs.get(res["language"], 0) + 1
        words = [[float(w["start"]) + a, float(w["end"]) + a, w.get("word", "")] for w in (res.get("words") or [])]
        segs = res.get("segments") or []
        if not segs and res.get("text"):
            segs = [{"start": 0, "end": b - a, "text": res["text"]}]
        cjk = _is_cjk_text(res.get("text") or "")
        for sg in segs:
            s0, e0 = float(sg["start"]) + a, float(sg["end"]) + a
            ws = [w for w in words if w[0] >= s0 - 0.05 and w[1] <= e0 + 0.3]
            for w in ws:
                w[2] = w[2] if (cjk or w[2].startswith(" ")) else " " + w[2]   # API trả chữ không có dấu cách đầu
            send({"ev": "seg", "s": s0, "e": e0, "t": sg.get("text", ""), "w": ws})
        send({"ev": "pos", "p": b})
    if langs:
        lg = max(langs, key=langs.get)
        send({"ev": "lang", "lang": WHISPER_NAME_TO_CODE.get(lg.lower(), lg), "prob": 0, "duration": dur,
              "device": "API"})
    send({"ev": "done"})


WHISPER_NAME_TO_CODE = {"chinese": "zh", "japanese": "ja", "korean": "ko", "english": "en", "vietnamese": "vi",
                        "cantonese": "yue", "thai": "th", "french": "fr", "german": "de", "spanish": "es",
                        "russian": "ru", "indonesian": "id"}


# ---------- hàng đợi nhận giọng

class SttJob:
    def __init__(self, jid, name, path, uploaded=False):
        self.id, self.name, self.path, self.uploaded = jid, name, path, uploaded
        self.status = "ready"       # ready | queued | running | done | error | stopped
        self.error = self.srt = self.lang = self.device = self.stage = ""
        self.duration = self.pos = 0.0
        self.segments = []
        self.cues = []
        self.t0 = None
        self.added = time.time()
        self.lib_id = ""

    def summary(self):
        pct = int(min(100, self.pos * 100 / self.duration)) if self.duration else 0
        eta = None
        if self.status == "running" and self.t0 and self.pos > 5 and self.duration:
            el = time.time() - self.t0
            if el > 5:
                eta = int(el / self.pos * (self.duration - self.pos))
        return {"id": self.id, "name": self.name, "path": "" if self.uploaded else self.path, "status": self.status,
                "error": self.error, "srt": self.srt, "lang": self.lang, "device": self.device, "stage": self.stage,
                "duration": self.duration, "pos": self.pos, "pct": 100 if self.status == "done" else pct,
                "eta": eta, "cues": len(self.cues), "libId": self.lib_id}

    def to_json(self):
        return {"id": self.id, "name": self.name, "path": self.path, "uploaded": self.uploaded,
                "status": self.status if self.status in ("done", "error") else ("stopped" if self.status in
                                                                                ("running", "queued") else self.status),
                "error": self.error, "srt": self.srt, "lang": self.lang, "duration": self.duration,
                "added": self.added, "libId": self.lib_id}


class SttState:
    def __init__(self):
        self.jobs, self.order = {}, []
        self.lock = threading.RLock()
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.running = None
        self.proc_worker = None
        self._load()
        threading.Thread(target=self._loop, daemon=True).start()

    def busy(self):
        return self.running is not None or not self.q.empty()

    def _load(self):
        try:
            with open(os.path.join(STT_DIR, "jobs.json"), encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            return
        for it in items:
            j = SttJob(it["id"], it["name"], it["path"], it.get("uploaded", False))
            j.status, j.error, j.srt, j.lang = it.get("status", "ready"), it.get("error", ""), it.get("srt", ""), it.get("lang", "")
            j.duration, j.added, j.lib_id = it.get("duration", 0), it.get("added", 0), it.get("libId", "")
            if j.status == "done":
                j.pos = j.duration
                try:
                    with open(os.path.join(STT_DIR, j.id + ".json"), encoding="utf-8") as f:
                        j.cues = json.load(f)
                except Exception:
                    pass
            self.jobs[j.id] = j
            self.order.append(j.id)

    def save(self):
        try:
            os.makedirs(STT_DIR, exist_ok=True)
            with self.lock:
                data = [self.jobs[i].to_json() for i in self.order if i in self.jobs]
            tmp = os.path.join(STT_DIR, "jobs.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, os.path.join(STT_DIR, "jobs.json"))
        except Exception as e:
            log_file(f"Không lưu được danh sách nhận giọng: {e}")

    def add(self, path, name=None, uploaded=False):
        if not os.path.isfile(path):
            raise ValueError(f"Không thấy file: {path}")
        if os.path.splitext(path)[1].lower() not in MEDIA_EXTS:
            raise ValueError("Không phải file âm thanh hoặc video")
        j = SttJob(uuid.uuid4().hex[:10], name or os.path.basename(path), path, uploaded)
        with self.lock:
            self.jobs[j.id] = j
            self.order.append(j.id)
        self.save()
        STATE.log(f"Đã thêm để nhận giọng: {j.name}")
        return j

    def remove(self, jid):
        with self.lock:
            if self.running == jid:
                return False
            j = self.jobs.pop(jid, None)
            if jid in self.order:
                self.order.remove(jid)
        if j is not None:
            if j.uploaded:
                shutil.rmtree(os.path.dirname(j.path), ignore_errors=True)
            try:
                os.remove(os.path.join(STT_DIR, jid + ".json"))
            except OSError:
                pass
        self.save()
        return True

    def enqueue(self, ids, cfg):
        with self.lock:
            if self.running is None and self.q.empty():
                self.stop.clear()
            n = 0
            for jid in ids:
                j = self.jobs.get(jid)
                if not j or j.status in ("queued", "running"):
                    continue
                if j.uploaded and not os.path.isfile(j.path):
                    j.status, j.error = "error", "File tải lên đã bị xoá, hãy thêm lại."
                    continue
                j.status, j.error = "queued", ""
                self.q.put((jid, dict(cfg)))
                n += 1
        self.save()
        return n

    def request_stop(self):
        self.stop.set()
        with self.lock:
            while True:
                try:
                    jid, _ = self.q.get_nowait()
                except queue.Empty:
                    break
                if jid in self.jobs:
                    self.jobs[jid].status = "stopped"
            w = self.proc_worker
        if w is not None:
            w.kill()
        self.save()

    def _loop(self):
        while True:
            jid, cfg = self.q.get()
            j = self.jobs.get(jid)
            if j is None:
                continue
            if self.stop.is_set():
                j.status = "stopped"
                continue
            with self.lock:
                self.running = jid
                j.status, j.t0, j.pos, j.segments, j.cues, j.stage = "running", time.time(), 0.0, [], [], ""
            try:
                self._run(j, cfg)
            except Stopped:
                j.status, j.stage = "stopped", ""
                STATE.log(f"[{j.name}] Đã dừng nhận giọng.")
            except Exception as e:
                if self.stop.is_set():      # bấm Dừng làm đứt kết nối với Whisper -> không phải lỗi
                    j.status, j.stage = "stopped", ""
                    STATE.log(f"[{j.name}] Đã dừng nhận giọng.")
                    continue
                j.status, j.error, j.stage = "error", str(e), ""
                STATE.log(f"[{j.name}] LỖI nhận giọng: {e}")
                log_file(f"STT lỗi {j.name}: {e!r}")
            finally:
                with self.lock:
                    self.running = None
                    if self.q.empty():
                        self.stop.clear()
                self.save()

    # ---------- chạy một file
    def _event(self, j, ev, lang_opt, size, conv):
        k = ev.get("ev")
        if k == "stage":
            j.stage = ev.get("msg", "")
            STATE.log(f"[{j.name}] {j.stage}")
        elif k == "lang":
            if ev.get("duration"):
                j.duration = float(ev["duration"])
            if ev.get("lang"):
                j.lang = ev["lang"]
            if ev.get("device"):
                j.device = {"cuda": "GPU", "cpu": "CPU"}.get(ev["device"], ev["device"])
            if ev.get("prob"):
                STATE.log(f"[{j.name}] Ngôn ngữ: {STT_LANGS.get(j.lang, j.lang)} ({int(ev['prob'] * 100)}%), "
                          f"dài {int(j.duration // 60)} phút {int(j.duration % 60)} giây, chạy bằng {j.device}.")
            j.stage = "Đang nhận giọng..."
        elif k == "seg":
            with self.lock:
                j.segments.append(ev)
                j.pos = max(j.pos, float(ev.get("e") or 0))
                if len(j.segments) % 5 == 0 or len(j.segments) < 5:
                    j.cues = make_cues(j.segments, j.lang or lang_opt, size, conv)
        elif k == "pos":
            j.pos = max(j.pos, float(ev.get("p") or 0))

    def _run(self, j, cfg):
        engine = cfg.get("engine") or "local"
        lang_opt = cfg.get("language") or "auto"
        lang_opt = None if lang_opt == "auto" else lang_opt
        size = cfg.get("size") or "medium"
        conv = zh_converter(cfg.get("zhScript") or "s")
        hot = (cfg.get("hotwords") or "").strip()
        STATE.log(f"[{j.name}] Bắt đầu tạo phụ đề ({'Whisper trên máy' if engine == 'local' else engine}).")
        t0 = time.time()
        if engine == "local":
            self._run_local(j, cfg, lang_opt, size, conv, hot)
        else:
            sc = cfg.get("api") or {}
            if not sc.get("key"):
                raise FatalError("Chưa nhập API key.")
            opts = {"url": sc.get("url"), "key": sc.get("key"), "model": sc.get("model"),
                    "name": "Groq" if engine == "groq" else "OpenAI", "language": lang_opt, "hotwords": hot}
            api_transcribe(j.path, opts, lambda ev: self._event(j, ev, lang_opt, size, conv), self.stop)
        with self.lock:
            j.cues = make_cues(j.segments, j.lang or lang_opt, size, conv)
            j.pos = j.duration
        if not j.cues:
            raise RuntimeError("Không nghe thấy lời thoại nào trong file.")
        self._finish(j, cfg, time.time() - t0)

    def _run_local(self, j, cfg, lang_opt, size, conv, hot):
        info = stt_libs_status()
        if not all(info.values()):
            raise FatalError("Thiếu thư viện Whisper (faster-whisper). " +
                             ("Hãy build lại exe bằng Tao_file_EXE.bat." if getattr(sys, "frozen", False)
                              else "Bấm 'Cài thư viện' trong tab Giọng nói."))
        name = cfg.get("model") or "large-v3-turbo"
        if name not in STT_MODELS:
            name = "large-v3-turbo"
        if not stt_model_ready(name) and not os.environ.get("DICHVIET_STT_FAKE"):
            raise FatalError(f"Chưa tải model Whisper {name}. Bấm 'Tải về máy' trong tab Giọng nói rồi thử lại.")
        pref = cfg.get("device") or "auto"
        g = nvidia_gpu()
        devices = ["cpu"]
        if pref == "gpu" or (pref == "auto" and g):
            if stt_gpu_ready() or pref == "gpu":
                devices = ["cuda", "cpu"]
            else:
                STATE.log(f"[{j.name}] Có card NVIDIA nhưng chưa có thư viện GPU (cuDNN), chạy bằng CPU. "
                          "Bấm 'Tải hỗ trợ GPU' trong tab Giọng nói để chạy nhanh hơn nhiều lần.")
        last_err = ""
        for dev in devices:
            opts = {"path": j.path, "dir": stt_model_dir(name), "model": name, "device": dev,
                    "language": lang_opt, "hotwords": hot, "zhPrompt": True, "zhScript": cfg.get("zhScript") or "s",
                    "vram": (g or {}).get("vram", 0), "beam": int(cfg.get("beam") or 5),
                    "threads": max(4, (os.cpu_count() or 4) // 2)}
            with self.lock:
                j.segments, j.cues, j.pos = [], [], 0.0
            ok, err, got = self._worker_run(j, opts, lang_opt, size, conv)
            if ok:
                return
            last_err = err
            if self.stop.is_set():
                raise Stopped()
            if dev == "cuda" and not got:
                STATE.log(f"[{j.name}] GPU lỗi ({err}), chuyển sang CPU...")
                log_file(f"STT GPU lỗi: {err}")
                continue
            break
        raise RuntimeError(last_err or "Whisper dừng bất thường")

    def _worker_run(self, j, opts, lang_opt, size, conv):
        """Trả (thành công, lỗi, đã nhận được câu nào chưa)."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(1.0)
        port = srv.getsockname()[1]
        os.makedirs(DATA_DIR, exist_ok=True)
        logf = open(LOG_PATH, "ab")
        w = HachimiWorker()
        try:
            w.proc = subprocess.Popen(stt_worker_cmd(port), stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
                                      creationflags=NO_WINDOW, cwd=APP_DIR)
        finally:
            logf.close()
        self.proc_worker = w
        try:
            conn, end = None, time.time() + 120
            while conn is None:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    if self.stop.is_set():
                        raise Stopped()
                    if w.proc.poll() is not None:
                        return False, f"Whisper thoát ngay khi khởi động (mã {w.proc.returncode})", False
                    if time.time() > end:
                        return False, "Whisper không khởi động được (quá thời gian chờ)", False
            w.sock, w.rf = conn, conn.makefile("rb")
            conn.sendall((json.dumps(opts, ensure_ascii=True) + "\n").encode("ascii"))
            conn.settimeout(1800)       # model lớn trên CPU có thể mất lâu cho một câu
            got = False
            while True:
                line = w.rf.readline()
                if not line:
                    if self.stop.is_set():
                        raise Stopped()
                    time.sleep(0.3)
                    code = w.proc.poll()
                    return False, f"Whisper bị tắt đột ngột (mã {code}), thường do thiếu hoặc lỗi thư viện GPU", got
                ev = json.loads(line.decode("ascii"))
                if ev.get("ev") == "done":
                    return True, "", got
                if ev.get("ev") == "error":
                    return False, ev.get("msg", "lỗi"), got
                if ev.get("ev") == "seg":
                    got = True
                self._event(j, ev, lang_opt, size, conv)
        except socket.timeout:
            return False, "Whisper không phản hồi (bị treo)", False
        except OSError as e:
            if self.stop.is_set():
                raise Stopped()
            return False, f"Mất kết nối với Whisper: {e}", False
        finally:
            srv.close()
            w.kill()
            self.proc_worker = None

    def _finish(self, j, cfg, took):
        data = cues_to_srt(j.cues)
        base = os.path.splitext(j.name)[0]
        tag = j.lang or "auto"
        fname = f"{base}.{tag}.srt"
        folder = None
        if not j.uploaded and cfg.get("saveNext", True):
            folder = os.path.dirname(j.path)
        out_dir = folder or cfg.get("outDir") or default_out_dir()
        try:
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, fname)
            with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(data)
        except OSError:
            out_dir = cfg.get("outDir") or default_out_dir()   # thư mục video không ghi được -> lưu thư mục xuất
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, fname)
            with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(data)
        j.srt = path
        with open(os.path.join(STT_DIR, j.id + ".json"), "w", encoding="utf-8") as f:
            json.dump(j.cues, f, ensure_ascii=False)
        j.status, j.stage = "done", ""
        mins = int(took // 60)
        STATE.log(f"[{j.name}] Xong: {len(j.cues)} dòng phụ đề sau {mins} phút {int(took % 60)} giây. Đã lưu: {path}")
        if j.uploaded:      # file tải lên chỉ là bản sao tạm, xoá cho đỡ tốn ổ
            shutil.rmtree(os.path.dirname(j.path), ignore_errors=True)
        tr = cfg.get("translate")
        if tr:
            try:
                self.to_library(j, tr, out_dir)
            except Exception as e:
                STATE.log(f"[{j.name}] Không tự dịch được: {e}")

    def to_library(self, j, tcfg, out_dir=None):
        """Thêm SRT vừa tạo vào Tài liệu và dịch (sang tiếng Việt theo dịch vụ đang chọn)."""
        if not j.cues:
            raise ValueError("Chưa có phụ đề")
        if j.lib_id and j.lib_id in STATE.jobs:
            job = STATE.jobs[j.lib_id]
        else:
            name = f"{os.path.splitext(j.name)[0]}.{j.lang or 'auto'}.srt"
            job = STATE.add(name, cues_to_srt(j.cues).encode("utf-8"))
            if out_dir:
                job.out_dir = out_dir
                job.save_meta()
            j.lib_id = job.id
            self.save()
        tgt = tcfg.get("target") or "vi"
        src = STT_TO_APP.get(j.lang, "auto")
        if src == tgt:
            STATE.log(f"[{j.name}] Phụ đề đã là {LANG_VI.get(tgt, tgt)}, không cần dịch.")
            return job
        cfg = dict(tcfg, source=src if src != "auto" else (tcfg.get("source") or "auto"))
        if cfg.get("service") == "hachimi" and not src.startswith("zh"):
            cfg["service"] = "gtx"
            STATE.log(f"[{j.name}] HachimiMT chỉ dịch tiếng Trung, phụ đề này dịch bằng GTX API.")
        STATE.enqueue([job.id], cfg)
        return job


STT = None


def pick_files_dialog():
    """Hộp chọn file của Windows (trả về đường dẫn thật, không phải chép file)."""
    if not IS_WIN:
        raise RuntimeError("no-dialog")
    exts = ";".join("*" + e for e in sorted(MEDIA_EXTS))
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$f=New-Object System.Windows.Forms.Form;$f.TopMost=$true;$f.ShowInTaskbar=$false;"
          "$d=New-Object System.Windows.Forms.OpenFileDialog;$d.Multiselect=$true;"
          "$d.Title='Chọn video hoặc âm thanh để tạo phụ đề';"
          f"$d.Filter='Video, âm thanh|{exts}|Tất cả|*.*';"
          "if($d.ShowDialog($f) -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;$d.FileNames -join \"`n\"}")
    p = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True,
                       creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, timeout=3600)
    out = p.stdout.decode("utf-8", "replace").strip()
    return [x.strip() for x in out.splitlines() if x.strip()]


# ================================================================ cập nhật từ GitHub Releases

UPDATE_EXIT = threading.Event()
_UPD = {"at": 0, "info": None}


def _vt(v):
    n = [int(x) for x in re.findall(r"\d+", v or "")[:3]]
    return tuple(n + [0] * (3 - len(n)))


def install_mode():
    """onefile: 1 file exe | portable / onedir: thư mục có _internal | source: chạy bằng Python."""
    if not getattr(sys, "frozen", False):
        return "source"
    if os.path.isdir(os.path.join(APP_DIR, "_internal")):
        return "portable" if PORTABLE else "onedir"
    return "onefile"


def check_update(force=False):
    if not force and _UPD["info"] and time.time() - _UPD["at"] < 600:
        return _UPD["info"]
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "DichViet-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            info = {"current": APP_VERSION, "latest": "", "newer": False, "mode": install_mode(),
                    "url": f"https://github.com/{GITHUB_REPO}/releases", "msg": "Chưa có bản phát hành nào."}
            _UPD.update(at=time.time(), info=info)
            return info
        raise RuntimeError(f"GitHub báo lỗi {e.code}")
    tag = rel.get("tag_name") or ""
    mode = install_mode()
    want = ".exe" if mode == "onefile" else "portable.zip"
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(want)), None)
    info = {"current": APP_VERSION, "latest": tag.lstrip("vV"), "newer": _vt(tag) > _vt(APP_VERSION),
            "notes": (rel.get("body") or "")[:3000], "url": rel.get("html_url"), "mode": mode,
            "published": rel.get("published_at"),
            "asset": {"name": asset["name"], "url": asset["browser_download_url"], "size": asset.get("size", 0),
                      "digest": asset.get("digest") or ""} if asset else None}
    _UPD.update(at=time.time(), info=info)
    return info


def _restart_cmd(exe):
    return [exe, "--after-update"]


def _clean_env():
    """Tiến trình mới phải độc lập với bản cũ (bản 1 file exe của PyInstaller giải nén ra thư mục tạm riêng)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def update_task():
    def fn(task):
        info = check_update(force=True)
        if not info["newer"]:
            return "Đang dùng bản mới nhất."
        mode, a = info["mode"], info.get("asset")
        if mode == "source":
            raise RuntimeError("Bạn đang chạy bằng Python. Hãy tải mã nguồn mới trên GitHub.")
        if not IS_WIN:
            raise RuntimeError("Tự cập nhật chỉ hỗ trợ Windows.")
        if not a:
            raise RuntimeError("Bản phát hành chưa có file cho kiểu cài đặt này.")
        if (STATE and (STATE.running or not STATE.q.empty())) or (STT and STT.busy()):
            raise RuntimeError("Đang dịch hoặc đang tạo phụ đề. Hãy đợi xong hoặc bấm Dừng rồi cập nhật.")
        upd = os.path.join(DATA_DIR, "update")
        shutil.rmtree(upd, ignore_errors=True)
        os.makedirs(upd, exist_ok=True)
        task["total"] = int(a.get("size") or 0)
        task["msg"] = f"Đang tải bản {info['latest']}"
        dest = os.path.join(upd, a["name"])
        download_file(a["url"], dest, task)
        if a.get("digest", "").startswith("sha256:"):
            import hashlib
            h = hashlib.sha256()
            with open(dest, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() != a["digest"].split(":", 1)[1]:
                raise RuntimeError("File tải về bị lỗi (sai mã kiểm tra). Hãy thử lại.")
        task["msg"] = "Đang cài bản mới..."
        if mode == "onefile":
            with open(dest, "rb") as f:
                if f.read(2) != b"MZ":
                    raise RuntimeError("File tải về không phải file exe.")
            cur = sys.executable
            old = cur + ".old"
            try:
                os.remove(old)
            except OSError:
                pass
            os.replace(cur, old)            # Windows cho đổi tên exe đang chạy
            try:
                shutil.move(dest, cur)
            except Exception:
                os.replace(old, cur)
                raise
            subprocess.Popen(_restart_cmd(cur), creationflags=0x00000008 | 0x00000200, close_fds=True, env=_clean_env())
        else:
            with zipfile.ZipFile(dest) as z:
                z.extractall(os.path.join(upd, "new"))
            os.remove(dest)
            root = None
            for r, _, files in os.walk(os.path.join(upd, "new")):
                if os.path.isdir(os.path.join(r, "_internal")) and any(f.lower().endswith(".exe") for f in files):
                    root = r
                    break
            if not root:
                raise RuntimeError("File cập nhật không đúng cấu trúc.")
            new_exe = next(f for f in os.listdir(root) if f.lower().endswith(".exe"))
            cur_exe = os.path.basename(sys.executable)
            lines = ["@echo off", "chcp 65001 >nul",
                     ":wait", f'tasklist /FI "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul && '
                              f'(ping -n 2 127.0.0.1 >nul & goto wait)',
                     # _internal thay hẳn (xoá file cũ thừa), còn lại chép đè; KHÔNG đụng thư mục data và portable.ini
                     f'robocopy "{os.path.join(root, "_internal")}" "{os.path.join(APP_DIR, "_internal")}" /MIR '
                     f'/R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul',
                     f'robocopy "{root}" "{APP_DIR}" /E /XD data _internal /XF portable.ini /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul']
            if cur_exe.lower() != new_exe.lower():
                lines.append(f'del /f /q "{os.path.join(APP_DIR, cur_exe)}" >nul 2>nul')
            lines += [f'start "" "{os.path.join(APP_DIR, new_exe)}" --after-update',
                      f'rmdir /s /q "{os.path.join(upd, "new")}"', '(goto) 2>nul & del "%~f0"']
            bat = os.path.join(DATA_DIR, "cap_nhat.cmd")
            with open(bat, "w", encoding="utf-8") as f:
                f.write("\r\n".join(lines) + "\r\n")
            subprocess.Popen(["cmd", "/c", bat], creationflags=NO_WINDOW | 0x00000200, close_fds=True,
                             cwd=DATA_DIR, env=_clean_env())
        log_file(f"Cập nhật {APP_VERSION} -> {info['latest']} ({mode}), khởi động lại...")
        threading.Timer(1.5, UPDATE_EXIT.set).start()
        return f"Đã cài bản {info['latest']}. Đang khởi động lại..."
    return fn


def cleanup_old_update():
    try:
        if getattr(sys, "frozen", False) and os.path.isfile(sys.executable + ".old"):
            os.remove(sys.executable + ".old")
    except OSError:
        pass
    shutil.rmtree(os.path.join(DATA_DIR, "update"), ignore_errors=True)



# ================================================================ tủ sách / hàng đợi

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def default_out_dir():
    d = os.path.join(HOME, "Downloads")
    return d if os.path.isdir(d) else HOME


DEFAULT_SETTINGS = {"style": "tu_nhien", "note": "", "glossary": "", "fixes": ""}


class Job:
    """Một cuốn sách trong tủ sách. Tiến độ được lưu xuống đĩa để mở lại dịch tiếp."""

    def __init__(self, jid, name, book, settings=None):
        self.id = jid
        self.name = name
        self.book = book
        self.lang = detect_lang(book.segs)
        self.status = "ready"     # ready | queued | running | done | partial | stopped | error
        self.error = ""
        self.events = []          # chỉ số các đoạn vừa đổi
        self.saved = ""
        self.settings = dict(DEFAULT_SETTINGS, **(settings or {}))
        self.dirty = False
        self.added = time.time()
        self.run_t0 = None        # lúc bắt đầu lượt dịch hiện tại
        self.run_n0 = 0           # số đoạn đã xong lúc bắt đầu
        self.out_dir = ""         # lưu riêng (vd. phụ đề tạo từ video: lưu cạnh video)

    @property
    def dir(self):
        return os.path.join(BOOKS_DIR, self.id)

    def counts(self, a=0, b=None):
        segs = self.book.segs[a:b]
        total = sum(1 for c in segs if c.src.strip())
        done = sum(1 for c in segs if c.src.strip() and c.vi is not None)
        return done, total

    def summary(self):
        done, total = self.counts()
        rate = eta = None
        if self.status == "running" and self.run_t0:
            el = time.time() - self.run_t0
            if el > 8 and done > self.run_n0:
                rate = (done - self.run_n0) / el * 60
                eta = int((total - done) / (rate / 60)) if rate else None
        return {"id": self.id, "name": self.name, "mode": self.book.mode, "kind": self.book.kind, "lang": self.lang,
                "ext": getattr(self.book, "src_ext", self.book.ext),
                "status": self.status, "done": done, "total": total, "error": self.error, "saved": self.saved,
                "chapters": len(self.book.chapters), "title": self.book.title, "rate": rate, "eta": eta,
                "chars": sum(len(s.src) for s in self.book.segs) if not hasattr(self, "_chars") else self._chars}

    def chapter_progress(self):
        segs = self.book.segs
        out = []
        for ch in self.book.chapters:
            t = d = 0
            for s in segs[ch["start"]:ch["end"]]:
                if s.src.strip():
                    t += 1
                    if s.vi is not None:
                        d += 1
            out.append([d, t])
        return out

    def out_name(self, ext):
        base = os.path.splitext(self.name)[0]
        base = re.sub(r"\.(zh|yue|ja|ko|en|vi|auto)$", "", base)    # phim.zh.srt -> phim.vi.srt
        return base + ".vi" + ext

    def save_progress(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            data = {"n": len(self.book.segs), "vi": [s.vi for s in self.book.segs], "saved": self.saved,
                    "status": self.status if self.status in ("done", "partial", "stopped", "error") else "stopped"}
            tmp = os.path.join(self.dir, "progress.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(self.dir, "progress.json"))
            self.dirty = False
        except Exception as e:
            log_file(f"Không lưu được tiến độ {self.name}: {e}")

    def save_meta(self):
        try:
            os.makedirs(self.dir, exist_ok=True)
            with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump({"name": self.name, "added": self.added, "settings": self.settings, "outDir": self.out_dir},
                          f, ensure_ascii=False, indent=1)
        except Exception as e:
            log_file(f"Không lưu được thông tin {self.name}: {e}")


class State:
    def __init__(self):
        self.jobs = {}
        self.order = []
        self.logs = []
        self.lock = threading.RLock()
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.running = None
        self.last_ping = time.time()
        self._load_library()
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._saver, daemon=True).start()

    def log(self, msg, job=None):
        with self.lock:
            prefix = f"[{job.name}] " if job is not None else ""
            self.logs.append(time.strftime("%H:%M:%S  ") + prefix + msg)
        log_file(prefix + msg)

    # ---------- tủ sách
    def _load_library(self):
        if not os.path.isdir(BOOKS_DIR):
            return
        items = []
        for jid in os.listdir(BOOKS_DIR):
            d = os.path.join(BOOKS_DIR, jid)
            try:
                with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
                    meta = json.load(f)
                src = [x for x in os.listdir(d) if x.startswith("source")]
                if not src:
                    continue
                with open(os.path.join(d, src[0]), "rb") as f:
                    data = f.read()
                book = parse_book(data, meta["name"], cache_dir=d)
                job = Job(jid, meta["name"], book, meta.get("settings"))
                job._chars = sum(len(s.src) for s in book.segs)
                job.added = meta.get("added", 0)
                job.out_dir = meta.get("outDir") or ""
                p = os.path.join(d, "progress.json")
                if os.path.isfile(p):
                    with open(p, encoding="utf-8") as f:
                        prog = json.load(f)
                    if prog.get("n") == len(book.segs):
                        for s, v in zip(book.segs, prog.get("vi", [])):
                            s.vi = v
                        job.saved = prog.get("saved", "")
                        done, total = job.counts()
                        job.status = "done" if total and done == total else ("partial" if done else "ready")
                items.append(job)
            except Exception as e:
                log_file(f"Không mở được sách trong {d}: {e}")
        for job in sorted(items, key=lambda j: j.added):
            self.jobs[job.id] = job
            self.order.append(job.id)
        if items:
            self.log(f"Đã mở tủ sách: {len(items)} cuốn.")

    def add(self, name, data):
        jid = uuid.uuid4().hex[:10]
        jdir = os.path.join(BOOKS_DIR, jid)
        try:
            book = parse_book(data, name, cache_dir=jdir)
            if not book.segs:
                raise ValueError("File không có chữ để dịch")
        except Exception:
            shutil.rmtree(jdir, ignore_errors=True)
            raise
        job = Job(jid, name, book)
        job._chars = sum(len(s.src) for s in book.segs)
        os.makedirs(job.dir, exist_ok=True)
        with open(os.path.join(job.dir, "source" + os.path.splitext(name)[1].lower()), "wb") as f:
            f.write(data)
        job.save_meta()
        with self.lock:
            self.jobs[job.id] = job
            self.order.append(job.id)
        if book.kind == "sub":
            self.log(f"Đã thêm phụ đề: {len(book.segs):,} dòng, {book.mode.upper()}, {LANG_VI.get(job.lang, job.lang)}.".replace(",", "."), job)
        else:
            self.log(f"Đã thêm sách: {len(book.chapters)} chương, {len(book.segs):,} đoạn, ~{job._chars:,} ký tự, "
                     f"{book.mode.upper()}, {LANG_VI.get(job.lang, job.lang)}.".replace(",", "."), job)
        return job

    def remove(self, jid):
        with self.lock:
            if self.running == jid:
                return False
            job = self.jobs.pop(jid, None)
            if jid in self.order:
                self.order.remove(jid)
        if job is not None:
            shutil.rmtree(job.dir, ignore_errors=True)
        return True

    def _saver(self):
        while True:
            time.sleep(3)
            for job in list(self.jobs.values()):
                if job.dirty:
                    job.save_progress()

    # ---------- dịch
    def enqueue(self, ids, cfg, restart=False, chapter=None):
        with self.lock:
            if self.running is None and self.q.empty():
                self.stop.clear()
            n = 0
            for jid in ids:
                job = self.jobs.get(jid)
                if not job or job.status in ("queued", "running"):
                    continue
                job.status, job.error = "queued", ""
                self.q.put((jid, dict(cfg, _restart=restart, _chapter=chapter)))
                n += 1
            return n

    def request_stop(self):
        self.stop.set()
        with self.lock:
            while True:
                try:
                    jid, _ = self.q.get_nowait()
                except queue.Empty:
                    break
                if jid in self.jobs:
                    self.jobs[jid].status = "stopped"

    def _worker(self):
        while True:
            jid, cfg = self.q.get()
            job = self.jobs.get(jid)
            if job is None:
                continue
            if self.stop.is_set():
                job.status = "stopped"
                continue
            with self.lock:
                self.running = jid
                job.status = "running"
            try:
                self._run(job, cfg)
            finally:
                job.save_progress()
                with self.lock:
                    self.running = None
                    if self.q.empty():
                        self.stop.clear()

    def _run(self, job, cfg):
        book = job.book
        ch = cfg.get("_chapter")
        if ch is not None and 0 <= int(ch) < len(book.chapters):
            c = book.chapters[int(ch)]
            a, b = c["start"], c["end"]
            scope = f"chương “{c['title']}”"
        else:
            a, b, scope = 0, len(book.segs), "cả cuốn"
        segs = book.segs[a:b]
        fixes = parse_pairs(job.settings.get("fixes", ""))

        def post(kind, data):
            if kind == "log":
                self.log(data, job)
            elif kind == "cue":
                s = segs[data]
                if fixes and s.vi:
                    s.vi = "\n".join(x.strip() for x in apply_pairs(s.vi, fixes).split("\n"))
                job.events.append(data + a)
                job.dirty = True

        src = cfg.get("source") or "auto"
        tgt = cfg.get("target") or "vi"
        try:
            eng = make_engine(cfg, job, src, tgt, self.stop, post)
            if cfg.get("_restart"):
                with self.lock:
                    for s in segs:
                        s.vi = None
                    job.events.append(-1)
            self.log(f"Bắt đầu dịch {scope}.", job)
            t0 = time.time()
            job.run_t0, job.run_n0 = t0, job.counts()[0]
            eng.run(segs)
            rem = remaining_count(book.segs)
            job.status = "done" if rem == 0 else "partial"
            took = int(time.time() - t0)
            if remaining_count(segs):
                self.log(f"Còn {remaining_count(segs)} {eng.unit} chưa dịch. Bấm 'Dịch tiếp' để dịch phần còn thiếu.", job)
            else:
                self.log(f"Xong {scope} sau {took // 60} phút {took % 60} giây.", job)
        except Stopped:
            job.status = "stopped"
            self.log("Đã dừng. Lần sau bấm 'Dịch tiếp' để dịch tiếp từ chỗ dừng.", job)
        except FatalError as e:
            job.status, job.error = "error", str(e)
            self.log("LỖI: " + str(e), job)
        except Exception as e:
            job.status, job.error = "error", f"Lỗi: {e}"
            self.log(f"LỖI: {e}", job)
            log_file(f"Lỗi khi dịch {job.name}: {e!r}")
        done, _ = job.counts()
        if cfg.get("autosave", True) and done and job.status in ("done", "partial", "stopped"):
            try:
                job.saved = save_export(job, job.out_dir or cfg.get("outDir"), cfg.get("format", "orig"),
                                        cfg.get("content", "vi"), tgt)
                self.log(f"Đã lưu: {job.saved}", job)
            except Exception as e:
                self.log(f"Không tự lưu được: {e}", job)


def save_export(job, folder, fmt, content, tgt):
    folder = folder or default_out_dir()
    os.makedirs(folder, exist_ok=True)
    data, ext = export_book(job.book, fmt, content, tgt)
    name = job.out_name(ext)
    if content != "vi":
        name = name[:-len(ext)] + "-song-ngu" + ext
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def resolve_src(cfg, job):
    s = cfg.get("source") or "auto"
    return job.lang if s == "auto" else s


def make_engine(cfg, job, src, tgt, stop, post):
    svc = cfg.get("service", "gtx")
    sc = (cfg.get("services") or {}).get(svc, {})
    st = job.settings
    glossary = parse_pairs(st.get("glossary", ""))
    batch = int(cfg.get("batch") or 40)
    delay = float(cfg.get("delay") or 0)
    chunk = int(cfg.get("chunk") or 2500)
    sub = job.book.kind == "sub"
    if sub:
        batch = int(cfg.get("subBatch") or 40)
    pre = (lambda t: apply_pairs(t, glossary)) if glossary else None
    eng = _make_engine(svc, sc, cfg, job, src, tgt, stop, post, batch, delay, chunk, sub, glossary, pre, st)
    eng.unit = "dòng" if sub else "đoạn"
    return eng


def _make_engine(svc, sc, cfg, job, src, tgt, stop, post, batch, delay, chunk, sub, glossary, pre, st):
    if svc == "gtx":
        endpoint = sc.get("url") or GTX_ENDPOINT
        legacy = "/translate_a/" in endpoint
        return BookMTEngine("GTX API (Google)", lambda L: gtx_translate(L, src, tgt, endpoint),
                            12 if legacy else 60, 4500, 3 if legacy else 2, 0.3, stop, post, maxlen=1500, pre=pre)
    if svc == "edge":
        return BookMTEngine("Edge API (Microsoft)", lambda L: edge_translate(L, src, tgt), 40, 4500, 2, 0.3,
                            stop, post, maxlen=1500, pre=pre)
    if svc == "hachimi":
        name = (sc.get("model") or "HachimiMT-60-QT").split("/")[-1]
        if name not in HACHIMI_MODELS:
            name = "HachimiMT-60-QT"
        return BookMTEngine(name, None, max(4, batch), 10 ** 9, 1, 0, stop, post, maxlen=150,
                            loader=hachimi_loader(name, sc.get("device") or "auto"))
    lsrc = resolve_src(cfg, job)
    url, model = sc.get("url", ""), sc.get("model", "")
    if not model:
        raise FatalError("Chưa chọn model.")
    common = dict(style=st.get("style", "tu_nhien"), glossary=glossary, max_chars=chunk, sub=sub)
    if svc == "ollama":
        return BookLLMEngine("ollama", url or "http://localhost:11434", "", model, batch, 0, st.get("note", ""),
                             lsrc, tgt, stop, post, **common)
    if svc == "lmstudio":
        return BookLLMEngine("openai", url or "http://localhost:1234/v1", "", model, batch, 0, st.get("note", ""),
                             lsrc, tgt, stop, post, **common)
    if not url:
        raise FatalError("Thiếu API URL.")
    if not sc.get("key"):
        raise FatalError("Chưa nhập API key cho dịch vụ này.")
    return BookLLMEngine("openai", url, sc.get("key"), model, batch, delay, st.get("note", ""), lsrc, tgt,
                         stop, post, **common)


STATE = None


# ================================================================ HTTP server

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def _job(self, jid):
        job = STATE.jobs.get(jid)
        if job is None:
            raise KeyError("Không tìm thấy sách")
        return job

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(BASE_DIR, "ui.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if u.path == "/api/ping":
                STATE.last_ping = time.time()
                return self._send(200, {"ok": True, "app": APP_NAME, "version": APP_VERSION})
            if u.path == "/api/config":
                cfg = load_config()
                cfg.setdefault("outDir", default_out_dir())
                return self._send(200, cfg)
            if u.path == "/api/status":
                STATE.last_ping = time.time()
                with STATE.lock:
                    jobs = [STATE.jobs[j].summary() for j in STATE.order if j in STATE.jobs]
                    lp = int(q.get("log", 0))
                    if lp > len(STATE.logs):
                        lp = 0
                    res = {"jobs": jobs, "running": STATE.running, "logs": STATE.logs[lp:], "logTotal": len(STATE.logs)}
                with STT.lock:
                    res["stt"] = [STT.jobs[i].summary() for i in STT.order if i in STT.jobs]
                    res["sttRunning"] = STT.running
                with STATE.lock:
                    job = STATE.jobs.get(q.get("job", ""))
                    if job is not None:
                        ev = int(q.get("ev", 0))
                        evs = job.events[ev:]
                        if -1 in evs:
                            res["reload"] = True
                        else:
                            a, b = int(q.get("a", 0)), int(q.get("b", 0))
                            res["updates"] = [[i, job.book.segs[i].vi] for i in sorted(set(evs)) if a <= i < b]
                        res["evTotal"] = len(job.events)
                        if evs or q.get("full"):
                            res["chProgress"] = job.chapter_progress()
                            segs = job.book.segs
                            res["chTitles"] = [(segs[c["start"]].vi or "").replace("\n", " ")
                                               if segs[c["start"]].kind == "h" else "" for c in job.book.chapters]
                return self._send(200, res)
            if u.path == "/api/office":
                return self._send(200, office_info())
            if u.path == "/api/update/check":
                try:
                    return self._send(200, check_update(bool(q.get("force"))))
                except Exception as e:
                    return self._send(200, {"current": APP_VERSION, "error": f"Không kiểm tra được bản mới: {e}",
                                            "mode": install_mode(), "newer": False})
            if u.path == "/api/update/status":
                return self._send(200, TASKS.public().get("update") or {})
            if u.path == "/api/stt/info":
                return self._send(200, stt_info())
            if u.path == "/api/stt/cues":
                j = STT.jobs.get(q.get("id", ""))
                if j is None:
                    raise KeyError("Không tìm thấy file")
                f = max(0, int(q.get("from", 0)))
                with STT.lock:
                    cues = j.cues
                    f = min(f, len(cues))
                    return self._send(200, {"total": len(cues), "from": f, "cues": cues[f:f + 3000],
                                            "job": j.summary()})
            if u.path == "/api/stt/srt":
                j = STT.jobs.get(q.get("id", ""))
                if j is None or not j.cues:
                    raise KeyError("Chưa có phụ đề")
                name = f"{os.path.splitext(j.name)[0]}.{j.lang or 'auto'}.srt"
                disp = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
                    re.sub(r"[^\x20-\x7e]", "_", name).replace('"', ""), urllib.parse.quote(name))
                return self._send(200, "\ufeff" + cues_to_srt(j.cues).replace("\n", "\r\n"),
                                  "application/x-subrip; charset=utf-8", {"Content-Disposition": disp})
            if u.path == "/api/hachimi":
                return self._send(200, hachimi_status())
            if u.path == "/api/book":
                job = self._job(q.get("id", ""))
                with STATE.lock:
                    segs = job.book.segs
                    chs = [{"title": c["title"], "vi": (segs[c["start"]].vi or "").replace("\n", " ")
                            if segs[c["start"]].kind == "h" else "", "start": c["start"], "end": c["end"]}
                           for c in job.book.chapters]
                    return self._send(200, {"job": job.summary(), "chapters": chs, "progress": job.chapter_progress(),
                                            "settings": job.settings, "evTotal": len(job.events)})
            if u.path == "/api/chapter":
                job = self._job(q.get("id", ""))
                c = job.book.chapters[int(q.get("ch", 0))]
                with STATE.lock:
                    segs = [[s.src, s.vi, s.kind, s.time] for s in job.book.segs[c["start"]:c["end"]]]
                return self._send(200, {"start": c["start"], "end": c["end"], "segs": segs})
            if u.path == "/api/download":
                job = self._job(q.get("id", ""))
                fmt, content, tgt = q.get("fmt", "orig"), q.get("content", "vi"), q.get("tgt", "vi")
                with STATE.lock:
                    data, ext = export_book(job.book, fmt, content, tgt)
                name = job.out_name(ext)
                if content != "vi":
                    name = name[:-len(ext)] + "-song-ngu" + ext
                disp = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
                    re.sub(r"[^\x20-\x7e]", "_", name).replace('"', ""), urllib.parse.quote(name))
                return self._send(200, data, "application/octet-stream", {"Content-Disposition": disp})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            log_file(f"GET {u.path} lỗi: {e!r}")
            return self._send(400, {"error": str(e)})

    def _upload(self, q):
        name = os.path.basename((q.get("name") or "file").replace("\\", "/")) or "file"
        if os.path.splitext(name)[1].lower() not in MEDIA_EXTS:
            raise ValueError("Không phải file âm thanh hoặc video")
        n = int(self.headers.get("Content-Length") or 0)
        d = os.path.join(STT_DIR, "uploads", uuid.uuid4().hex[:10])
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        try:
            with open(path, "wb") as f:
                while n > 0:
                    chunk = self.rfile.read(min(n, 1 << 20))
                    if not chunk:
                        raise ValueError("Tải file lên bị ngắt giữa chừng")
                    f.write(chunk)
                    n -= len(chunk)
            return STT.add(path, name, uploaded=True)
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            raise

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            if u.path == "/api/stt/upload":
                q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                return self._send(200, {"job": self._upload(q).summary()})
            d = self._json()
            if u.path == "/api/config":
                save_config(d)
                return self._send(200, {"ok": True})
            if u.path == "/api/open":
                added, errors = [], []
                for f in d.get("files", []):
                    try:
                        job = STATE.add(f["name"], base64.b64decode(f["data"]))
                        added.append(job.summary())
                    except Exception as e:
                        errors.append(f"{f.get('name')}: {e}")
                        log_file(f"Mở {f.get('name')} lỗi: {e!r}")
                return self._send(200, {"added": added, "errors": errors})
            if u.path == "/api/remove":
                for jid in d.get("ids", []):
                    STATE.remove(jid)
                return self._send(200, {"ok": True})
            if u.path == "/api/clear":
                mode = d.get("mode", "done")
                with STATE.lock:
                    ids = [j for j in STATE.order if j in STATE.jobs and STATE.jobs[j].status not in ("running", "queued")
                           and (mode == "all" or STATE.jobs[j].status == "done")]
                for jid in ids:
                    STATE.remove(jid)
                STATE.log(f"Đã xoá {len(ids)} tài liệu khỏi lịch sử.")
                return self._send(200, {"removed": len(ids)})
            if u.path == "/api/clear_log":
                with STATE.lock:
                    STATE.logs.clear()
                return self._send(200, {"ok": True})
            if u.path == "/api/settings":
                job = self._job(d["id"])
                job.settings.update({k: str(v) for k, v in (d.get("settings") or {}).items() if k in DEFAULT_SETTINGS})
                job.save_meta()
                return self._send(200, {"ok": True})
            if u.path == "/api/translate":
                cfg = d.get("config", {})
                if cfg.get("service") == "hachimi" and (cfg.get("target") or "vi") != "vi":
                    return self._send(400, {"error": "HachimiMT chỉ dịch sang tiếng Việt."})
                n = STATE.enqueue(d.get("ids", []), cfg, bool(d.get("restart")), d.get("chapter"))
                return self._send(200, {"queued": n})
            if u.path == "/api/stop":
                STATE.request_stop()
                return self._send(200, {"ok": True})
            if u.path == "/api/edit":
                job = self._job(d["id"])
                i = int(d["i"])
                txt = d.get("text")
                with STATE.lock:
                    job.book.segs[i].vi = txt if txt and txt.strip() else None
                    job.events.append(i)
                    job.dirty = True
                return self._send(200, {"ok": True})
            if u.path == "/api/save":
                job = self._job(d["id"])
                with STATE.lock:
                    job.saved = save_export(job, d.get("outDir"), d.get("fmt", "orig"), d.get("content", "vi"),
                                            d.get("tgt", "vi"))
                job.save_progress()
                STATE.log(f"Đã lưu: {job.saved}", job)
                return self._send(200, {"path": job.saved})
            if u.path == "/api/open_folder":
                folder = d.get("path") or default_out_dir()
                if os.path.isfile(folder):
                    folder = os.path.dirname(folder)
                os.makedirs(folder, exist_ok=True)
                if sys.platform == "win32":
                    os.startfile(folder)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", folder])
                else:
                    subprocess.Popen(["xdg-open", folder])
                return self._send(200, {"ok": True})
            if u.path == "/api/models":
                svc = d.get("service")
                kind = "ollama" if svc == "ollama" else "openai"
                try:
                    return self._send(200, {"models": list_models(kind, d.get("url", ""), d.get("key"))})
                except Exception as e:
                    msg = str(e)
                    if svc == "ollama" and ("10061" in msg or "refused" in msg.lower()):
                        msg = "Ollama chưa chạy. Cài tại ollama.com rồi mở Ollama từ Start Menu."
                    return self._send(200, {"models": [], "error": msg})
            if u.path == "/api/update/run":
                TASKS.start("update", "Cập nhật app", update_task())
                return self._send(200, {"ok": True})
            if u.path == "/api/open_url":
                url = d.get("url", "")
                if not url.startswith(("https://github.com/", "https://console.groq.com/", "https://aistudio.google.com/")):
                    raise ValueError("Địa chỉ không hợp lệ")
                webbrowser.open(url)
                return self._send(200, {"ok": True})
            if u.path == "/api/stt/pick":
                try:
                    paths = pick_files_dialog()
                except RuntimeError:
                    return self._send(200, {"noDialog": True})
                added, errors = [], []
                for p_ in paths:
                    try:
                        added.append(STT.add(p_).summary())
                    except Exception as e:
                        errors.append(f"{os.path.basename(p_)}: {e}")
                return self._send(200, {"added": added, "errors": errors})
            if u.path == "/api/stt/add":
                added, errors = [], []
                for p_ in d.get("paths", []):
                    try:
                        added.append(STT.add(p_).summary())
                    except Exception as e:
                        errors.append(f"{os.path.basename(p_)}: {e}")
                return self._send(200, {"added": added, "errors": errors})
            if u.path == "/api/stt/start":
                cfg = d.get("config") or {}
                ids = d.get("ids") or [i for i in STT.order if STT.jobs[i].status in ("ready", "stopped", "error")]
                return self._send(200, {"queued": STT.enqueue(ids, cfg)})
            if u.path == "/api/stt/stop":
                STT.request_stop()
                return self._send(200, {"ok": True})
            if u.path == "/api/stt/remove":
                for jid in d.get("ids", []):
                    STT.remove(jid)
                return self._send(200, {"ok": True})
            if u.path == "/api/stt/clear":
                mode = d.get("mode", "done")
                with STT.lock:
                    ids = [i for i in STT.order if STT.jobs[i].status not in ("running", "queued")
                           and (mode == "all" or STT.jobs[i].status == "done")]
                for jid in ids:
                    STT.remove(jid)
                return self._send(200, {"removed": len(ids)})
            if u.path == "/api/stt/translate":
                j = STT.jobs.get(d.get("id", ""))
                if j is None:
                    raise KeyError("Không tìm thấy file")
                job = STT.to_library(j, d.get("config") or {}, os.path.dirname(j.srt) if j.srt else None)
                return self._send(200, {"libId": job.id})
            if u.path == "/api/stt/model":
                name = d.get("name")
                if name not in STT_MODELS:
                    raise ValueError("Model không hợp lệ")
                if d.get("delete"):
                    shutil.rmtree(stt_model_dir(name), ignore_errors=True)
                else:
                    TASKS.start("whisper:" + name, f"Tải Whisper {name}", download_stt_model_task(name))
                return self._send(200, {"ok": True})
            if u.path == "/api/stt/gpu":
                TASKS.start("sttgpu", "Tải thư viện GPU cho Whisper", download_stt_gpu_task())
                return self._send(200, {"ok": True})
            if u.path == "/api/stt/libs":
                TASKS.start("sttlibs", "Cài thư viện Whisper", install_stt_libs_task())
                return self._send(200, {"ok": True})
            if u.path == "/api/hachimi/download":
                name = d.get("name")
                if name not in HACHIMI_MODELS:
                    raise ValueError("Model không hợp lệ")
                TASKS.start("model:" + name, f"Tải {name}", download_model_task(name))
                return self._send(200, {"ok": True})
            if u.path == "/api/hachimi/cuda":
                TASKS.start("cuda", "Tải thư viện GPU (CUDA 12)", download_cuda_task())
                return self._send(200, {"ok": True})
            if u.path == "/api/hachimi/libs":
                TASKS.start("libs", "Cài thư viện HachimiMT", install_libs_task())
                return self._send(200, {"ok": True})
            if u.path == "/api/hachimi/reprobe":
                release_worker()
                probe_async(force=True)
                return self._send(200, {"ok": True})
            if u.path == "/api/hachimi/cancel":
                TASKS.cancel(d.get("key", ""))
                return self._send(200, {"ok": True})
            if u.path == "/api/hachimi/delete":
                name = d.get("name")
                if name in HACHIMI_MODELS and os.path.isdir(model_dir(name)):
                    shutil.rmtree(model_dir(name), ignore_errors=True)
                    release_worker()
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            log_file(f"POST {u.path} lỗi: {e!r}")
            return self._send(400, {"error": str(e)})


# ================================================================ khởi động

def find_browser():
    cands = []
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif sys.platform == "darwin":
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        cands = [shutil.which(x) for x in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def open_window(url):
    exe = find_browser()
    win = load_config().get("win") or {}
    w, h = int(win.get("w") or 1380), int(win.get("h") or 900)
    w, h = max(900, min(w, 7680)), max(620, min(h, 4320))
    args = [f"--app={url}", f"--window-size={w},{h}", "--no-first-run", "--no-default-browser-check"]
    if win.get("x") is not None and win.get("y") is not None and -50 < int(win["x"]) < 7000 and -50 < int(win["y"]) < 4000:
        args.append(f"--window-position={int(win['x'])},{int(win['y'])}")
    if exe:
        try:
            kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
            subprocess.Popen([exe] + args, **kw)
            return
        except Exception:
            pass
    webbrowser.open(url)


def already_running(url):
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=2) as r:
            return json.loads(r.read().decode()).get("app") == APP_NAME
    except Exception:
        return False


def main():
    global STATE, STT
    if "--stt-worker" in sys.argv:
        stt_worker_main(int(sys.argv[sys.argv.index("--stt-worker") + 1]))
        return
    if "--hachimi-worker" in sys.argv:
        worker_main(int(sys.argv[sys.argv.index("--hachimi-worker") + 1]))
        return
    log_file(f"=== Mở {APP_NAME} {APP_VERSION} (portable={PORTABLE}, mode={install_mode()}) ===")
    after_update = "--after-update" in sys.argv
    if after_update:
        time.sleep(1)
    cleanup_old_update()
    url = f"http://127.0.0.1:{PORT}/"
    server = None
    for _ in range(40 if after_update else 1):     # sau khi cập nhật: chờ bản cũ tắt hẳn, nhả cổng
        try:
            server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
            break
        except OSError:
            time.sleep(0.5)
    if server is None:
        if already_running(url):
            open_window(url)
            return
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
    STATE = State()
    STT = SttState()
    setup_cuda_path()
    threading.Thread(target=office_info, daemon=True).start()
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if after_update:
        # cửa sổ cũ vẫn mở và tự tải lại; không thấy nó thì mở cửa sổ mới
        def reopen(t0=time.time()):
            time.sleep(12)
            if STATE.last_ping < t0:
                open_window(url)
        STATE.last_ping = 0
        threading.Thread(target=reopen, daemon=True).start()
    elif "--no-window" not in sys.argv:
        open_window(url)
    if sys.stdout:
        try:
            print(f"{APP_NAME} đang chạy tại {url}  (đóng cửa sổ app để thoát)")
        except Exception:
            pass
    # tự thoát khi cửa sổ đã đóng lâu và không còn dịch
    try:
        while not UPDATE_EXIT.is_set():
            UPDATE_EXIT.wait(5)
            if UPDATE_EXIT.is_set():
                break
            idle = time.time() - max(STATE.last_ping, START_TIME)
            if idle > 150 and STATE.running is None and STATE.q.empty() and not STT.busy() \
                    and "--no-window" not in sys.argv:
                break
    except KeyboardInterrupt:
        pass
    release_worker()
    STT.request_stop()
    server.shutdown()


if __name__ == "__main__":
    main()

