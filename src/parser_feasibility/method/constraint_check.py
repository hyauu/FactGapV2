"""Finite text-only count constraint baseline. No IDs, labels, files, oracle, model or network imports."""
import dataclasses,math,re,time
@dataclasses.dataclass(frozen=True)
class Abstention:
    reason:str
@dataclasses.dataclass(frozen=True)
class Constraint:
    subject:str
    property:str
    dimension:str
    unit:str
    lower:int
    upper:int
    lower_inclusive:bool
    upper_inclusive:bool
    subject_span:tuple
    property_span:tuple
    evidence_spans:tuple
    arithmetic_spans:tuple
@dataclasses.dataclass(frozen=True)
class GroundedFact:
    subject:str
    property:str
    dimension:str
    unit:str
    value:int
    subject_span:tuple
    property_span:tuple
    value_span:tuple
    evidence_span:tuple
def norm(s): return re.sub(r'\s+',' ',s.strip()).lower()
SUB=r'(?P<subject>[A-Za-z]+(?: [A-Za-z]+){0,5} record)'
PROP=r'(?P<property>[A-Za-z]+(?: [A-Za-z]+){0,2} count)'
VERB=r'(?:Select|Find|Return|Choose|Retrieve|Identify|Pick)'
ROOT_PATTERNS=[
    rf'{VERB} (?:the|a|an) {SUB} (?:whose |with (?:a |an )?|having (?:a |an )?|that has (?:a |an )?){PROP} (?P<condition>.+)\.',
    rf'A {SUB} is eligible exactly when its {PROP} (?P<condition>.+)\. Return an eligible record\.',
    rf'Return a qualifying {SUB}\. Qualification means that its {PROP} (?P<condition>.+)\.',
    rf'The requested {SUB} has a {PROP} (?P<condition>.+)\. Select that record\.',
    rf'For a {SUB}, apply both tests to its {PROP}: (?P<condition>.+)\. Select a record passing both\.',
    rf'Select a {SUB} passing both requirements on its {PROP}: (?P<condition>.+)\.'
]
INT=r'\d{1,10}'
EXPR=rf'(?:the sum of {INT} and {INT}|the difference of {INT} minus {INT}|the result of {INT} [+-] {INT}|\({INT} [+-] {INT}\)|{INT} [+-] {INT}|{INT})'
OP=r'(?:strictly greater than|strictly less than|no smaller than|no greater than|greater than|less than|strictly above|strictly below|at least|at most|more than|fewer than|above|below)'
SIDE=r'(?:\([12]\) )?(?:(?:it|the value) )?(?:is )?'
BOUND=re.compile(rf'{SIDE}(?P<op1>{OP}) (?P<expr1>{EXPR})(?: and | but |; ){SIDE}(?P<op2>{OP}) (?P<expr2>{EXPR})',re.I)
RANGE=re.compile(rf'(?:between (?P<a>{EXPR}) and (?P<b>{EXPR})|in the range from (?P<c>{EXPR}) to (?P<d>{EXPR})), (?P<low>including|excluding) the lower boundary and (?P<high>including|excluding) the upper boundary',re.I)
OPERATION={
    'strictly greater than':('lower',False),'greater than':('lower',False),'more than':('lower',False),'strictly above':('lower',False),'above':('lower',False),
    'at least':('lower',True),'no smaller than':('lower',True),
    'strictly less than':('upper',False),'less than':('upper',False),'fewer than':('upper',False),'strictly below':('upper',False),'below':('upper',False),
    'at most':('upper',True),'no greater than':('upper',True)
}
def exact_integer(text):
    t=norm(text)
    if re.fullmatch(INT,t): return int(t)
    patterns=[(rf'the sum of ({INT}) and ({INT})','+'),(rf'the difference of ({INT}) minus ({INT})','-'),(rf'(?:the result of )?\(?({INT}) ([+-]) ({INT})\)?',None)]
    for pat,op in patterns:
        m=re.fullmatch(pat,t)
        if m:
            a=int(m[1]);b=int(m[2] if op else m[3]);operation=op or m[2]
            return a+b if operation=='+' else a-b
    raise ValueError('Unsupported arithmetic')
def parse_query(query):
    if not isinstance(query,str) or len(query)>700: return Abstention('QUERY_TYPE_OR_LENGTH_UNSUPPORTED')
    match=None
    for pattern in ROOT_PATTERNS:
        match=re.fullmatch(pattern,query,re.I)
        if match:break
    if match is None:return Abstention('NO_COMPLETE_SUPPORTED_QUERY_GRAMMAR')
    condition=match['condition'];base=match.start('condition');m=BOUND.fullmatch(condition)
    evidence=[];arithmetic=[]
    if m:
        constraints={}
        for i in (1,2):
            role,inc=OPERATION[norm(m['op'+str(i)])]
            if role in constraints:return Abstention('MISSING_OPPOSITE_BOUND')
            key='expr'+str(i);text=m[key];value=exact_integer(text)
            constraints[role]=(value,inc)
            evidence.append((base+m.start('op'+str(i)),base+m.end(key)))
            if not re.fullmatch(INT,text):arithmetic.append((base+m.start(key),base+m.end(key),value))
        lower,li=constraints['lower'];upper,ui=constraints['upper']
    else:
        m=RANGE.fullmatch(condition)
        if not m:return Abstention('INCOMPLETE_OR_UNSUPPORTED_CONDITION')
        keys=('a','b') if m['a'] is not None else ('c','d')
        lower=exact_integer(m[keys[0]]);upper=exact_integer(m[keys[1]])
        li=norm(m['low'])=='including';ui=norm(m['high'])=='including'
        evidence.append((base,base+len(condition)))
        for key,value in zip(keys,(lower,upper)):
            if not re.fullmatch(INT,m[key]):arithmetic.append((base+m.start(key),base+m.end(key),value))
    if lower<=0 or upper<=0:return Abstention('OUTSIDE_POSITIVE_COUNT_SCOPE')
    if lower>upper:return Abstention('REVERSED_BOUNDS')
    return Constraint(match['subject'],match['property'],'count','individual',lower,upper,li,ui,match.span('subject'),match.span('property'),tuple(evidence),tuple(arithmetic))
FACT_PATTERNS=[
    rf'(?:The |A |An )?{SUB} (?:reports|records) {PROP}(?:: | of | as | is )(?P<value>{INT})\.',
    rf'(?:The |A |An )?{SUB} has (?:a |an )?{PROP} of (?P<value>{INT})\.',
    rf'For (?:the |a |an )?{SUB}, the {PROP} is (?P<value>{INT})\.',
    rf'The {PROP} of (?:the |a |an )?{SUB} is (?P<value>{INT})\.',
    rf"(?:The |A |An )?{SUB}'s {PROP} is (?P<value>{INT})\."
]
METADATA=re.compile(r'(?:Record ID: \d{1,10}|Model (?:number|ID): [A-Za-z0-9-]+|Logged (?:on|date:) \d{4}-\d{2}-\d{2})\.',re.I)
def parse_document(document):
    if not isinstance(document,str) or len(document)>900:return Abstention('DOCUMENT_TYPE_OR_LENGTH_UNSUPPORTED')
    facts=[]
    for sentence in re.finditer(r'\S.*?(?:\.(?=\s|$)|$)',document):
        text=sentence[0];m=None
        for pattern in FACT_PATTERNS:
            m=re.fullmatch(pattern,text,re.I)
            if m:break
        if m is None:
            if METADATA.fullmatch(text):continue
            return Abstention('UNSUPPORTED_OR_AMBIGUOUS_DOCUMENT_CLAUSE')
        value=int(m['value'])
        if value<=0:return Abstention('OUTSIDE_POSITIVE_COUNT_SCOPE')
        offset=sentence.start()
        span=lambda key:(offset+m.start(key),offset+m.end(key))
        facts.append(GroundedFact(m['subject'],m['property'],'count','individual',value,span('subject'),span('property'),span('value'),(sentence.start(),sentence.end())))
    return facts if facts else Abstention('NO_GROUNDED_FACT')
def check(constraint,facts):
    if isinstance(constraint,Abstention):return {'status':'UNKNOWN','reason':constraint.reason}
    if isinstance(facts,Abstention):return {'status':'UNKNOWN','reason':facts.reason}
    matched=[f for f in facts if norm(f.subject)==norm(constraint.subject) and norm(f.property)==norm(constraint.property)]
    if len(matched)!=1:return {'status':'UNKNOWN','reason':'SUBJECT_PROPERTY_NOT_UNIQUELY_GROUNDED'}
    f=matched[0]
    if (f.dimension,f.unit)!=(constraint.dimension,constraint.unit):return {'status':'UNKNOWN','reason':'UNIT_OR_DIMENSION_MISMATCH'}
    lower=f.value>=constraint.lower if constraint.lower_inclusive else f.value>constraint.lower
    upper=f.value<=constraint.upper if constraint.upper_inclusive else f.value<constraint.upper
    return {'status':'SATISFIES' if lower and upper else 'VIOLATES','reason':'EXACT_COUNT_INTERVAL_CHECK','fact':dataclasses.asdict(f)}
def semantic_key(c):
    return (norm(c.subject),norm(c.property),c.dimension,c.unit,c.lower,c.upper,c.lower_inclusive,c.upper_inclusive) if isinstance(c,Constraint) else None
def rewrite(query):
    started=time.perf_counter_ns();constraint=parse_query(query)
    if isinstance(constraint,Abstention):
        return {'query':query,'action':'ABSTAIN_REWRITE','reason':constraint.reason,'constraint':None,'latency_ns':time.perf_counter_ns()-started}
    result=query
    for begin,end,value in sorted(constraint.arithmetic_spans,reverse=True):result=result[:begin]+str(value)+result[end:]
    after=parse_query(result)
    if semantic_key(constraint)!=semantic_key(after):raise RuntimeError('M1_CONSTRAINT_PRESERVATION_FAILURE')
    return {'query':result,'action':'REWRITTEN' if result!=query else 'UNCHANGED_NORMAL_FORM','reason':'QUERY_ONLY_EXACT_ARITHMETIC','constraint':dataclasses.asdict(constraint),'latency_ns':time.perf_counter_ns()-started}
def rerank(query,candidates,base_scores):
    if len(candidates)!=2 or len(base_scores)!=2 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in base_scores):raise ValueError('Two finite original scores required')
    started=time.perf_counter_ns();constraint=parse_query(query)
    documents=[parse_document(s) for s in candidates]
    statuses=[check(constraint,facts) for facts in documents]
    safe=sorted(x['status'] for x in statuses)==['SATISFIES','VIOLATES']
    keys=[(1 if x['status']=='SATISFIES' else 0,float(s)) if safe else (0,float(s)) for x,s in zip(statuses,base_scores)]
    relation='A' if keys[0]>keys[1] else 'B' if keys[1]>keys[0] else 'TIE'
    return {'constraint':dataclasses.asdict(constraint) if isinstance(constraint,Constraint) else None,'query_abstention':constraint.reason if isinstance(constraint,Abstention) else None,
            'documents':[dataclasses.asdict(x) if isinstance(x,Abstention) else [dataclasses.asdict(f) for f in x] for x in documents],
            'constraint_status':statuses,'ranking_key':keys,'base_score':list(base_scores),'choice':relation,'override_rule_applied':safe,
            'reason':'UNIQUE_SAFE_SATISFIER' if safe else 'NO_SAFE_OVERRIDE','latency_ns':time.perf_counter_ns()-started}
