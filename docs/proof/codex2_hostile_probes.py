"""Independent post-fix probes. Run from the isolated APP copy; no real API calls."""
import os,sys,json,hashlib,copy
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(Path.cwd()))
AUDIT=Path.cwd().parent
AUTH=os.path.normcase(os.path.abspath(r'D:\HACKATHON\BANLAG'))
def protected(p):
 if not isinstance(p,(str,bytes,os.PathLike)): return False
 p=os.path.normcase(os.path.abspath(os.fsdecode(p)))
 return p==AUTH or p.startswith(AUTH+os.sep)
def guard(e,a):
 if e=='open':
  p,m,f=a
  if ((isinstance(m,str) and any(c in m for c in 'wax+')) or (isinstance(f,int) and f & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))) and protected(p): raise RuntimeError('authoritative write blocked')
 elif e in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate') and protected(a[0]): raise RuntimeError('authoritative mutation blocked')
 elif e in ('os.rename','os.link','os.symlink') and any(protected(p) for p in a[:2]): raise RuntimeError('authoritative mutation blocked')
 elif e=='socket.connect' and a[1][0] not in ('127.0.0.1','::1','localhost'): raise RuntimeError('outbound network blocked')
 elif e=='socket.getaddrinfo' and a[0] not in ('127.0.0.1','::1','localhost',None): raise RuntimeError('outbound DNS blocked')
sys.addaudithook(guard)
from banlag import corpus,capture_store
from banlag.engine import evaluate,evaluate_run
from banlag.citations import reference_formulation,relation_to
from banlag.claims import restriction_statements
from banlag.legal import entry_by_id
ING=['dicyclomine','paracetamol','clidinium bromide']
F08=entry_by_id('F08')
LEAD='Dicyclomine, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.'
results=[]
def record(name,**data):
 row={'name':name,**data}; results.append(row); print(json.dumps(row,ensure_ascii=False))
def answer(name,text,organic=None,refs=None,snaps=None):
 p={'source_kind':'SYNTHETIC_TEST','query':'q','ingredients':ING,'google':{'search_metadata':{'id':'S1'},'search_parameters':{'q':'q'},'organic_results':organic or [],'ai_overview':{'text_blocks':[{'type':'paragraph','snippet':text,'reference_indexes':[0] if refs else []}],'references':refs or []}}}
 r=evaluate(p,verified_snapshots=snaps)
 a=r['answers'][0]
 record(name,text=text,organic=organic,label=a['prereg_label'],tier=r['evidence_tier'],verified_tier=r['verified_evidence_tier'],subject=a['analysis']['subject'],restrictions=[c['restriction'] for c in a['analysis']['claims'] if 'restriction' in c],tier2_hits=a['tier2_hits'],tier3_hits=a['tier3_hits'],coherence=a['citation_coherence'])
 return r
def organic(text): return [{'position':1,'title':'Restriction notice','link':'https://news.example.invalid/notice','snippet':text}]
# Identical first-audit conditions.
answer('original_1_unknown_extra','Dicyclomine, Paracetamol and Clidinium Bromide and omeprazole are used to treat abdominal cramps.')
ref={'index':0,'title':'Dicyclomine, Paracetamol and Clidinium Bromide and omeprazole','link':'https://x.invalid/p','snippet':''}
f=reference_formulation(ref); record('original_1_citation',ref=ref,formulation=f,relation=relation_to(set(ING),f))
answer('original_1_tier2',LEAD,organic('Dicyclomine, Paracetamol and Clidinium Bromide and omeprazole are prohibited in India.'))
for suffix in ['This combination is not currently banned in India.','This combination is not legally prohibited in India.','This combination was banned in India, but the ban was revoked.']:
 answer('original_4_'+suffix,LEAD+' '+suffix)
for suffix in ['Dicyclomine, Paracetamol and Clidinium Bromide is banned in the United States.','Dicyclomine, Paracetamol and Clidinium Bromide was prohibited in India, but the ban has been revoked.']:
 answer('original_5_'+suffix,LEAD,organic(suffix))
# Fresh composition variants, same declared exact input.
for text in [
 'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) are used to treat abdominal cramps.',
 'Dicyclomine, Paracetamol and Clidinium Bromide, including omeprazole, are used to treat abdominal cramps.',
 'Dicyclomine, Paracetamol and Clidinium Bromide plus activated charcoal are used to treat abdominal cramps.',
 'Dicyclomine, an omeprazole capsule, Paracetamol and Clidinium Bromide are used to treat abdominal cramps.',
 'Dicyclomine, Paracetamol and Clidinium Bromide plus light magnesium oxide are used to treat abdominal cramps.',
 'Dicyclomine, Paracetamol and Clidinium Bromide and zinc sulfate monohydrate are used to treat abdominal cramps.',
 'Dicyclomine, Paracetamol and Clidinium Bromide as well as omeprazole are used to treat abdominal cramps.',
 'Dicyclomine, Paracetamol and Clidinium Bromide; the formulation also contains omeprazole and is used to treat abdominal cramps.'
]: answer('fresh_1_'+text,text)
# Conflicting metadata views with equally many known ingredients.
for snippet in ['Dicyclomine + Paracetamol + Clidinium Bromide + Omeprazole Tablets','Dicyclomine + Paracetamol + Clidinium Bromide ...','Dicyclomine + Paracetamol + Clidinium Bromide + Simethicone Tablets']:
 ref={'index':0,'title':'Dicyclomine + Paracetamol + Clidinium Bromide Tablets','link':'https://x.invalid/p','snippet':snippet}
 f=reference_formulation(ref); record('fresh_1_citation_tie',ref=ref,formulation=f,relation=relation_to(set(ING),f))
# Fail-closed archive and self-declared manifest attack.
base=json.loads(Path('evidence/g1_corpus.json').read_text(encoding='utf-8'))
man=json.loads(Path('evidence/CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
def corpus_variant(name,c=base,m=man,missing=False):
 d=AUDIT/'corpus-probes'/name; d.mkdir(parents=True,exist_ok=True)
 (d/'g1_corpus.json').write_bytes(json.dumps(c,ensure_ascii=False,indent=1).encode())
 if not missing: (d/'CORPUS_MANIFEST.json').write_text(json.dumps(m),encoding='utf-8')
 try:
  r=corpus.build_cases(str(d/'g1_corpus.json'),str(d/'CORPUS_MANIFEST.json'))
  q=next(x for x in r['cases'] if x['entry']['id']=='F08')
  record(name,integrity=r['corpus']['integrity'],origin=r['corpus']['origin'],g1=r['g1']['locked'],q02_g1_positive=q['g1_positive'],q02_engine=q['g1_engine'],q02_gate=q['publication_gate'],q02_lead=q['uses']['A']['blocks'][0]['text'] if q['uses']['A'] else None,summary_consistent=r['g1']['summary_table_consistent'])
 except Exception as e: record(name,error=type(e).__name__,detail=str(e))
c=copy.deepcopy(base)
q=next(x for x in c['records'] if x['record_id']=='PassA_Q02')
q['blocks'][0]['text']='Dicyclomine and Paracetamol are used to treat abdominal cramps.'
corpus_variant('original_2_body_tamper',c)
corpus_variant('original_2_manifest_missing',base,missing=True)
raw=json.dumps(c,ensure_ascii=False,indent=1).encode()
corpus_variant('fresh_2_body_and_manifest_rehashed',c,dict(man,corpus_sha256=hashlib.sha256(raw).hexdigest()))
# Leave corpus bytes unchanged: use original byte serialization so null manifest alone is tested.
d=AUDIT/'corpus-probes'/'fresh_2_null_manifest'; d.mkdir(parents=True,exist_ok=True)
(d/'g1_corpus.json').write_bytes(Path('evidence/g1_corpus.json').read_bytes()); (d/'CORPUS_MANIFEST.json').write_text('null')
r=corpus.build_cases(str(d/'g1_corpus.json'),str(d/'CORPUS_MANIFEST.json'))
record('fresh_2_null_manifest',integrity=r['corpus']['integrity'],gate=r['cases'][0]['publication_gate'])
# Active controls and direct attacks on qualification and jurisdiction binding.
for status in [
 'Dicyclomine, Paracetamol and Clidinium Bromide are prohibited in India.',
 'This combination is not under any circumstances banned in India.',
 'This combination is prohibited in India only if it contains an additional benzodiazepine.',
 'This combination would be prohibited in India if the draft were approved.',
 'This combination was banned in India in 2016. The ban was subsequently revoked.',
 'This combination was banned in India. That prohibition has since been lifted.'
]: answer('fresh_4_'+status,LEAD+' '+status)
for status in [
 'Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in the United States.',
 'Dicyclomine, Paracetamol and Clidinium Bromide, a combination sold in India, is banned in Canada.',
 'Dicyclomine, Paracetamol and Clidinium Bromide is prohibited in India only if it contains an additional benzodiazepine.',
 'Dicyclomine, Paracetamol and Clidinium Bromide would be prohibited in India if the draft were approved.',
 'Dicyclomine, Paracetamol and Clidinium Bromide was banned in India. That prohibition has since been lifted.',
 'In 2016, the fixed dose combination of Dicyclomine, Paracetamol and Clidinium Bromide was prohibited in India.',
 'The Central Government has prohibited the fixed dose combination of Dicyclomine, Paracetamol and Clidinium Bromide for human use.',
 'Dicyclomine, Paracetamol and Clidinium Bromide (plus omeprazole) is prohibited in India.'
]:
 answer('fresh_5_'+status,LEAD,organic(status))
 url='https://ref.example.invalid/p'
 answer('fresh_5_tier3_'+status,LEAD,refs=[{'index':0,'link':url}],snaps=[{'url':url,'text':status,'sha256':'0'*64}])
# Original counterfeit conditions: self-consistent raw bytes + arbitrary HMAC, no local key.
s=AUDIT/'forged-store'; (s/'raw').mkdir(parents=True,exist_ok=True)
template=json.loads(next(Path('captures/store').glob('*C1.json')).read_text(encoding='utf-8')) if list(Path('captures/store').glob('*C1.json')) else json.loads(next(p for p in Path('captures/store').glob('*.json') if json.loads(p.read_text())['record']['role']=='uses_search').read_text())
rec=copy.deepcopy(template['record']); rec.update(run_id='forged-run',capture_id='forged-capture',call_id='C1',call_index=1,role='uses_search')
rec['request']={'engine':'google','params':{'q':'q'}}
rec['plan']['ingredients']=ING
raw=json.dumps({'search_metadata':rec['provider'],'search_parameters':{'engine':'google','q':'q'},'ai_overview':{'text_blocks':[{'type':'paragraph','snippet':LEAD}],'references':[]},'organic_results':organic('Dicyclomine, Paracetamol and Clidinium Bromide is banned in India.')}).encode()
sha=hashlib.sha256(raw).hexdigest(); rec.update(raw_sha256=sha,raw_file='raw/'+sha+'.json',raw_bytes=len(raw))
(s/'raw'/f'{sha}.json').write_bytes(raw); (s/'forged-capture.json').write_text(json.dumps({'record':rec,'hmac_sha256':'0'*64}),encoding='utf-8')
r=evaluate_run('forged-run',s,AUDIT/'nonexistent-key'/'key')
record('original_3_forged_keyless_archive',origin=r['origin'],tier=r['evidence_tier'],verified_tier=r['verified_evidence_tier'],replay_tier=r['replay_evidence_tier'],tier_status=r['tier_status'],gate=r['publication_gate'])
# Citation uncertainty control.
answer('original_P2_uncertain_citation',LEAD,refs=[{'index':0,'title':'Overview','link':'https://x.invalid/p','snippet':'A page.'}])
answer('original_P2_single_component_citation',LEAD,refs=[{'index':0,'title':'Paracetamol','link':'https://x.invalid/p','snippet':'Paracetamol treats pain.'}])
(AUDIT/'hostile-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('RESULTS_WRITTEN',str(AUDIT/'hostile-results.json'))
