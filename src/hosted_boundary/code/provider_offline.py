import json,hashlib,math,pathlib
R=pathlib.Path(__file__).resolve().parents[1]
MODELS={'openai': 'gpt-5.6-sol', 'anthropic': 'claude-sonnet-5', 'google': 'gemini-3.8-flash'}
RATES={'openai': (4.0, 20.0), 'anthropic': (2.0, 10.0), 'google': (0.75, 3.75)}

def read(p): return json.loads((R/p).read_text(encoding='utf-8-sig'))

def jsbytes(v): return json.dumps(v,ensure_ascii=False,separators=(',',':')).encode('utf-8')

def hashbytes(b): return hashlib.sha256(b).hexdigest()

def body(provider,item):
    task=item['task'];model=MODELS[provider];prompt=PROMPTS[task];user=item['user_content'];schema=SCHEMAS[task]
    if provider=='openai':
        return {'model':model,'instructions':prompt,'input':[{'role':'user','content':user}],'reasoning':{'effort':'medium'},'max_output_tokens':CAPS[provider],'text':{'format':{'type':'json_schema','name':'constraint' if task=='A' else 'selection','schema':schema,'strict':True}},'tools':[],'store':False,'background':False,'service_tier':'default','truncation':'disabled'}
    if provider=='anthropic':
        return {'model':model,'system':prompt,'messages':[{'role':'user','content':user}],'max_tokens':CAPS[provider],'thinking':{'type':'adaptive','display':'omitted'},'output_config':{'effort':'high','format':{'type':'json_schema','schema':schema}},'tools':[]}
    return {'systemInstruction':{'parts':[{'text':prompt}]},'contents':[{'role':'user','parts':[{'text':user}]}],'generationConfig':{'maxOutputTokens':CAPS[provider],'responseMimeType':'application/json','responseJsonSchema':schema,'thinkingConfig':{'thinkingLevel':'medium','includeThoughts':False}}}

def parse(task,value):
    if not isinstance(value,dict): return False
    if task=='B': return set(value)=={'choice'} and value['choice'] in ('A','B','TIE','ABSTAIN')
    if set(value)!=set(SCHEMAS['A']['required']) or type(value['valid']) is not bool: return False
    for key in ('lower_bound','upper_bound'):
        x=value[key]
        if x is not None and (type(x) not in (int,float) or not math.isfinite(x)): return False
    for key in ('lower_inclusive','upper_inclusive'):
        if value[key] is not None and type(value[key]) is not bool: return False
    if not value['valid'] and any(value[k] is not None for k in value if k!='valid'): return False
    return True

def extract(provider,response):
    if provider=='openai':
        text=''.join(c.get('text','') for o in response.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
        u=response.get('usage',{});it=u.get('input_tokens');ot=u.get('output_tokens');cached=u.get('input_tokens_details',{}).get('cached_tokens',0);thinking=u.get('output_tokens_details',{}).get('reasoning_tokens')
        version=response.get('model');finish=response.get('status');rid=response.get('id')
    elif provider=='anthropic':
        text=''.join(c.get('text','') for c in response.get('content',[]) if c.get('type')=='text')
        u=response.get('usage',{});it=u.get('input_tokens');ot=u.get('output_tokens');cached=u.get('cache_read_input_tokens',0);thinking=None
        version=response.get('model');finish=response.get('stop_reason');rid=response.get('id')
    else:
        cs=response.get('candidates',[])
        text=''.join(p.get('text','') for c in cs for p in c.get('content',{}).get('parts',[]) if not p.get('thought'))
        u=response.get('usageMetadata',{});it=u.get('promptTokenCount');thinking=u.get('thoughtsTokenCount',0);cached=u.get('cachedContentTokenCount',0)
        visible=u.get('candidatesTokenCount');ot=(visible+thinking) if visible is not None else (u['totalTokenCount']-it if it is not None and 'totalTokenCount' in u else None)
        version=response.get('modelVersion');finish=cs[0].get('finishReason') if cs else None;rid=response.get('responseId')
    return text,it,ot,cached,thinking,version,finish,rid
