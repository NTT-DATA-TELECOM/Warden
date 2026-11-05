import sys, collections, re
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
jobs = []
for f in root.iter("FOLDER"):
    for j in f.iter("JOB"):
        jobs.append((f, j))
print("folders:", [(f.get("FOLDER_NAME"), f.get("FOLDER_ORDER_METHOD"), len(f.findall("JOB"))) for f in root.iter("FOLDER")])
# schedule combos
combo = collections.Counter()
for f, j in jobs:
    combo[(j.get("DAYS") is not None, j.get("WEEKDAYS") is not None, j.get("DAYS_AND_OR"), j.get("DATE") is not None)] += 1
print("== (has DAYS, has WEEKDAYS, DAYS_AND_OR, has DATE):", combo)
for f, j in jobs:
    if j.get("DAYS_AND_OR") == "A" or j.get("DATE") or j.get("ACTIVE_FROM") or j.get("ACTIVE_TILL") or j.get("WEEKDAYS") == "D6W1" or j.get("CONFIRM") == "1":
        print("  special:", f.get("FOLDER_NAME"), j.get("JOBNAME"), {k: j.get(k) for k in ["DAYS","WEEKDAYS","DAYS_AND_OR","DATE","ACTIVE_FROM","ACTIVE_TILL","CONFIRM"] if j.get(k)})
# month patterns
mp = collections.Counter("".join(j.get(m,"?") for m in "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()) for f, j in jobs)
print("== month patterns", mp)
# unique jobnames
names = collections.Counter(j.get("JOBNAME") for f, j in jobs)
print("== duplicated JOBNAME:", {n: c for n, c in names.items() if c > 1})
isn = collections.Counter((f.get("FOLDER_NAME"), j.get("JOBISN")) for f, j in jobs)
print("== duplicated JOBISN in folder:", sum(1 for c in isn.values() if c > 1))
# conditions
prod = collections.defaultdict(set); cons = collections.defaultdict(set); dels = collections.defaultdict(set); doc = collections.defaultdict(set)
for f, j in jobs:
    n = j.get("JOBNAME")
    for c in j.findall("INCOND"): cons[c.get("NAME")].add(n)
    for c in j.findall("OUTCOND"):
        (prod if c.get("SIGN") == "+" else dels)[c.get("NAME")].add(n)
    for on in j.findall("ON"):
        for d in on.findall("DOCOND"):
            if d.get("SIGN") == "+": doc[d.get("NAME")].add((n, on.get("CODE")))
orph = [c for c in cons if c not in prod and c not in doc]
pref = collections.Counter(re.split(r"[-_]", c)[0] for c in orph)
print("== INCOND conds:", len(cons), "producers:", len(prod), "orphans (no + OUTCOND or DOCOND):", len(orph))
print("  orphan prefixes:", pref.most_common(30))
for c in sorted(orph)[:400]:
    print("   ORPH", c, sorted(cons[c])[:3])
only_doc = [c for c in cons if c not in prod and c in doc]
print("== consumed conds produced only by DOCOND:", len(only_doc))
for c in only_doc[:40]: print("   ", c, doc[c])
no_cons = [c for c in prod if c not in cons]
print("== OUTCOND+ without consumer:", len(no_cons), collections.Counter(re.split(r"[-_]", c)[0] for c in no_cons).most_common(15))
allpref = collections.Counter(re.split(r"[-_]", c)[0] for c in cons)
print("== all INCOND prefixes:", allpref.most_common(30))
# multiple producers
mp = {c: p for c, p in prod.items() if len(p) > 1 and c in cons}
print("== consumed conds with >1 producer:", len(mp))
for c, p in list(mp.items())[:15]: print("   ", c, sorted(p))
# OR groups
for f, j in jobs:
    ors = [c.get("NAME") for c in j.findall("INCOND") if c.get("AND_OR") == "O"]
    if ors: print("== OR incond", j.get("JOBNAME"), [(c.get("NAME"), c.get("AND_OR")) for c in j.findall("INCOND")])
# PREV/NEXT
for t in ("INCOND", "OUTCOND", "DOCOND"):
    for f, j in jobs:
        for c in j.iter(t):
            if c.get("ODATE") == "NEXT" and t != "OUTCOND":
                print("== NEXT", t, j.get("JOBNAME"), c.get("NAME"), c.get("SIGN"))
# SIGN - on condition not in own INCOND
weird = 0; ex = []
for f, j in jobs:
    ins = {c.get("NAME") for c in j.findall("INCOND")}
    for c in j.findall("OUTCOND"):
        if c.get("SIGN") == "-" and c.get("NAME") not in ins:
            weird += 1; ex.append((j.get("JOBNAME"), c.get("NAME"), c.get("ODATE")))
print("== OUTCOND - not among own INCONDs:", weird)
for e in ex[:30]: print("   ", e)
# jobs consuming but whose own + and - same cond
for f, j in jobs:
    p = {(c.get("NAME")) for c in j.findall("OUTCOND") if c.get("SIGN") == "+"}
    m = {(c.get("NAME")) for c in j.findall("OUTCOND") if c.get("SIGN") == "-"}
    if p & m: print("== same cond +/-:", j.get("JOBNAME"), p & m)
# DOFORCEJOB targets
print("== DOFORCEJOB:")
for f, j in jobs:
    for on in j.findall("ON"):
        for d in on.findall("DOFORCEJOB"):
            print("   ", j.get("JOBNAME"), on.get("CODE"), "->", d.get("TABLE_NAME"), d.get("NAME"))
# ON codes non standard
for f, j in jobs:
    for on in j.findall("ON"):
        if on.get("CODE") not in ("OK", "NOTOK"):
            print("== ON", j.get("JOBNAME"), on.get("STMT"), on.get("CODE"), on.get("AND_OR"), [(x.tag, x.get("NAME") or x.get("ACTION")) for x in on])
# cyclic sample
for f, j in jobs[:0]: pass
cyc = [(j.get("JOBNAME"), j.get("INTERVAL"), j.get("CYCLIC_TYPE"), j.get("CYCLIC_TIMES_SEQUENCE"), j.get("CYCLIC_INTERVAL_SEQUENCE"), j.get("TIMEFROM"), j.get("TIMETO")) for f, j in jobs if j.get("CYCLIC") == "1"]
print("== cyclic sample:", cyc[:10])
print("== END_FOLDER values:", collections.Counter(j.get("END_FOLDER") for f, j in jobs))
print("== CONTROL:", [(j.get("JOBNAME"), c.attrib) for f, j in jobs for c in j.findall("CONTROL")])
print("== VARIABLE names:", collections.Counter(v.get("NAME") for v in root.iter("VARIABLE")).most_common(20))
# no-days-no-weekdays jobs, are they forced?
forced = {d.get("NAME") for d in root.iter("DOFORCEJOB")}
nod = [(f.get("FOLDER_NAME"), j.get("JOBNAME")) for f, j in jobs if not j.get("DAYS") and not j.get("WEEKDAYS") and not j.get("DATE")]
print("== jobs with no DAYS/WEEKDAYS/DATE:", len(nod), "forced by DOFORCEJOB:", sum(1 for _, n in nod if n in forced))
print("   by folder:", collections.Counter(f for f, _ in nod))
# TIMEFROM>TIMETO
for f, j in jobs:
    tf, tt = j.get("TIMEFROM"), j.get("TIMETO")
    if tf and tt and tt != ">" and tf > tt: print("== TIMEFROM>TIMETO (crosses midnight?)", j.get("JOBNAME"), tf, tt)
    if tt and not tf: print("== TIMETO w/o TIMEFROM", j.get("JOBNAME"), tt)
