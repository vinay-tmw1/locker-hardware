import json, base64, html

products = json.load(open('products.json'))

def truncate_name(name):
    name = name.strip()
    if len(name) <= 8:
        return html.escape(name)
    return html.escape(name[:8]) + "..."

def img_to_b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')

ROWS_PER_PAGE = 14
COLS = 4
PER_PAGE = ROWS_PER_PAGE * COLS

cells_html = []
for p in products:
    b64 = img_to_b64(p['img'])
    name_display = truncate_name(p['name'])
    sku_display = html.escape(p['sku'])
    cell = f'''<div class="box">
  <img class="qr" src="data:image/png;base64,{b64}" alt="QR"/>
  <div class="info">
    <div class="pname">{name_display}</div>
    <div class="psku">{sku_display}</div>
  </div>
</div>'''
    cells_html.append(cell)

# pad last page with empty boxes to keep grid lines consistent (optional - blank box keeps border)
total = len(cells_html)
pages = []
for i in range(0, total, PER_PAGE):
    chunk = cells_html[i:i+PER_PAGE]
    # pad to full page so grid/border stays a complete rectangle
    while len(chunk) < PER_PAGE:
        chunk.append('<div class="box empty"></div>')
    pages.append(chunk)

page_blocks = []
for chunk in pages:
    grid = '\n'.join(chunk)
    page_blocks.append(f'<div class="sheet">\n{grid}\n</div>')

all_pages_html = '\n'.join(page_blocks)

css = '''
@page {
  size: A4;
  margin: 0;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
}
body {
  font-family: Arial, Helvetica, sans-serif;
}
.sheet {
  width: 21cm;
  height: 29.6996cm;
  display: grid;
  grid-template-columns: repeat(4, 5.25cm);
  grid-template-rows: repeat(14, 2.1214cm);
  page-break-after: always;
}
.sheet:last-child {
  page-break-after: auto;
}
.box {
  border: none;
  box-sizing: border-box;
  width: 5.25cm;
  height: 2.1214cm;
  display: flex;
  align-items: center;
  overflow: hidden;
  padding: 0;
}
.box.empty {
  border: none;
}
.qr {
  height: calc(2.1214cm - 2mm);
  width: calc(2.1214cm - 2mm);
  margin-left: 1mm;
  flex-shrink: 0;
  display: block;
  object-fit: contain;
}
.info {
  flex: 1;
  min-width: 0;
  padding-left: 2mm;
  padding-right: 1mm;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
}
.pname {
  font-weight: bold;
  font-size: 9pt;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}
.psku {
  font-weight: normal;
  font-size: 7.5pt;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-align: left;
  margin-top: 0.8mm;
  color: #000;
}
'''

html_doc = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Inventory QR Labels</title>
<style>{css}</style>
</head>
<body>
{all_pages_html}
</body>
</html>'''

with open('labels.html', 'w', encoding='utf-8') as f:
    f.write(html_doc)

print(f'Generated {len(pages)} pages for {total} products')