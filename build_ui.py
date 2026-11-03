"""Tạo ui.html từ ui_src.html (nhúng logo). Chạy: python build_ui.py"""
import base64
import os

D = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(D, "ui_src.html"), encoding="utf-8").read()
fav = "data:image/svg+xml;base64," + base64.b64encode(open(os.path.join(D, "logo_small.svg"), "rb").read()).decode()
logo = open(os.path.join(D, "logo.svg"), encoding="utf-8").read()
logo = logo[logo.index("<svg"):]
open(os.path.join(D, "ui.html"), "w", encoding="utf-8").write(s.replace("%%FAV%%", fav).replace("%%LOGO%%", logo))
print("Đã tạo ui.html")
