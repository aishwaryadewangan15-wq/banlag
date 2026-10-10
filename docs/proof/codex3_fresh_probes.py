"""Read-only final acceptance probes. All mutations occur in the isolated audit directory."""
import sys,os,json,hashlib,copy,datetime as dt
from pathlib import Path
from unittest.mock import patch
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(Path.cwd()))
A=Path.cwd().parent
os.environ['BANLAG_KEY_DIR']=str(A/'absent-real-key')
AUTH=os.path.normcase(os.path.abspath(r'D:\HACKATHON\BANLAG'))
def protected(p):
 if not isinstance(p,(str,bytes,os.PathLike)):return False
 p=os.path.normcase(os.path.abspath(os.fsdecode(p)))
 return p==AUTH or p.startswith(AUTH+os.sep)
def guard(e,a):
 if e=='open':
  p,m,f=a
  if ((isinstance(m,str) and any(c in m for c in 'wax+')) or (isinstance(f,int) and f&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))) and protected(p):raise RuntimeError('AUTHORITATIVE WRITE BLOCKED')
 elif e in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate') and protected(a[0]):raise RuntimeError('AUTHORITATIVE MUTATION BLOCKED')
 elif e in ('os.rename','os.link','os.symlink') and any(protected(p) for p in a[:2]):raise RuntimeError('AUTHORITATIVE MUTATION BLOCKED')
 elif e=='socket.connect' and a[1][0] not in ('127.0.0.1','localhost','::1'):raise RuntimeError('OUTBOUND NETWORK BLOCKED')
 elif e=='socket.getaddrinfo' and a[0] not in ('127.0.0.1','localhost','::1',None):raise RuntimeError('OUTBOUND DNS BLOCKED')
 elif e=='subprocess.Popen':raise RuntimeError('SUBPROCESS BLOCKED')
sys.addaudithook(guard)
from banlag import corpus,collector,capture_store
from banlag.engine import evaluate,evaluate_run
from banlag.citations import reference_formulation,relation_to
from banlag.legal import entry_by_id
from banlag.claims import restriction_statements
ING=['dicyclomine','paracetamol','clidinium bromide']; F08=entry_by_id('F08')
X='Dicyclomine, Paracetamol and Clidinium Bromide'
LEAD=X+' are used to treat abdominal cramps.'
BAN='The Central Government has prohibited the fixed dose combination of '+X+' for human use.'
rows=[]
def rec(name,expected,passed,**data):
 rows.append({'name':name,'expected':expected,'outcome':'PASS' if passed else 'FAIL',**data})
def payload(text,org=None,refs=None,blocks=None):
 return {'source_kind':'SYNTHETIC_TEST','query':'q','ingredients':ING,'google':{'search_parameters':{'q':'q'},'search_metadata':{'id':'S1'},'organic_results':org or [],'ai_overview':{'text_blocks':blocks or [{'type':'paragraph','snippet':text,'reference_indexes':[0] if refs else []}],'references':refs or []}}}
def organic(s,url='https://news.example.invalid/r'):return [{'position':1,'title':'Regulatory report','link':url,'snippet':s}]
def answer(name,text,want,org=None,refs=None,snaps=None,blocks=None):
 try:
  r=evaluate(payload(text,org,refs,blocks),verified_snapshots=snaps)
  a=r['answers'][0];label=a['prereg_label'];tier=r['evidence_tier']
  ok=(label in ('B','F') and tier==0) if want=='ABSTAIN' else label!='D' if want=='NOT_D' else (label,tier)==want
  rec(name,str(want),ok,text=text,organic=org,label=label,tier=tier,subject=a['analysis']['subject'],restrictions=[dict(text=c['text'],**c['restriction']) for c in a['analysis']['claims'] if 'restriction' in c],tier2_hits=a['tier2_hits'],tier3_hits=a['tier3_hits'],coherence=a['citation_coherence'])
 except Exception as e:rec(name,str(want),False,text=text,error=type(e).__name__,message=str(e))
# Composition additions: clear subject links, ambiguous subject links, and ordinary controls.
for i,tail in enumerate([
 'Omeprazole is also in it.',
 'This medicine has omeprazole as another active ingredient.',
 'A fourth component, omeprazole, is included.',
 'Its fourth active ingredient is omeprazole.',
 'The same tablet has activated charcoal as its fourth ingredient.',
 'Each tablet additionally comprises light magnesium oxide.',
 'The active ingredients are the three above plus rifaximin.',
 'It contains a fourth active ingredient: omeprazole.',
 'The formulation additionally contains omeprazole.',
 'It also contains omeprazole.',
 'The medicine contains paracetamol and omeprazole.',
 'This medicine contains dicyclomine and omeprazole.'
]):answer('composition_addition_'+str(i),LEAD+' '+tail,'ABSTAIN')
for i,text in enumerate([
 LEAD+' Omeprazole is a separate medicine used for acid reflux.',
 LEAD+' The three ingredients are combined in one tablet.',
 LEAD+' Dicyclomine relaxes muscles; paracetamol relieves pain.',
 LEAD+' Each tablet contains Dicyclomine 10 mg, Paracetamol 325 mg and Clidinium Bromide 2.5 mg.',
 X+' (an antispasmodic combination) are used to treat abdominal cramps.',
 'Dicyclomine 10 mg + Paracetamol 325 mg + Clidinium Bromide 2.5 mg tablets are commonly prescribed.',
 LEAD+' A different product contains omeprazole.',
 LEAD+' Omeprazole is also discussed in the article, but it is not an ingredient in this formulation.'
]):answer('composition_positive_'+str(i),text,('E',1))
answer('composition_ambiguous_pronoun',LEAD+' Another medicine is used for reflux. It also contains omeprazole.','ABSTAIN')
# Entity must bind to the SAME restriction predicate as jurisdiction, rather than the sentence union.
for i,s in enumerate([
 X+' is banned in Canada, but omeprazole is prohibited in India.',
 X+' is banned in Canada, whereas rifaximin is prohibited in India.',
 X+' is prescribed for cramps, while omeprazole is prohibited in India.',
 'This combination is banned in Canada, but omeprazole is prohibited in India.',
 'No authority has prohibited this combination in India.',
 'It is not true that this combination is banned in India.',
 'The regulator denies that this combination is prohibited in India.',
 'This combination is banned in India if clinically inappropriate.',
 'This combination is banned in India on condition that a fourth active is added.',
 'This combination is banned in India, according to an uncorroborated report.'
]):answer('restriction_negative_'+str(i),LEAD+' '+s,'NOT_D')
for i,s in enumerate([
 'This combination is prohibited in India and is not prohibited in Canada.',
 'This combination is prohibited in India. A ban on omeprazole was lifted.',
 'This combination is prohibited in India. Omeprazole is not banned in India.',
 'This combination was banned in India in 2016. That ban was lifted. This combination is now prohibited again in India.',
 'This combination is not only prohibited in India; manufacture, sale and distribution are banned.'
]):answer('restriction_positive_'+str(i),LEAD+' '+s,('D',0))
# Fresh T2/T3 cases: compare against exact same positive control.
legal_cases=[
 ('wrong_entity_india',X+' is banned in Canada, but omeprazole is prohibited in India.',1),
 ('conditional_scope',X+' is banned in India if clinically inappropriate.',1),
 ('cross_sentence_addition',X+' is prohibited in India. Omeprazole is also in it.',1),
 ('known_cross_sentence_addition',X+' is prohibited in India. This formulation also contains Chlordiazepoxide.',1),
 ('historical_then_current','In 2016, '+X+' was banned in India. That prohibition was lifted. In June 2026, '+X+' was prohibited again in India.',2),
 ('current_plus_unrelated_lift',BAN+' A ban on omeprazole was lifted.',2),
 ('current_control',BAN,2),
 ('foreign_unknown_place',X+' is banned in Bhutan and sold in India.',1)
]
for name,s,want in legal_cases:
 answer('tier2_'+name,LEAD,('E',want),org=organic(s))
 url='https://ref.example.invalid/p'
 answer('tier3_'+name,LEAD,('E',3 if want==2 else 1),refs=[{'index':0,'link':url}],snaps=[{'url':url,'text':s,'sha256':'0'*64}])
# Citation views and per-claim binding.
def cite(name,ref,want):
 try:
  f=reference_formulation(dict(ref,index=0));rel=relation_to(set(ING),f)
  rec(name,want,rel in want if isinstance(want,list) else rel==want,ref=ref,formulation=f,relation=rel)
 except Exception as e:rec(name,str(want),False,error=type(e).__name__,message=str(e))
T='Dicyclomine + Paracetamol + Clidinium Bromide Tablets'
cite('citation_extra_later_sentence',{'title':T,'snippet':LEAD+' Omeprazole is also in it.','link':'https://x.invalid/p'},['UNRECOGNISED_COMPONENT','CONFLICTING_VIEWS','MULTIPLE_FORMULATIONS'])
cite('citation_known_extra_later_sentence',{'title':T,'snippet':LEAD+' This formulation also contains Chlordiazepoxide.','link':'https://x.invalid/p'},['CONFLICTING_VIEWS','MULTIPLE_FORMULATIONS'])
cite('citation_title_strengths',{'title':'Dicyclomine 10mg / Paracetamol 325mg / Clidinium Bromide 2.5mg','snippet':'','link':'https://x.invalid/p'},'EXACT')
cite('citation_exact_vs_url_unknown',{'title':T,'snippet':'','link':'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-activated-charcoal'},['UNRECOGNISED_COMPONENT','CONFLICTING_VIEWS'])
cite('citation_nested_parenthetical_extra',{'title':T,'snippet':X+' (contains a fourth active ingredient: omeprazole).','link':'https://x.invalid/p'},['UNRECOGNISED_COMPONENT','CONFLICTING_VIEWS','MULTIPLE_FORMULATIONS'])
cite('citation_consistent_truncated',{'title':T,'snippet':X+' ...','link':'https://x.invalid/p'},'EXACT')
# Duplicate index ambiguity: whether the result silently resolves the conflicting reference as exact.
refs=[{'index':0,'title':T,'link':'https://x.invalid/one'},{'index':0,'title':'Dicyclomine + Paracetamol + Chlordiazepoxide','link':'https://x.invalid/two'}]
for order in [refs,refs[::-1]]:
 r=evaluate(payload(LEAD,refs=order));coh=r['answers'][0]['citation_coherence']
 rec('citation_duplicate_index_'+order[0]['link'],'duplicate ambiguity visible',coh['status']=='NO_MISMATCH_DETECTED_PARTIAL_COVERAGE' or any(x.get('conflict') for x in coh['references']),refs=order,coherence=coh)
# Composition additions remain blockers after authentication by a dummy local key.
from tests.test_capture_store import PLAN,KEY,FakeFetch,fake_responses
sha=hashlib.sha256(PLAN.read_bytes()).hexdigest()
for name,aitext,orgtext,want in [
 ('known_addition',LEAD+' Omeprazole is also in it.',BAN,0),
 ('wrong_restriction_entity',LEAD,X+' is banned in Canada, but omeprazole is prohibited in India.',1),
 ('positive_control',LEAD,BAN,2)
]:
 d=A/'sealed-fresh'/name;resp=fake_responses();resp[1]['ai_overview']['text_blocks'][0]['snippet']=aitext;resp[0]['organic_results']=organic(orgtext)
 run,n=collector.run(PLAN,sha,env={'BANLAG_SERPAPI_APPROVAL':sha,'SERPAPI_API_KEY':KEY},fetch=FakeFetch(resp),store=d/'store',key_path=d/'private'/'key',now=lambda:dt.datetime(2026,10,10,10,0,5,tzinfo=dt.timezone.utc),out=lambda *a:None)
 r=evaluate_run(run,d/'store',d/'private'/'key')
 rec('sealed_'+name,'verified tier '+str(want),r['verified_evidence_tier']==want,fixture='fake fetcher, dummy keys, no API calls',ai_text=aitext,organic_text=orgtext,origin=r['origin'],label=r['answers'][0]['prereg_label'],verified_tier=r['verified_evidence_tier'],gate=r['publication_gate'])
# Additional 12 previously reported reproductions, performed independently.
extra=[]
def extra_rec(name,ok,**data):extra.append({'name':name,'outcome':'PASS' if ok else 'FAIL',**data})
good=Path('evidence/g1_corpus.json').read_bytes();man=json.loads(Path('evidence/CORPUS_MANIFEST.json').read_text())
d=A/'corpus-fresh';d.mkdir(exist_ok=True);cp=d/'g1_corpus.json';mp=d/'CORPUS_MANIFEST.json'
def write_c(raw,m):cp.write_bytes(raw);mp.write_text(json.dumps(m),encoding='utf-8');return corpus.build_cases(str(cp),str(mp))
r=write_c(good,man);extra_rec('pristine_first_load',r['corpus']['integrity']['status']=='VERIFIED')
bad=good.replace(b'is used to treat abdominal cramps',b'is used to treat abdominal crampz',1)
r=write_c(bad,dict(man,corpus_sha256=hashlib.sha256(bad).hexdigest()));extra_rec('tamper_rehash_after_load',r['corpus']['integrity']['status']=='FAILED' and all(c['publication_gate']['decision']=='WITHHOLD' for c in r['cases']))
r=write_c(good,man);extra_rec('restore_recovery',r['corpus']['integrity']['status']=='VERIFIED' and r['g1']['locked']['verdict']=='G1_PASS')
r=write_c(good,[]);extra_rec('list_manifest',r['corpus']['integrity']['status']=='FAILED')
r=write_c(good,{'corpus_sha256':hashlib.sha256(good).hexdigest()});extra_rec('missing_fields_manifest',r['corpus']['integrity']['status']=='FAILED')
b=json.loads(good);b['records'][0]['gold_label']='E';braw=json.dumps(b).encode();r=write_c(braw,dict(man,corpus_sha256=hashlib.sha256(braw).hexdigest()));extra_rec('changed_label_same_count',r['corpus']['integrity']['status']=='FAILED')
for name,ref,want in [
 ('conflicting_snippet',{'title':T,'snippet':'Dicyclomine + Paracetamol + Chlordiazepoxide tablets.','link':'https://x.invalid/p'},'CONFLICTING_VIEWS'),
 ('conflicting_url',{'title':T,'snippet':'','link':'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide-chlordiazepoxide'},'CONFLICTING_VIEWS'),
 ('two_formulations',{'title':'Antispasmodics','snippet':'Dicyclomine + Paracetamol and Dicyclomine + Paracetamol + Clidinium Bromide are both sold.','link':'https://x.invalid/p'},'MULTIPLE_FORMULATIONS'),
 ('no_formulation',{'title':'Overview','snippet':'Antispasmodic medicines.','link':'https://x.invalid/p'},'NO_FORMULATION_NAMED'),
 ('citation_positive',{'title':T,'snippet':LEAD,'link':'https://x.invalid/dicyclomine-paracetamol-clidinium-bromide'},'EXACT')
]:
 f=reference_formulation(ref);rel=relation_to(set(ING),f);extra_rec(name,rel==want,relation=rel)
# Reproduce old sealed parenthetical counterexample with the unchanged test helper (fake fetch).
from tests.test_codex_p1b import E_TierPromotion
r=E_TierPromotion().sealed(X+', a combination sold in India, is banned in the United States.',X+' (plus omeprazole) are used to treat abdominal cramps.')
extra_rec('sealed_old_composition',r['answers'][0]['prereg_label'] in ('B','F') and r['verified_evidence_tier']==0)
# TOCTOU: alter the copied file after validation. Evaluated bytes must still be the checked snapshot; next call must fail.
write_c(good,man);real_integrity=corpus.corpus_integrity
seen=[]
def after_verify(corpus_path,manifest_path,raw=None):
 integ=real_integrity(corpus_path,manifest_path,raw)
 seen.append(hashlib.sha256(raw).hexdigest());cp.write_bytes(bad)
 return integ
with patch.object(corpus,'corpus_integrity',side_effect=after_verify):loaded=corpus.load_corpus(str(cp),str(mp))
next_r=corpus.build_cases(str(cp),str(mp))
rec('corpus_validation_evaluation_snapshot','checked bytes evaluated; next read detects tamper',loaded['_sha256']==seen[0] and loaded['records']==json.loads(good)['records'] and next_r['corpus']['integrity']['status']=='FAILED',checked=seen,evaluated=loaded['_sha256'],next_read=next_r['corpus']['integrity']['status'])
write_c(good,man)
(A/'fresh-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
(A/'extra12-results.json').write_text(json.dumps(extra,indent=2),encoding='utf-8')
print(json.dumps({'fresh_probes':len(rows),'fresh_passed':sum(x['outcome']=='PASS' for x in rows),'failures':[dict(name=x['name'],text=x.get('text',x.get('ai_text')),label=x.get('label'),tier=x.get('tier',x.get('verified_tier')),relation=x.get('relation')) for x in rows if x['outcome']=='FAIL'],'extra12_passed':sum(x['outcome']=='PASS' for x in extra),'extra12_failed':[x for x in extra if x['outcome']=='FAIL']},ensure_ascii=False,indent=2))
