import re, html

path = r"C:\Users\thofe\LearnLoop\content\applied-ch10-12.html"
src = open(path, encoding="utf-8").read()
sections = re.findall(r"<section class=\"chapter\">.*?</section>", src, re.S)

def text_of(fragment):
    t = fragment
    t = re.sub(r"<(?:/p|/pre|/h1|/h2|/div|/section|br\s*/?|/li|/code)>", " ", t)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t)

for i, sec in enumerate(sections, 1):
    h1 = re.search(r"<h1>(.*?)</h1>", sec, re.S).group(1)
    prose = re.sub(r"<pre>.*?</pre>", " ", sec, flags=re.S)
    code_blocks = re.findall(r"<pre><code>(.*?)</code></pre>", sec, re.S)
    pw = len(text_of(prose).split())
    cw = sum(len(html.unescape(c).split()) for c in code_blocks)
    print(f"{i}. {h1}\n   prose={pw} code={cw} total={pw+cw}")

print("TOTAL:", len(text_of(src).split()))
