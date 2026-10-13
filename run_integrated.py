"""Single-origin offline composition of copied BANLAG and OMF sources."""
import os, sys, json, re, mimetypes
from pathlib import Path
from urllib.parse import urlparse
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
ORIG = ROOT / 'original'
V2 = ROOT / 'omf'
# Never consult the source tree's archival raw capture directory.
os.environ['OMF_ORIGINAL_RUN_DIR'] = str(ROOT / 'NO_ARCHIVE_CONFIGURED')
sys.path.insert(0, str(ORIG))
import banlag.server as B
sys.path.insert(0, str(V2))
import app as O
O.Handler.state = O.State()

class Integrated(B.Handler):
    state = O.Handler.state
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        return O.Handler._send(self, code, body, ctype)
    def _omf_path(self):
        return urlparse(self.path).path.startswith('/omf/') or urlparse(self.path).path == '/omf'
    def do_GET(self):
        if not self._omf_path():
            if urlparse(self.path).path == '/':
                if not self._host_ok(): return self._json({'error':'Host not allowed'},421)
                data=(B.ASSETS/'index.html').read_bytes()
                link=b'<nav aria-label="BANLAG modes"><a href="/omf/">One Missing Fact</a> | <a href="/">Evidence audit</a></nav>'
                data=data.replace(b'<body>',b'<body>'+link,1)
                self._headers(200,B.TYPES['.html'],len(data)); return self.wfile.write(data)
            return B.Handler.do_GET(self)
        if not self._host_ok(): return self._json({'error':'Host not allowed'},421)
        p=urlparse(self.path).path
        if p == '/omf':
            self.send_response(308); self.send_header('Location','/omf/'); self.send_header('Content-Length','0'); self.end_headers(); return
        if p.startswith('/omf/api/'):
            old=self.path; self.path=self.path[len('/omf'):]
            try:
                if self.path.split('?')[0] == '/api/evidence': return O.Handler.do_GET(self)
                return O.Handler.do_GET(self)
            finally: self.path=old
        assets={'/omf/':'index.html','/omf/index.html':'index.html','/omf/app.js':'app.js','/omf/style.css':'style.css'}
        name=assets.get(p)
        if not name: return O.Handler._send(self,404,{'error':'NOT_FOUND'})
        data=(V2/'web'/name).read_bytes()
        if name=='index.html':
            data=data.replace(b'href="/style.css"',b'href="/omf/style.css"').replace(b'src="/app.js"',b'src="/omf/app.js"')
            nav=b'<nav aria-label="BANLAG modes"><a href="/">Evidence audit</a> | <a href="/omf/">One Missing Fact</a></nav>'
            data=data.replace(b'<body>',b'<body>'+nav,1)
        if name=='app.js': data=data.replace(b"'/api/",b"'/omf/api/").replace(b'"/api/',b'"/omf/api/')
        return O.Handler._send(self,200,data,{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.rsplit('.',1)[-1]])
    def do_POST(self):
        if not self._omf_path(): return B.Handler.do_POST(self)
        if not self._host_ok(): return self._json({'error':'Host not allowed'},421)
        old=self.path; self.path=self.path[len('/omf'):]
        try: return O.Handler.do_POST(self)
        finally: self.path=old
    def do_HEAD(self):
        if self._omf_path(): return self.do_GET()
        return B.Handler.do_GET(self)

if __name__=='__main__':
    srv=ThreadingHTTPServer(('127.0.0.1',0),Integrated)
    print('BANLAG integrated offline server http://127.0.0.1:%d/'%srv.server_address[1],flush=True)
    print('OMF evidence state: %s; authentic=%s'%(O.Handler.state.decision['state'],O.Handler.state.decision['authentic']),flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    finally: srv.server_close()
