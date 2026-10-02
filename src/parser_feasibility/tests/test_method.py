"""Eight query toy fixtures; candidate variants exercise protected fallback. No research labels or corpus."""
import copy,dataclasses,inspect,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'method'))
from constraint_check import *
def main():
    q1='Select the depot audit record whose parcel count is at least 10 and strictly below the sum of 12 and 3.'
    a='The depot audit record reports parcel count: 11. Record ID: 9876. Logged on 2025-02-03.'
    b='The depot audit record reports parcel count: 15. Model ID: K77.'
    d=rerank(q1,[a,b],[0,2]);assert d['choice']=='A' and d['override_rule_applied']
    assert d['constraint_status'][0]['fact']['value']==11
    r=rewrite(q1);assert r['query']==q1.replace('the sum of 12 and 3','15')
    assert semantic_key(parse_query(q1))==semantic_key(parse_query(r['query']))
    c=parse_query(q1);parts=[];last=0
    for begin,end,v in sorted(c.arithmetic_spans):parts.extend([q1[last:begin],str(v)]);last=end
    parts.append(q1[last:]);assert ''.join(parts)==r['query']
    swapped=rerank(q1,[b,a],[2,0]);assert swapped['choice']=='B' and list(reversed(swapped['constraint_status']))==d['constraint_status']
    metadata={'id':'old','private_gold':'B','query':q1,'candidates':[a,b],'scores':[0,2]}
    def project(x):return rerank(x['query'],x['candidates'],x['scores'])
    mutated=copy.deepcopy(metadata);mutated.update(id='other',private_gold='A',split='eval',template='T999')
    x=project(metadata);y=project(mutated);x.pop('latency_ns');y.pop('latency_ns');assert x==y
    assert tuple(inspect.signature(rerank).parameters)==('query','candidates','base_scores')
    q2='Find the depot audit record with a parcel count greater than 5 and at most 5.'
    c=parse_query(q2);assert isinstance(c,Constraint)
    assert check(c,parse_document('The depot audit record reports parcel count: 5.'))['status']=='VIOLATES'
    q3='Find the depot audit record with a parcel count greater than 5 and at most 10.'
    c=parse_query(q3)
    assert check(c,parse_document('The depot audit record reports parcel count: 5.'))['status']=='VIOLATES'
    assert check(c,parse_document('The depot audit record reports parcel count: 10.'))['status']=='SATISFIES'
    for text in ('The yard audit record reports parcel count: 7.','The depot audit record reports box count: 7.','The depot audit record reports parcel count: 7 kg.','The depot audit record does not report parcel count: 7.'):
        out=rerank(q3,[text,b],[4,1]);assert not out['override_rule_applied'] and out['choice']=='A' and out['constraint_status'][0]['status']=='UNKNOWN'
    q4='Find the depot audit record for model K77.'
    assert isinstance(parse_query(q4),Abstention) and rewrite(q4)['query']==q4
    q5='Find the depot audit record with a parcel count at least 5 and less than 10 and status approved.'
    assert isinstance(parse_query(q5),Abstention) and rewrite(q5)['action']=='ABSTAIN_REWRITE'
    q6='Select the depot audit record whose parcel count is at least 5 and strictly below 10.'
    aa='The depot audit record reports parcel count: 6.';bb='The depot audit record reports parcel count: 8.'
    for scores in ([1,3],[2,2]):
        out=rerank(q6,[aa,bb],scores);assert not out['override_rule_applied'] and out['choice']==('B' if scores[0]<scores[1] else 'TIE')
    q7='Find the depot audit record with a parcel count no smaller than 20 but less than 30.'
    out=rerank(q7,[aa,bb],[2,2]);assert out['choice']=='TIE' and not out['override_rule_applied']
    assert [x['status'] for x in out['constraint_status']]==['VIOLATES','VIOLATES']
    q8='A depot audit record is eligible exactly when its parcel count is greater than the difference of 14 minus 4 and at most 19. Return an eligible record.'
    c=parse_query(q8);assert (c.lower,c.upper,c.lower_inclusive,c.upper_inclusive)==(10,19,False,True)
    assert rewrite(q8)['query']==q8.replace('the difference of 14 minus 4','10')
    try:exact_integer('__import__(os)');raise AssertionError('unsafe expression accepted')
    except ValueError:pass
    print(json.dumps({'status':'PASS','query_toy_fixtures':8,'metadata_independence':True,'candidate_order_mapping':True,'irrelevant_numbers_not_count_values':True,'subject_property_unit_negation_fallback':True,'boundary_and_exact_arithmetic':True,'both_or_neither_satisfying_preserves_base_and_tie':True,'M1_preserves_full_query_outside_arithmetic_spans':True}))
if __name__=='__main__':main()
