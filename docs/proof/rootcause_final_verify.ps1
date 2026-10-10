# Final verification of the frozen candidate. No network; writes only to the scratchpad (and nothing to APP or evidence).
$ErrorActionPreference = 'Continue'
$sp = $env:BANLAG_SCRATCH  # local scratch directory (redacted)
$app = 'D:\HACKATHON\BANLAG\APP'
$out = "$sp\FINAL_VERIFY.txt"
$env:PYTHONDONTWRITEBYTECODE = '1'
function W($s) { $s | Tee-Object -FilePath $out -Append }
if (Test-Path $out) { Clear-Content $out }
W ("run at " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'))
# identity (documented method) + full inventory of banlag/ web/ tests/
$files = Get-ChildItem -Recurse -File "$app\banlag","$app\web","$app\tests" -Include *.py,*.js,*.html,*.css,*.json | Sort-Object FullName
$lines = $files | ForEach-Object { (Get-FileHash -Algorithm SHA256 $_.FullName).Hash + '  ' + $_.FullName.Substring($app.Length + 1) }
$lines | Out-File "$sp\CODE_IDENTITY_FINAL.txt" -Encoding utf8
$agg = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n")))).Replace('-','').ToLower()
W "code identity ($($files.Count) source files, documented method): $agg"
$agg | Set-Content "$sp\CODE_IDENTITY_FINAL.sha"
$all = Get-ChildItem -Recurse -File "$app\banlag","$app\web","$app\tests" | Where-Object { $_.FullName -notmatch '\\__pycache__\\' }
$excluded = $all | Where-Object { $_.Extension -notin '.py','.js','.html','.css','.json' }
W ("files under banlag/ web/ tests/ (non-cache): " + $all.Count + "; outside the identity's extensions: " + (($excluded | ForEach-Object { $_.FullName.Substring($app.Length + 1) }) -join ', '))
W ("new source modules included: " + (($lines | Where-Object { $_ -match 'semantics\.py|test_semantic_core\.py' } | ForEach-Object { $_.Substring(66) }) -join ', '))
# suites
Set-Location $app
python -m unittest discover -s tests -v *> "$sp\final_suite_KEY.txt"; $e1 = $LASTEXITCODE
$env:BANLAG_KEY_DIR = "$sp\emptykey"; python -m unittest discover -s tests -v *> "$sp\final_suite_KEYLESS.txt"; $e2 = $LASTEXITCODE; $env:BANLAG_KEY_DIR = $null
W ("suite with local key: exit $e1; " + ((Get-Content "$sp\final_suite_KEY.txt" | Select-String '^Ran ').Line) + '; ' + (Get-Content "$sp\final_suite_KEY.txt" -Tail 1))
W ("suite keyless:        exit $e2; " + ((Get-Content "$sp\final_suite_KEYLESS.txt" | Select-String '^Ran ').Line) + '; ' + (Get-Content "$sp\final_suite_KEYLESS.txt" -Tail 1))
W ("  skipped: " + ((Get-Content "$sp\final_suite_KEYLESS.txt" | Select-String '\.\.\. skipped' | ForEach-Object { ($_.Line -split ' ')[0] }) -join ', '))
W ("  empty key dir entries after keyless run: " + @(Get-ChildItem -Force "$sp\emptykey").Count)
# corpus + preservation
W ("corpus " + (python "$sp\run_claims.py" evidence\g1_corpus.json 2>&1 | Select-Object -Last 1))
python "$sp\replay_dump.py" > "$sp\replay_FINALRC.json" 2>&1; python "$sp\g1_dump.py" > "$sp\g1_FINALRC.json" 2>&1; python "$sp\bench_dump.py" > "$sp\bench_FINALRC.json" 2>$null
W ("live sealed replay summary identical to baseline: " + ((Get-FileHash "$sp\replay_BEFORE.json").Hash -eq (Get-FileHash "$sp\replay_FINALRC.json").Hash))
W ("G1 summary identical to baseline: " + ((Get-FileHash "$sp\g1_BEFORE.json").Hash -eq (Get-FileHash "$sp\g1_FINALRC.json").Hash))
W ("benchmark/agreement/adversarial/controls/notice_integrity: " + (python "$sp\json_same_minus.py" "$sp\bench_BEFORE.json" "$sp\bench_FINALRC.json" "composition_verdict,composition_blockers,reference_index_problems"))
$env:BANLAG_KEY_DIR = "$sp\emptykey"
W (python -c "import sys; sys.path.insert(0,'.'); from banlag.engine import evaluate_run; r = evaluate_run('run-20261010T024515Z-9415e2', 'captures/store'); print('keyless live replay:', r['origin'], 'verified', r['verified_evidence_tier'], r['tier_status'], r['publication_gate']['decision'], [(a['surface'], a['prereg_label']) for a in r['answers']])")
$env:BANLAG_KEY_DIR = $null
W (python -c "import sys; sys.path.insert(0,'.'); from banlag.engine import evaluate_run; r = evaluate_run('run-20261010T024515Z-9415e2', 'captures/store'); print('key-holding live replay:', r['origin'], 'tier', r['evidence_tier'], 'verified', r['verified_evidence_tier'], r['publication_gate']['decision'], [(a['surface'], a['prereg_label']) for a in r['answers']])")
W ((python -m banlag.evidence_ingest --evidence 'D:\HACKATHON\BANLAG\EVIDENCE\banlag_v2_audit' --verify 2>&1 | Select-Object -Last 1))
W (python "$sp\check_evidence.py" 'D:\HACKATHON\BANLAG\EVIDENCE\banlag_v2_audit')
W ("newest locked-evidence file: " + ((Get-ChildItem -Recurse -File 'D:\HACKATHON\BANLAG\EVIDENCE\banlag_v2_audit' | Sort-Object LastWriteTime | Select-Object -Last 1).LastWriteTime))
W ("sealed store files: " + ((Get-ChildItem -Recurse -File captures\store | ForEach-Object { $_.Name.Substring(0, [Math]::Min(16, $_.Name.Length)) + '…' + ((Get-FileHash $_.FullName).Hash.ToLower().Substring(0,12)) }) -join ', '))
W ("raw capture names equal their sha256: " + ((Get-ChildItem captures\store\raw\*.json | Where-Object { (Get-FileHash $_.FullName).Hash.ToLower() + '.json' -ne $_.Name }).Count -eq 0))
# Codex sets on a fresh isolated copy
& "$sp\run_codex_sets.ps1" final | ForEach-Object { W $_ }
# developer sets (now regression; first-run results recorded separately)
Set-Location $app
W ((python "$sp\meta_probe.py" 2>&1 | Select-Object -Last 1))
W ((python "$sp\meta_probe2.py" 2>&1 | Select-Object -Last 1))
W ((python "$sp\meta_probe3.py" 2>&1 | Select-Object -Last 1))
W (python "$sp\secret_scan.py" $app "$sp\rc_final" | Select-Object -Last 1)
W ("BANLAG_SERPAPI_APPROVAL set: " + [bool]$env:BANLAG_SERPAPI_APPROVAL)
