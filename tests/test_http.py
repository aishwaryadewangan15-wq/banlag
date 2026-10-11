import http.client,json,threading,unittest
from http.server import ThreadingHTTPServer
from banlag.server import Handler
from banlag.public import legacy_view

class HTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.s=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  cls.t=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.t.start()
 @classmethod
 def tearDownClass(cls):
  cls.s.shutdown();cls.s.server_close();cls.t.join(timeout=3)
 def request(self,method,path,obj=None):
  c=http.client.HTTPConnection('127.0.0.1',self.s.server_port,timeout=4)
  raw=json.dumps(obj).encode() if obj is not None else None
  c.request(method,path,body=raw,headers={'Content-Type':'application/json'} if raw else {})
  r=c.getresponse();data=r.read().decode();status=r.status;c.close();return status,legacy_view(json.loads(data)) if path.startswith('/api/') else data  # public contract: legacy fields are served under "experimental"; legacy_view restores them (values unchanged)
 def test_registry_read_only(self):
  s,r=self.request('GET','/api/registry');self.assertEqual(s,200);self.assertEqual(len(r['entries']),16)
 def test_default_no_live_activity(self):
  s,r=self.request('GET','/api/status');self.assertEqual(s,200)
  self.assertFalse(r['live_serpapi_enabled']);self.assertEqual(r['serpapi_requests_made'],0)
 def test_local_match_negative_control(self):
  s,r=self.request('POST','/api/match',{'ingredients':['amoxicillin','serratiopeptidase','clavulanic acid']})
  self.assertEqual(s,200);self.assertEqual(r['status'],'NO_EXACT_MATCH')
 def test_local_evaluate(self):
  s,r=self.request('POST','/api/evaluate',{'source_kind':'SYNTHETIC_TEST','ingredients':['amoxicillin','serratiopeptidase'],
    'ai_mode':{'text_blocks':[{'snippet':'Amoxicillin + serratiopeptidase is commonly prescribed.'}]}})
  self.assertEqual(s,200);self.assertEqual(r['evidence_tier'],1)
 def test_import_no_implicit_origin(self):
  s,r=self.request('POST','/api/evaluate',{'ingredients':['amoxicillin','serratiopeptidase']})
  self.assertEqual(s,400)
 def test_local_assets(self):
  for p in ['/','/app.js','/style.css']:
   s,r=self.request('GET',p);self.assertEqual(s,200);self.assertGreater(len(r),100)
if __name__=='__main__':unittest.main()
