import sys, os
sys.stderr = open(os.devnull, 'w')
import parser as rp, json, fitz

base = r'C:\Users\HP\DOWNLOADS'
files = {}
for f in os.listdir(base):
    fl = f.lower()
    if fl.endswith('.pdf'):
        if 'muskan' in fl: files['muskan'] = os.path.join(base, f)

if 'muskan' in files:
    print("=== MUSKAN SOURCE - ALL text on page 1 ===")
    doc = fitz.open(files['muskan'])
    print("Source:", os.path.basename(files['muskan']))
    page = doc[0]
    # Get all text blocks with positions
    blocks = page.get_text("dict", sort=True)["blocks"]
    for blk in blocks:
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                flags = span.get('flags', 0)
                # bold or italic or notable size
                if span["size"] > 8 and span["x0"] < 250:
                    txt = span['text'].strip()[:80]
                    if txt:
                        print(f"  y={int(span['y0']):3d} x={int(span['x0']):3d} size={span['size']:.1f} bold={bool(flags&16)} ital={bool(flags&4)} font={span['font'][:20]} : '{txt}'")
    print("\n=== MUSKAN PARSED SECTIONS ===")
    d2 = rp.parse_pdf(files['muskan'])
    secs = d2['structured']['sections']
    for sec in secs:
        print(f"  title='{sec.get('title')}' key={sec.get('key')} entries={len(sec.get('entries',[]))}")
    for sec in secs:
        if sec.get('key','').lower() == 'experience':
            print(f"\n=== MUSKAN EXPERIENCE ===")
            print(json.dumps(sec['entries'], indent=2, default=str)[:3000])
            break
files = {}
for f in os.listdir(base):
    fl = f.lower()
    if fl.endswith('.pdf'):
        if 'kanish' in fl: files['kanish'] = os.path.join(base, f)
        if 'muskan' in fl: files['muskan'] = os.path.join(base, f)

print("FOUND FILES:", {k: os.path.basename(v) for k,v in files.items()})

if 'kanish' in files:
    d = rp.parse_pdf(files['kanish'])
    secs = d['structured']['sections']
    print("\n=== KANISH SECTIONS ===")
    for sec in secs:
        st = sec.get('structured') or sec.get('type') or sec.get('key') or ''
        print(f"  title='{sec.get('title')}' key={sec.get('key')} type={sec.get('type')}")
    # find education section
    for sec in secs:
        if sec.get('key','').lower() == 'education' or 'educat' in (sec.get('title','').lower()):
            print(f"\n=== KANISH EDUCATION SECTION (key={sec.get('key')}) ===")
            print(json.dumps(sec.get('entries', sec), indent=2, default=str)[:2000])
            break

if 'muskan' in files:
    print("\n=== MUSKAN SOURCE - experience-region spans ===")
    doc = fitz.open(files['muskan'])
    print("Source:", os.path.basename(files['muskan']))
    for pi, page in enumerate(doc):
        try:
            blocks = page.get_text("dict", sort=True)["blocks"]
        except Exception:
            blocks = page.get_text("dict")["blocks"]
        for blk in blocks:
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    if span["x0"] < 300 and span["size"] > 9:
                        flags = span.get('flags', 0)
                        txt = span['text'].strip()[:70]
                        if txt and not txt.startswith('('):
                            print(f"  y={int(span['y0'])} x={int(span['x0'])} size={span['size']:.1f} bold={bool(flags&16)} ital={bool(flags&4)} font={span['font'][:25]} : '{txt}'")
    print("\n=== MUSKAN PARSED SECTIONS ===")
    d2 = rp.parse_pdf(files['muskan'])
    secs = d2['structured']['sections']
    for sec in secs:
        print(f"  title='{sec.get('title')}' key={sec.get('key')} type={sec.get('type')} entries={len(sec.get('entries',[]))}")
    for sec in secs:
        if sec.get('key','').lower() == 'experience':
            print(f"\n=== MUSKAN EXPERIENCE (key={sec.get('key')}) ===")
            print(json.dumps(sec['entries'], indent=2, default=str)[:2500])
            break