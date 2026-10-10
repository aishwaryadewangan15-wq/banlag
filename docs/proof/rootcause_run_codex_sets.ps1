# Copy the current APP to an isolated scratch directory and run Codex's harnesses there (no network; audit hooks block
# writes under D:\HACKATHON\BANLAG). Usage: run_codex_sets.ps1 <label>
param([string]$label = 'dev')
$ErrorActionPreference = 'Stop'
$sp = $env:BANLAG_SCRATCH  # local scratch directory (redacted)
$dst = "$sp\rc_$label"
if (Test-Path $dst) { Remove-Item -LiteralPath $dst -Recurse -Force -Confirm:$false }
New-Item -ItemType Directory -Force "$dst\APP" | Out-Null
foreach ($d in 'banlag','captures','evidence','plans','tests','web') { Copy-Item -Recurse -Path "D:\HACKATHON\BANLAG\APP\$d" -Destination "$dst\APP\$d" }
Get-ChildItem -Recurse -Directory "$dst\APP" -Filter __pycache__ | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -Confirm:$false }
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location "$dst\APP"
python -I -c "import sys; sys.path.insert(0,'.'); exec(open(r'$sp\codex3_fresh_probes.py',encoding='utf-8').read())" *> "$dst\fresh_stdout.txt"
"fresh exit: $LASTEXITCODE"
python -c "import json; r=json.load(open(r'$dst\fresh-results.json',encoding='utf-8')); f=[x for x in r if x['outcome']=='FAIL']; print('fresh64:', len(r)-len(f), 'pass /', len(r)); [print('  FAIL', x['name'], '| want', x['expected'], '| got', x.get('label'), x.get('tier', x.get('verified_tier')), x.get('relation') or '', x.get('error') or '') for x in f]"
python -c "import json; r=json.load(open(r'$dst\extra12-results.json',encoding='utf-8')); print('extra12:', sum(x['outcome']=='PASS' for x in r), '/', len(r)); [print('  FAIL', x['name']) for x in r if x['outcome']!='PASS']"
python -I -c "import sys; sys.path.insert(0,'.'); exec(open(r'$sp\codex2_probes.py',encoding='utf-8').read())" *> "$dst\h48_stdout.txt"
python "$sp\score_codex2.py" "$dst\hostile-results.json" > "$dst\SCORED48.txt"; "orig48: " + (Get-Content "$dst\SCORED48.txt" -Tail 1)
Get-Content "$dst\SCORED48.txt" | Where-Object { $_ -match '^FAIL' }
python "$sp\repro_codex2_extra.py" > "$dst\EXTRA12_mine.txt" 2>&1; "my extra12: " + (Get-Content "$dst\EXTRA12_mine.txt" -Tail 1)
Pop-Location
