"""C-phase verification: C.6 (colon/orphan-meta) + C.7 (phrase wrap) +
hanging bullet indent, all measured on the rendered PDF."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz

import parser as rp
import template_engine as te

PDF = r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf"
fails = []


def check(name, cond, detail=""):
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        fails.append(name)


p = rp.parse_pdf(PDF)
st = p["structured"]

# --- C.6a: no doubled colons anywhere in skills items -------------------
# select the skills section by TYPE / canonical key (the source-faithful
# title may be 'Skills Summary' or 'Technical Skills', not literally 'Skills')
skills_secs = [s for s in st.get("sections", [])
               if s.get("type") == "skills"
               or (s.get("key") or "").lower() == "skills"]
items = [i for s in skills_secs for i in s.get("items", [])]
doubles = [i for i in items if "::" in i]
check("C.6a no '::' in skills items", not doubles, repr(doubles[:1]))
env = [i for i in items if "Environments" in i]
check("C.6a environments line single colon",
      bool(env) and env[0].count(":") == 1, repr(env[:1]))

# --- C.7: coursework merged into one item ------------------------------
cw = [i for i in items if "Coursework" in i]
check("C.7 coursework is ONE item", len(cw) == 1
      and "Object Oriented Programming" in cw[0], repr(cw))

# --- render ------------------------------------------------------------
pdf = te.generate_pdf(st, "classic")
doc = fitz.open(stream=pdf, filetype="pdf")
page = doc[0]

lines = []           # (y0, x0, text)
for blk in page.get_text("dict")["blocks"]:
    for ln in blk.get("lines", []):
        txt = "".join(s["text"] for s in ln["spans"])
        lines.append((round(ln["bbox"][1], 1), round(ln["bbox"][0], 1), txt))
lines.sort()


def find_line(sub):
    return [l for l in lines if sub in l[2]]


# --- C.6a render: single colon on environments row ---------------------
env_lines = find_line("Environments:")
check("C.6a render 'Environments: Docker' (one colon)",
      bool(env_lines) and env_lines[0][2].count(":") == 1
      and "::" not in env_lines[0][2], env_lines[:1])

# --- C.6b: 'Remote' shares the title/meta row ---------------------------
remote = find_line("Remote")
cel = find_line("Celebal")
ok = bool(remote) and bool(cel)
if ok:
    same_y = any(abs(r[0] - c[0]) < 2.5 for r in remote for c in cel)
    lone = [r for r in remote if r[2].strip() == "Remote"]
    ok = same_y and not lone
check("C.6b '· Remote' stays inline with title/meta row", ok,
      "remote@%s celebal@%s" % ([r[0] for r in remote],
                                [c[0] for c in cel][:1]))

# --- C.7 render: phrase not split across lines --------------------------
split_obj = [l for l in lines if l[2].strip() == "Oriented Programming"]
check("C.7 render: no lone 'Oriented Programming' line", not split_obj,
      repr(split_obj[:1]))
course = find_line("Coursework")
all_txt = "\n".join(l[2] for l in lines)
check("C.7 render: phrase intact as unit (NBSP-joined)",
      "Object\u00a0Oriented\u00a0Programming" in all_txt
      or "Object Oriented Programming" in all_txt,
      repr([l[2] for l in lines if "Oriented" in l[2]]))
bare = [l for l in lines
        if l[2].rstrip().endswith("Object")
        and "Oriented" not in l[2]]
check("C.7 render: no line ends with orphan 'Object'", not bare,
      repr(bare[:1]))

# --- hanging indent: wrapped bullet line2 aligns under line1 TEXT -------
def bullet_rows():
    rows = []
    for i, (y, x, t) in enumerate(lines):
        if t.strip().startswith("\u2022"):
            rows.append(i)
    return rows


def text_x0(page_obj, y0):
    """x0 of the first non-marker span on the bullet line at y0."""
    for blk in page_obj.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            if abs(ln["bbox"][1] - y0) < 1.5:
                for sp in ln["spans"]:
                    if sp["text"].strip() and sp["text"].strip() != "\u2022":
                        return sp["bbox"][0]
    return None


_KNOWN_TITLES = set()
for _s in st.get("sections", []):
    _KNOWN_TITLES.add(_s.get("title", ""))
    for _e in _s.get("entries", []) or []:
        _KNOWN_TITLES.add(str(_e.get("title", "")).strip())

hang_checks, hang_ok, hang_details = 0, 0, []
for i in bullet_rows():
    y, x, t = lines[i]
    if i + 1 >= len(lines):
        continue
    y2, x2, t2 = lines[i + 1]
    if y2 - y > 12 or y2 - y < 4 or not t2.strip():
        continue
    if t2.strip().startswith("\u2022"):
        continue
    if t2.strip() in _KNOWN_TITLES:      # new entry heading, not a wrap
        continue
    tx = text_x0(page, y)
    if tx is None:
        continue
    hang_checks += 1
    good = abs(x2 - tx) <= 3.0
    hang_ok += good
    hang_details.append("L1 text x0=%.1f  L2 x0=%.1f  delta=%+.1f %s %r"
                        % (tx, x2, x2 - tx, "OK" if good else "BAD",
                           t2[:20]))
check("hanging indent: wrapped lines align under bullet text",
      hang_checks > 0 and hang_ok == hang_checks,
      "%d/%d aligned" % (hang_ok, hang_checks))
for d in hang_details:
    if "BAD" in d:
        print("        " + d)

# visual evidence PNGs
page.get_pixmap(clip=fitz.Rect(0, 100, page.rect.width, 175), dpi=260).save(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "_c6_meta.png"))
page.get_pixmap(clip=fitz.Rect(0, 175, page.rect.width, 330), dpi=260).save(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "_c7_skills.png"))
doc.close()

print("\n== C-phase: %s ==" % ("GREEN - 0 failures" if not fails
                              else "RED: %s" % fails))
sys.exit(1 if fails else 0)
