from __future__ import annotations
from typing import List, Tuple
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def math_run(text: str):
    r = OxmlElement('m:r')
    r_pr = OxmlElement('m:rPr')
    sty = OxmlElement('m:sty')
    sty.set(qn('m:val'), 'p')
    r_pr.append(sty)
    r.append(r_pr)
    t = OxmlElement('m:t')
    t.text = text
    r.append(t)
    return r

def split_args(text: str) -> List[str]:
    args=[]; depth=0; start=0
    for i,ch in enumerate(text):
        if ch=='(': depth+=1
        elif ch==')': depth-=1
        elif ch==',' and depth==0:
            args.append(text[start:i].strip()); start=i+1
    args.append(text[start:].strip())
    return args

def matching_paren(text: str,start: int)->int:
    depth=0
    for i in range(start,len(text)):
        if text[i]=='(': depth+=1
        elif text[i]==')':
            depth-=1
            if depth==0: return i
    return len(text)-1

def make_fraction(num: str,den: str):
    f=OxmlElement('m:f'); n=OxmlElement('m:num'); d=OxmlElement('m:den')
    for x in parse_math(num): n.append(x)
    for x in parse_math(den): d.append(x)
    f.extend([n,d]); return f

def make_radical(expr: str):
    r=OxmlElement('m:rad'); pr=OxmlElement('m:radPr'); hide=OxmlElement('m:degHide'); hide.set(qn('m:val'),'1')
    pr.append(hide); r.append(pr); r.append(OxmlElement('m:deg')); e=OxmlElement('m:e')
    for x in parse_math(expr): e.append(x)
    r.append(e); return r

def make_script(base: List,sub: str|None=None,sup: str|None=None):
    if sub is not None and sup is not None:
        el=OxmlElement('m:sSubSup'); e=OxmlElement('m:e'); se=OxmlElement('m:sub'); pe=OxmlElement('m:sup')
        for x in base: e.append(x)
        for x in parse_math(sub): se.append(x)
        for x in parse_math(sup): pe.append(x)
        el.extend([e,se,pe]); return el
    el=OxmlElement('m:sSub' if sub is not None else 'm:sSup'); e=OxmlElement('m:e')
    for x in base: e.append(x)
    s=OxmlElement('m:sub' if sub is not None else 'm:sup')
    for x in parse_math(sub if sub is not None else sup or ''): s.append(x)
    el.extend([e,s]); return el

def make_integral(lower: str,upper: str,expr: str,differential: str):
    n=OxmlElement('m:nary'); pr=OxmlElement('m:naryPr'); ch=OxmlElement('m:chr'); ch.set(qn('m:val'),'∫')
    loc=OxmlElement('m:limLoc'); loc.set(qn('m:val'),'subSup'); grow=OxmlElement('m:grow'); grow.set(qn('m:val'),'1')
    pr.extend([ch,loc,grow]); n.append(pr); sub=OxmlElement('m:sub'); sup=OxmlElement('m:sup'); e=OxmlElement('m:e')
    for x in parse_math(lower): sub.append(x)
    for x in parse_math(upper): sup.append(x)
    for x in parse_math(expr): e.append(x)
    if differential: e.append(math_run(' '+differential))
    n.extend([sub,sup,e]); return n

def make_limit(variable: str,target: str,expr: str):
    l=OxmlElement('m:limLow'); e=OxmlElement('m:e'); e.append(math_run('lim')); low=OxmlElement('m:lim')
    for x in parse_math(f'{variable}→{target}'): low.append(x)
    l.extend([e,low]); return [l,math_run(' ')]+parse_math(expr)

def read_script(text: str,i: int)->Tuple[str,int]:
    if i>=len(text): return '',i
    if text[i]=='(':
        end=matching_paren(text,i); return text[i+1:end],end+1
    if text[i]=='{':
        depth=0
        for j in range(i,len(text)):
            if text[j]=='{': depth+=1
            elif text[j]=='}':
                depth-=1
                if depth==0: return text[i+1:j],j+1
    j=i
    while j<len(text) and (text[j].isalnum() or text[j] in "'′∞πθ"): j+=1
    return text[i:j] or text[i:i+1],max(j,i+1)

def _group(nodes: List):
    b=OxmlElement('m:box'); e=OxmlElement('m:e')
    for x in nodes: e.append(x)
    b.append(e); return b

def parse_math(expression: str)->List:
    text=expression.strip().replace('**','^').replace("f'",'f′').replace('<=','≤').replace('>=','≥').replace('!=','≠').replace('->','→')
    nodes=[]; i=0
    while i<len(text):
        matched=False
        for name in ('sqrt','frac','int','lim','sum'):
            prefix=name+'('
            if text.startswith(prefix,i):
                end=matching_paren(text,i+len(name)); args=split_args(text[i+len(prefix):end])
                if name=='sqrt' and args: nodes.append(make_radical(args[0]))
                elif name=='frac' and len(args)>=2: nodes.append(make_fraction(args[0],args[1]))
                elif name=='int' and len(args)>=3: nodes.append(make_integral(args[0],args[1],args[2],args[3] if len(args)>3 else 'dx'))
                elif name=='lim' and len(args)>=3: nodes.extend(make_limit(args[0],args[1],args[2]))
                elif name=='sum' and len(args)>=3:
                    n=OxmlElement('m:nary'); pr=OxmlElement('m:naryPr'); ch=OxmlElement('m:chr'); ch.set(qn('m:val'),'∑'); loc=OxmlElement('m:limLoc'); loc.set(qn('m:val'),'subSup'); pr.extend([ch,loc]); n.append(pr)
                    sub=OxmlElement('m:sub'); sup=OxmlElement('m:sup'); e=OxmlElement('m:e')
                    for x in parse_math(args[0]): sub.append(x)
                    for x in parse_math(args[1]): sup.append(x)
                    for x in parse_math(args[2]): e.append(x)
                    n.extend([sub,sup,e]); nodes.append(n)
                i=end+1; matched=True; break
        if matched: continue
        ch=text[i]
        if ch=='(':
            end=matching_paren(text,i); base=[math_run('(')]+parse_math(text[i+1:end])+[math_run(')')]; i=end+1
        elif ch.isalpha() or ch.isdigit() or ch in 'π∞θ′':
            j=i+1
            while j<len(text) and (text[j].isalnum() or text[j] in "'′π∞θ"): j+=1
            base=[math_run(text[i:j])]; i=j
        else:
            nodes.append(math_run({'-':'−','*':'×'}.get(ch,ch))); i+=1; continue
        sub=sup=None
        while i<len(text) and text[i] in '^_':
            kind=text[i]; value,i=read_script(text,i+1)
            if kind=='^': sup=value
            else: sub=value
        nodes.append(make_script(base,sub,sup) if sub is not None or sup is not None else base[0] if len(base)==1 else _group(base))
    return nodes

def build_equation(expression: str):
    omath=OxmlElement('m:oMath')
    for node in parse_math(expression): omath.append(node)
    return omath
