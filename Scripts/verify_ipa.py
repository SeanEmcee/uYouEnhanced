#!/usr/bin/env python3
"""Fail the GitHub build unless the FINAL IPA contains all requested tweaks.

Note: checking library filenames proves inclusion, not whether code hooks work.
"""
from pathlib import Path
import hashlib
import sys
import zipfile

EXPECTED = {
    'YouPiP': 'YouPiP.dylib',
    'YTHoldForSpeed': 'YTHoldForSpeed.dylib',
    'Return YouTube Dislike': 'YouTubeDislikesReturn.dylib',
    'YTUHD': 'YTUHD.dylib',
    'iSponsorBlock': 'iSponsorBlock.dylib',
}


def verify(ipa: Path) -> int:
    if not ipa.is_file():
        print(f'FAIL: IPA not found: {ipa}', file=sys.stderr)
        return 1
    try:
        with zipfile.ZipFile(ipa) as zf:
            corrupted = zf.testzip()
            if corrupted:
                print(f'FAIL: corrupt archive entry: {corrupted}', file=sys.stderr)
                return 1
            names = [info.filename for info in zf.infolist()]
    except (OSError, zipfile.BadZipFile) as exc:
        print(f'FAIL: invalid IPA archive: {exc}', file=sys.stderr)
        return 1

    app_files = [n for n in names if n.startswith('Payload/') and '.app/' in n]
    missing = []
    print(f'Final IPA: {ipa.name}')
    if not app_files:
        print('FAIL: no Payload/*.app content found')
        missing.append('App bundle')
    for label, filename in EXPECTED.items():
        matches = [n for n in names if n.endswith('/' + filename)]
        if matches:
            print(f'PASS: {label} included -> {matches[0]}')
        else:
            print(f'FAIL: missing {label} ({filename})')
            missing.append(label)
    if missing:
        print('FAIL: required components missing: ' + ', '.join(missing))
        print('No IPA should be published from this workflow run.')
        return 1
    with ipa.open('rb') as f:
        print('SHA-256: ' + hashlib.file_digest(f, 'sha256').hexdigest())
    print('PASS: all required tweaks packaged. iPhone runtime compatibility is not established by this check.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: python Scripts/verify_ipa.py /path/to/YouTube.ipa')
    sys.exit(verify(Path(sys.argv[1])))
