import re, html
p = r"C:\Users\thofe\LearnLoop\content\applied-ch10-12.html"
s = open(p, encoding="utf-8").read()
t = re.sub(r"<[^>]+>", "", s)
t = html.unescape(t)
print("bare tokens:", len(t.split()))
print("alnum tokens:", len(re.findall(r"[A-Za-z0-9][^\s]*", t)))
print("em dashes:", t.count("\u2014"))
print(repr(t[:300]))
