import os

files = ['index.html', 'roadmap.html']
favicon_html = "<link rel=\"icon\" href=\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%236d56ff'/><text x='50' y='72' font-family='sans-serif' font-size='70' font-weight='900' fill='%23ffffff' text-anchor='middle'>J</text></svg>\">"

for file in files:
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if already has favicon
        if "rel=\"icon\"" not in content:
            # Insert after <title>
            if "<title>" in content:
                content = content.replace("</title>", f"</title>\n  {favicon_html}")
            else:
                content = content.replace("<head>", f"<head>\n  {favicon_html}")
            
            with open(file, 'w', encoding='utf-8') as f:
                f.write(content)
        print(f"Updated {file}")
