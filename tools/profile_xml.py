"""Perfilado exploratorio del XML de Control-M (solo lectura)."""
import sys, collections
import xml.etree.ElementTree as ET

path = sys.argv[1]
root = ET.parse(path).getroot()
tags = collections.Counter()
attrs = collections.defaultdict(collections.Counter)
parent_child = collections.Counter()
def walk(e, parent=None):
    tags[e.tag] += 1
    if parent is not None:
        parent_child[(parent.tag, e.tag)] += 1
    for k in e.attrib:
        attrs[e.tag][k] += 1
    for c in e:
        walk(c, e)
walk(root)
print("== TAGS"); [print(f"  {t}: {n}") for t, n in tags.most_common()]
print("== PARENT->CHILD"); [print(f"  {p}->{c}: {n}") for (p, c), n in parent_child.most_common()]
for t in tags:
    print(f"== ATTRS of {t}")
    print("  " + ", ".join(f"{k}({n})" for k, n in attrs[t].most_common()))

def vals(tag, attr, top=60):
    c = collections.Counter(e.get(attr) for e in root.iter(tag) if attr in e.attrib)
    print(f"== {tag}.{attr} distinct={len(c)}")
    for v, n in c.most_common(top):
        print(f"  {v!r}: {n}")

for a in ["DAYS","WEEKDAYS","DAYSCAL","WEEKSCAL","CONFCAL","DAYS_AND_OR","SHIFT","SHIFTNUM","RULE_BASED_CALENDAR_RELATIONSHIP",
          "TASKTYPE","CYCLIC","TIMEFROM","TIMETO","MAXWAIT","MAXRERUN","RETRO","DATE","DATEFROM","DATETO","ACTIVE_FROM","ACTIVE_TILL",
          "APPLICATION","SUB_APPLICATION","INTERVAL","CYCLIC_TYPE","CONFIRM","CRITICAL","APPL_TYPE","NODEID","PRIORITY","IND_CYCLIC","TIMEZONE","MAXDAYS","MAXRUNS"]:
    vals("JOB", a, 40)
for m in ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]:
    vals("JOB", m, 5)
for t in ["INCOND","OUTCOND","DOCOND"]:
    vals(t, "ODATE"); vals(t, "AND_OR"); vals(t, "SIGN")
vals("ON","CODE"); vals("ON","STMT"); vals("ON","AND_OR")
for t in tags:
    if t not in ("JOB","INCOND","OUTCOND","DOCOND","ON","DEFTABLE"):
        for a in attrs[t]:
            if a not in ("NAME","VALUE","MESSAGE","DEST","DESCRIPTION"):
                vals(t, a, 15)
vals("FOLDER","FOLDER_NAME",100)
