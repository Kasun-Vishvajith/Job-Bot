import re
with open('roadmap.html', 'r', encoding='utf-8') as f:
    html = f.read()
css_match = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
if css_match:
    with open('roadmap_css.txt', 'w', encoding='utf-8') as out:
        out.write(css_match.group(1))
    print("Done")
