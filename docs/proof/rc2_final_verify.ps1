# Final verification of the RC-2 candidate. No network; writes only to the scratchpad.
$ErrorActionPreference = 'Continue'
$sp = '<SCRATCH>'
$app = 'D:\HACKATHON\BANLAG\APP'
$out = "$sp\RC2_FINAL_VERIFY.txt"
$env:PYTHONDONTWRITEBYTECODE = '1'
function W($s) { $s | Tee-Object -FilePath $out -Append }
if (Test-Path $out) { Clear-Content $out }
W ("run at " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'))
$files = Get-ChildItem -Recurse -File "$app\banlag","$app\web","$app\tests" -Include *.py,*.js,*.html,*.css,*.json | Sort-Object FullName
$lines = $files | ForEach-Object { (Get-FileHash -Algorithm SHA256 $_.FullName).Hash + '  ' + $_.FullName.Substring($app.Length + 1) }
$lines | Out-File "$sp\CODE_IDENTITY_RC2.txt" -Encoding utf8
$agg = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n")))).Replace('-','').ToLower()
W "RC-2 code identity ($($files.Count) source files, documented method): $agg"
$agg | Set-Content "$sp\CODE_IDENTITY_RC2.sha"
$all = Get-ChildItem -Recurse -File "$app\banlag","$app\web","$app\tests" | Where-Object { $_.FullName -notmatch '\\__pycache__\\' }
W ("files under banlag/ web/ tests/ (non-cache): " + $all.Count + "; outside the identity's extensions: " + @($all | Where-Object { $_.Extension -notin '.py','.js','.html','.css','.json' }).Count)
$b = @{}; Get-Content "$sp\CODE_IDENTITY_FINAL.txt" | ForEach-Object { $b[$_.Substring(66).Trim()] = $_.Substring(0,64) }
$f = @{}; $lines | ForEach-Object { $f[$_.Substring(66).Trim()] = $_.Substring(0,64) }
W ("changed vs RC-1: " + (($f.Keys | Where-Object { $b.ContainsKey($_) -and $b[$_] -ne $f[$_] } | Sort-Object) -join ', '))
W ("added vs RC-1:   " + (($f.Keys | Where-Object { -not $b.ContainsKey($_) } | Sort-Object) -join ', '))
W ("removed vs RC-1: " + (($b.Keys | Where-Object { -not $f.ContainsKey($_) } | Sort-Object) -join ', '))
W ("pre-existing test files unchanged: " + (($b.Keys | Where-Object { $_ -like 'tests\*' -and $b[$_] -eq $f[$_] }).Count) + " of " + (($b.Keys | Where-Object { $_ -like 'tests\*' }).Count))
Set-Location $app
python -m unittest discover -s tests -v *> "$sp\rc2_suite_KEY.txt"; $e1 = $LASTEXITCODE
$env:BANLAG_KEY_DIR = "$sp\emptykey"; python -m unittest discover -s tests -v *> "$sp\rc2_suite_KEYLESS.txt"; $e2 = $LASTEXITCODE; $env:BANLAG_KEY_DIR = $null
W ("suite with local key: exit $e1; " + ((Get-Content "$sp\rc2_suite_KEY.txt" | Select-String '^Ran ').Line) + '; ' + (Get-Content "$sp\rc2_suite_KEY.txt" -Tail 1))
W ("suite keyless:        exit $e2; " + ((Get-Content "$sp\rc2_suite_KEYLESS.txt" | Select-String '^Ran ').Line) + '; ' + (Get-Content "$sp\rc2_suite_KEYLESS.txt" -Tail 1))
W ("  skipped: " + ((Get-Content "$sp\rc2_suite_KEYLESS.txt" | Select-String '\.\.\. skipped' | ForEach-Object { ($_.Line -split ' ')[0] }) -join ', '))
W ("  empty key dir entries after keyless run: " + @(Get-ChildItem -Force "$sp\emptykey").Count)
W ("corpus " + (python "$sp\run_claims.py" evidence\g1_corpus.json 2>&1 | Select-Object -Last 1))
python "$sp\replay_dump.py" > "$sp\replay_RC2F.json" 2>&1; python "$sp\g1_dump.py" > "$sp\g1_RC2F.json" 2>&1; python "$sp\bench_dump.py" > "$sp\bench_RC2F.json" 2>$null
W ("live sealed replay summary identical to baseline: " + ((Get-FileHash "$sp\replay_BEFORE.json").Hash -eq (Get-FileHash "$sp\replay_RC2F.json").Hash))
W ("G1 summary (locked 7/10, per-case gates) identical to baseline: " + ((Get-FileHash "$sp\g1_BEFORE.json").Hash -eq (Get-FileHash "$sp\g1_RC2F.json").Hash))
W ("benchmark blocks: " + (python "$sp\json_diff_paths.py" "$sp\bench_BEFORE.json" "$sp\bench_RC2F.json" "composition_verdict,composition_blockers,reference_index_problems,formulation_supported,malformed_indexes" | Select-Object -First 1))
$env:BANLAG_KEY_DIR = "$sp\emptykey"
W (python -c "import sys; sys.path.insert(0,'.'); from banlag.engine import evaluate_run; r = evaluate_run('run-20261010T024515Z-9415e2', 'captures/store'); print('keyless live replay:', r['origin'], 'verified', r['verified_evidence_tier'], r['tier_status'], r['publication_gate']['decision'], [(a['surface'], a['prereg_label']) for a in r['answers']])")
$env:BANLAG_KEY_DIR = $null
W (python -c "import sys; sys.path.insert(0,'.'); from banlag.engine import evaluate_run; r = evaluate_run('run-20261010T024515Z-9415e2', 'captures/store'); f = r['answers'][0]['citation_coherence']['findings']; print('key-holding live replay:', r['origin'], 'tier', r['evidence_tier'], 'verified', r['verified_evidence_tier'], r['publication_gate']['decision'], [(a['surface'], a['prereg_label']) for a in r['answers']], [(x['type'], [(s['index'], s['entry']) for s in x['other_notice_sources']], [s['index'] for s in x['unresolved_sources']]) for x in f])")
W ((python -m banlag.evidence_ingest --evidence 'D:\HACKATHON\BANLAG\EVIDENCE\banlag_v2_audit' --verify 2>&1 | Select-Object -Last 1))
W (python "$sp\check_evidence.py" 'D:\HACKATHON\BANLAG\EVIDENCE\banlag_v2_audit')
W ("newest locked-evidence file: " + ((Get-ChildItem -Recurse -File 'D:\HACKATHON\BANLAG\EVIDENCE\banlag_v2_audit' | Sort-Object LastWriteTime | Select-Object -Last 1).LastWriteTime))
W ("raw capture names equal their sha256: " + ((Get-ChildItem captures\store\raw\*.json | Where-Object { (Get-FileHash $_.FullName).Hash.ToLower() + '.json' -ne $_.Name }).Count -eq 0))
# RC-2 reproduction on a fresh isolated copy
$d = "$sp\rc2_final"
python "$sp\freeze_snapshot.py" $app $d | Select-Object -First 1 | Out-Null
Copy-Item -Recurse "$app\captures" "$d\APP\captures"
Set-Location "$d\APP"; python "$sp\repro_rc2.py" 2>&1 | Where-Object { $_ -notmatch '^LOCAL HTTP' } | Out-File "$sp\RC2_REPRO_AFTER.txt" -Encoding utf8
W ("RC-2 reproduction (fresh copy): " + (Get-Content "$sp\RC2_REPRO_AFTER.txt" -Tail 1))
Set-Location $app
& "$sp\run_codex_sets.ps1" rc2final | ForEach-Object { W $_ }
Set-Location $app
W ((python "$sp\meta_probe.py" 2>&1 | Select-Object -Last 1))
W ((python "$sp\meta_probe2.py" 2>&1 | Select-Object -Last 1))
W ((python "$sp\meta_probe3.py" 2>&1 | Select-Object -Last 1))
W (python "$sp\secret_scan.py" $app "$sp\rc2_final" | Select-Object -Last 1)
W ("BANLAG_SERPAPI_APPROVAL set: " + [bool]$env:BANLAG_SERPAPI_APPROVAL)
