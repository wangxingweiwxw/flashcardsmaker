"""Extract reviewed PDF art and package self-contained flashcard illustrations.

Numbers/calendars are deterministic SVG teaching diagrams, rendered by Chromium.
Illustrative bitmap additions come from the built-in image_gen tool, not drawing code.
"""
import base64
from collections import Counter
from io import BytesIO
import json
import math
from pathlib import Path
import runpy
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/junior-image-review'
PAGES = ROOT / 'tmp/pdfs/junior3500'
GENERATED = ROOT / 'outputs/junior-generated'
CROPS = runpy.run_path(str(ROOT / 'tools/data/junior-image-crops.py'))['CROPS']


def svg_diagrams(words):
    diagrams = {}
    start = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="220" viewBox="0 0 320 220"><rect width="320" height="220" rx="16" fill="#fffdf7"/><g stroke="#353931" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
    def circle(x,y,r,color):
        return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'
    def number(x,y,n,size=22,color='#353931'):
        return f'<text x="{x}" y="{y}" font-family="Arial" font-size="{size}" text-anchor="middle" stroke="none" fill="{color}">{n}</text>'
    def save(word,body):
        diagrams[word.casefold()] = start + body + '</g></svg>'
    numbers = dict(zip('one two three four five six seven eight nine eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(),list(range(1,10))+list(range(11,21))))
    numbers.update({f'twenty-{w}':20+n for w,n in list(numbers.items()) if n<10})
    numbers.update(dict(zip('thirty forty fifty sixty seventy eighty ninety hundred'.split(),range(30,101,10))))
    for word,n in numbers.items():
        cols=min(10,n); rows=math.ceil(n/cols); gap=min(30,155/max(rows,1)); radius=min(10,gap/2.8)
        body=number(160,35,n,30)
        for i in range(n):
            x=160+(i%cols-(cols-1)/2)*25; y=64+i//cols*gap
            body+=circle(x,y,radius,['#edb956','#86bd87','#73adc8'][i//10%3])
        save(word,body)
    ordinals=dict(zip('first second third fourth fifth sixth seventh eighth ninth tenth twelfth twentieth'.split(),[1,2,3,4,5,6,7,8,9,10,12,20]))
    for word,n in ordinals.items():
        total=10 if n<=10 else 20
        body='<path d="M28 64 H292 M280 57 L292 64 L280 71" fill="none" stroke="#4568a6"/>'
        for i in range(1,total+1):
            x=42+((i-1)%10)*26;y=110+((i-1)//10)*57
            body+=circle(x,y,12,'#f3b84e' if i==n else '#e9eee7')+number(x,y+5,i,14)
            if i==n:body+=f'<path d="M{x-7} {y-32} L{x+7} {y-32} L{x} {y-19} Z" fill="#e46d5f"/>'
        save(word,body)
    days='Monday Tuesday Wednesday Thursday Friday Saturday Sunday'.split()
    months='January February March April May June July August September October November December'.split()
    for is_month,names in [(False,days),(True,months)]:
        for i,word in enumerate(names,1):
            body='<rect x="23" y="25" width="274" height="172" rx="12" fill="white"/><path d="M23 65 H297" fill="none" stroke="#4568a6"/><path d="M72 16 V39 M248 16 V39" stroke-width="6"/>'
            body+=number(160,54,'12' if is_month else '7',23)
            cols=4 if is_month else 7
            for k in range(1,len(names)+1):
                x=(61+((k-1)%4)*65) if is_month else (49+(k-1)*37)
                y=(94+((k-1)//4)*36) if is_month else 127
                body+=circle(x,y,15,'#f3b84e' if k==i else '#e9eee7')+number(x,y+6,k,17)
            save(word,body)
    for word,n in [('yesterday',13),('today',14),('tomorrow',15)]:
        body=''
        for k in [13,14,15]:
            x=25+(k-13)*96
            body+=f'<rect x="{x}" y="66" width="78" height="99" rx="9" fill="'+('#f3cf7b' if k==n else '#f4f4ee')+'"/>'
            body+=f'<path d="M{x} 91 H{x+78} M{x+16} 57 V77 M{x+61} 57 V77" fill="none"/>'+number(x+39,136,k,29)
            if k==14:body+=f'<path d="M{x+39} 178 l4 8 9 1 -7 6 2 9 -8 -4 -8 4 2 -9 -7 -6 9 -1 Z" fill="#79b78b"/>'
        save(word,body)
    save('left','<path d="M260 81 H134 V47 L50 111 134 175 V141 H260 Z" fill="#6da8cd"/>')
    save('right','<path d="M60 81 H186 V47 L270 111 186 175 V141 H60 Z" fill="#e78b69"/>')
    save('sell','<path d="M71 52 H215 L276 111 215 170 H71 Z" fill="#f1c96f"/><circle cx="239" cy="111" r="9" fill="white"/><path d="M239 102 Q290 47 298 83" fill="none"/>'+number(153,135,'$',68))
    return diagrams


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    deck=json.loads((ROOT/'decks/junior-themed-vocabulary/deck.json').read_text(encoding='utf-8'))
    words=[c['front']['primary'] for c in deck['cards']]
    all_images={}; page_cache={}
    for word,spec in CROPS.items():
        page=spec['page']
        if page not in page_cache:page_cache[page]=Image.open(PAGES/f'page-{page:02}.png').convert('RGB')
        im=page_cache[page]; scale=im.width/1000
        x,y,w,h=spec['box']; bounds=tuple(round(v*scale) for v in (x,y,x+w,y+h))
        assert bounds[2]<=im.width and bounds[3]<=im.height,(word,bounds,im.size)
        all_images[word]=(im.crop(bounds),dict(kind='pdf-crop',page=page,box=spec['box']))
    for p in GENERATED.glob('*.png'):
        all_images[p.stem.casefold()]=(Image.open(p).convert('RGB'),dict(kind='generated',file=p.name))
    for target,source in [('violinist','violin'),('lend','borrow'),('taxi driver','taxi')]:
        if source in all_images:all_images[target]=all_images[source]
    diagrams=svg_diagrams(words)
    if diagrams:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport=dict(width=320,height=220),device_scale_factor=1)
            for word,svg in diagrams.items():
                page.set_content('<style>body{margin:0}</style>'+svg)
                data=page.screenshot()
                all_images[word]=(Image.open(BytesIO(data)).convert('RGB'),dict(kind='teaching-diagram',diagram=word))
            browser.close()
    result={}; thumbnails=[]
    for word in words:
        key=word.casefold()
        if key not in all_images:continue
        im,meta=all_images[key]
        # Present small source icons at a readable card size, retaining aspect ratio.
        if meta['kind']=='pdf-crop':
            factor=min(224/im.width,144/im.height)
            im=im.resize((round(im.width*factor),round(im.height*factor)),Image.Resampling.LANCZOS)
        else:
            im.thumbnail((256,192),Image.Resampling.LANCZOS)
        stream=BytesIO();im.save(stream,format='WEBP',quality=72,method=6)
        result[key]=dict(**meta,image='data:image/webp;base64,'+base64.b64encode(stream.getvalue()).decode())
        thumbnails.append((word,im,meta))
    target=ROOT/'tools/data/junior-illustrations.json'
    target.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',12)
    for start in range(0,len(thumbnails),80):
        sheet=Image.new('RGB',(1200,1300),'#e7e9e4');draw=ImageDraw.Draw(sheet)
        for i,(word,im,meta) in enumerate(thumbnails[start:start+80]):
            x=(i%8)*150;y=(i//8)*130
            draw.rectangle((x+2,y+2,x+147,y+105),fill='white')
            preview=im.copy();preview.thumbnail((140,95))
            sheet.paste(preview,(x+(150-preview.width)//2,y+5+(95-preview.height)//2))
            label=word[:24];source='p'+str(meta['page']) if 'page' in meta else meta['kind']
            draw.text((x+4,y+107),label,fill='black',font=font);draw.text((x+4,y+119),source,fill='#4568a6',font=font)
        sheet.save(OUT/f'contact-{start//80+1:02}.jpg',quality=92)
    missing=[w for w in words if w.casefold() not in result]
    print(json.dumps(dict(images=len(result),missing=missing,kinds=dict(Counter(v['kind'] for v in result.values())),bytes=target.stat().st_size)))
    if missing:raise SystemExit(1)


if __name__=='__main__':main()
