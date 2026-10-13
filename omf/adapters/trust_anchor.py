"""Immutable evidence trust anchors. CODE, not data: nothing under data/ can change these values.

RAW_SHA256 is the pinned SHA-256 of the original archived SerpApi google_ai_overview response (F08, run
run-20261010T024515Z-9415e2), recorded independently in G0 and in the master evidence record. The capture
record hashes were read from the original archive and agree with its own export manifest.
PROJECTION_SHA256 is the digest of the public projection that adapters.archived_aio.build() derives from
those verified raw bytes; it lets the app authenticate the projection when the private raw archive (which
contains a reusable page_token and is never shipped) is not present. If projection code changes, this pin
must be regenerated FROM VERIFIED RAW (tools/build_derivative.py --print-projection-digest) and reviewed.
SHA-256 equality proves agreement with these pinned bytes; it is not provider authentication.
"""
RAW_SHA256 = '34c1c76348b110ab16cc85c41b1af8dcbba25486307db90537f45622f95dcc24'
RECORD_SHA256 = {
    'manifest': 'ef504225dc76725a1ca818d30ed78ef4c4dd654ae4120424240372752d8b122f',
    'c1': '6253e442b9384b626f8be4b77d892aa79c8d7dff654207156a461653f1c5fc00',
    'c2': '56107e954cf17af02184f9d17394dd00837d14041de983f90ed0abf864921323',
}
RUN_ID = 'run-20261010T024515Z-9415e2'
# Derived 12 Oct 2026 ~20:40 IST by build() from raw bytes verified against RAW_SHA256 (see REPAIR_CHANGELOG.md).
PROJECTION_SHA256 = '7c7d32a48756f28beb8d539c5ebaada362a43460ca498914406c8cb5b13d31d9'
