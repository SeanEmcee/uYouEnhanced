#!/usr/bin/env python3
"""PiP Lab v5: update Actions to build with mandatory UHD/SponsorBlock plus preview guard.

Run once in a local Git clone of release v21.20.4-3.0.5. This changes
.github/workflows/buildapp.yml, not the upstream project or a GitHub run.

 - Adds the PiP Lab and unified edge-hold patch steps after checkout.
 - Hard-codes BOTH optional tweak build flags to 1 (requested by user).
 - Removes the misleading checkbox inputs (neither can be deselected).
 - Adds an IPA integrity gate before artifact upload.

Fails loudly on unknown workflow layouts instead of guessing.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys

CHECKOUT_ANCHOR = (
    "      - name: Checkout Main\n"
    "        uses: actions/checkout@v7\n"
    "        with:\n"
    "          path: main\n"
    "          ref: ${{ github.event.inputs.commit_id || github.ref }}\n"
    "          submodules: recursive\n"
)

PATCH_STEP = (
    "\n      - name: Apply LiveContainer PiP Lab\n"
    "        run: python3 main/Scripts/apply_lc_pip.py\n"
    "\n      - name: Apply unified edge hold v4 adapter\n"
    "        run: python3 main/Scripts/apply_lc_shorts.py\n"
)

VERIFY_STEP = (
    "      - name: Verify mandatory YouPiP, YTUHD and iSponsorBlock\n"
    "        run: python3 main/Scripts/verify_ipa.py \"main/packages/$RENAMED_IPA\"\n\n"
)

# Workflow inputs that used to permit omitting mandatory features.
OPTIONAL_INPUTS_PATTERN = re.compile(
    r"(?m)^      (?:ytuhd|sponsorblock):\n(?:        [^\n]*\n){1,8}"
)

MAKE_OPTION_PATTERN = re.compile(
    r"YTUHD_ENABLED=\$\{\{\s*inputs\.ytuhd\s*&&\s*'1'\s*\|\|\s*'0'\s*\}\}\s+"
    r"SPONSORBLOCK_ENABLED=\$\{\{\s*inputs\.sponsorblock\s*&&\s*'1'\s*\|\|\s*'0'\s*\}\}"
)


def replace_once(source: str, old: str, new: str, field: str) -> str:
    n = source.count(old)
    if n != 1:
        raise ValueError(f'{field}: expected one anchor, found {n}; verify pinned release workflow')
    return source.replace(old, new, 1)


def rewrite_v4_workflow(source: str) -> str:
    # Normalize CRLF to permit GitHub Windows checkout.
    s = source.replace('\r\n', '\n')
    # Preserve existing v2/v3 mandatory YTUHD + iSponsorBlock settings.
    if 'Verify mandatory YouPiP, YTUHD and iSponsorBlock' in s:
        if s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('Existing workflow lacks mandatory YTUHD/iSponsorBlock; inspect before upgrading')
        old = '      - name: Apply Shorts Hold 2x adapter\n        run: python3 main/Scripts/apply_lc_shorts.py\n'
        new = '      - name: Apply unified edge hold v4 adapter\n        run: python3 main/Scripts/apply_lc_shorts.py\n'
        if old in s:
            return replace_once(s, old, new, 'v3 upgrade')
        if new in s:
            raise ValueError('Workflow already updated to v4; scripts may still be replaced manually')
        existing = '      - name: Apply LiveContainer PiP Lab\n        run: python3 main/Scripts/apply_lc_pip.py\n'
        s = replace_once(s, existing, existing + '\n' + new, 'v2 upgrade')
        return s
    s = replace_once(s, CHECKOUT_ANCHOR, CHECKOUT_ANCHOR + PATCH_STEP, 'checkout')
    matches = list(OPTIONAL_INPUTS_PATTERN.finditer(s))
    if len(matches) != 2 or not any(m.group().startswith('      ytuhd:') for m in matches) or not any(m.group().startswith('      sponsorblock:') for m in matches):
        raise ValueError('Expected both ytuhd and sponsorblock workflow input blocks')
    # Remove in reverse to preserve offsets; both features are permanently ON.
    for m in reversed(matches):
        s = s[:m.start()] + s[m.end():]
    if len(MAKE_OPTION_PATTERN.findall(s)) != 1:
        raise ValueError('Cannot identify the precise make package option expression')
    s = MAKE_OPTION_PATTERN.sub('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1', s)
    s = replace_once(s, '      - name: Upload Artifact\n', VERIFY_STEP + '      - name: Upload Artifact\n', 'upload artifact')
    if s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
        raise ValueError('Expected exactly one forced enablement')
    if '${{ inputs.ytuhd' in s or '${{ inputs.sponsorblock' in s:
        raise ValueError('Unexpected leftover optional feature expressions')
    return s



# v5 adds exactly one source patch step after the existing v4 step.
V4_STEP = (
    '      - name: Apply unified edge hold v4 adapter\n'
    '        run: python3 main/Scripts/apply_lc_shorts.py\n'
)
V5_STEP = (
    '\n      - name: Fix overlapping feed preview audio v5\n'
    '        run: python3 main/Scripts/apply_lc_preview.py\n'
)


def rewrite_v5_workflow(source: str) -> str:
    s = source.replace('\r\n', '\n')
    if 'Fix overlapping feed preview audio v5' in s:
        # Idempotent, but still verify the required features and step order.
        if s.count(V5_STEP.strip()) != 1 or s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('Existing v5 workflow is incomplete; inspect before continuing')
        return s
    if V4_STEP in s:
        # Existing v4 kit: no need to rewrite mandatory build flags.
        if s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('v4 lacks mandatory YTUHD/iSponsorBlock; inspect workflow')
        if 'Verify mandatory YouPiP, YTUHD and iSponsorBlock' not in s:
            raise ValueError('v4 lacks final IPA verification')
    else:
        s = rewrite_v4_workflow(s)
    return replace_once(s, V4_STEP, V4_STEP + V5_STEP, 'v4 to v5 upgrade')

# v6: RYD UI count rescue, after v5 preview and before Theos package build.
V6_STEP = (
    '\n      - name: Restore missing like and dislike counts v6\n'
    '        run: python3 main/Scripts/apply_lc_counts.py\n'
)


def rewrite_v6_workflow(source: str) -> str:
    s = source.replace('\r\n', '\n')
    if V6_STEP.strip() in s:
        if s.count(V6_STEP.strip()) != 1 or s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('v6 step duplicated or required tweaks disabled')
        if 'Fix overlapping feed preview audio v5' not in s:
            raise ValueError('Missing v5 preview audio step')
        return s
    s = rewrite_v5_workflow(s)
    return replace_once(s, V5_STEP, V5_STEP + V6_STEP, 'v5 to v6 upgrade')


V7_STEP = (
    '\n      - name: Repair 2x audio and guard failed load v7\n'
    '        run: python3 main/Scripts/apply_lc_playback.py\n'
)

V8_STEP = (
    '\n      - name: Protect floating MiniPlayer gestures v8\n'
    '        run: python3 main/Scripts/apply_lc_miniplayer.py\n'
)

V9_STEP = (
    '\n      - name: Repair MiniPlayer touch and early rendering v9\n'
    '        run: python3 main/Scripts/apply_lc_miniplayer_v9.py\n'
)

def rewrite_workflow(source: str) -> str:
    s = source.replace('\r\n', '\n')
    if V8_STEP.strip() in s:
        if s.count(V8_STEP.strip()) != 1 or s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('v8 workflow invalid: repeated step or mandatory tweaks missing')
        required = (V4_STEP.strip(), V5_STEP.strip(), V6_STEP.strip(), V7_STEP.strip())
        if any(x not in s for x in required):
            raise ValueError('v8 workflow invalid: earlier patch step missing')
        return s
    if V7_STEP in s:
        if s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('v7 workflow lacks mandatory YTUHD/iSponsorBlock')
    else:
        s = rewrite_v6_workflow(s)
        s = replace_once(s, V6_STEP, V6_STEP + V7_STEP, 'v6 to v7 upgrade')
    s = replace_once(s, V7_STEP, V7_STEP + V8_STEP, 'v7 to v8 upgrade')
    if s.index(V4_STEP.strip()) >= s.index(V5_STEP.strip()) or s.index(V5_STEP.strip()) >= s.index(V6_STEP.strip()) or s.index(V6_STEP.strip()) >= s.index(V7_STEP.strip()) or s.index(V7_STEP.strip()) >= s.index(V8_STEP.strip()):
        raise ValueError('Incorrect source patch step order')
    return s

_rewrite_v8_workflow = rewrite_workflow

def rewrite_workflow(source: str) -> str:
    s = source.replace('\r\n','\n')
    if V9_STEP.strip() in s:
        if s.count(V9_STEP.strip()) != 1:
            raise ValueError('Duplicate v9 MiniPlayer patch step')
        if s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1') != 1:
            raise ValueError('Mandatory YTUHD and iSponsorBlock are not forced ON')
        return s
    s = _rewrite_v8_workflow(s)
    return replace_once(s, V8_STEP, V8_STEP+V9_STEP, 'v8 to v9 upgrade')


# v10: optional upgrade from the older bundled YTUHD fork to maintained upstream.
# Keeps YTUHD and SponsorBlock REQUIRED under both profiles.
_v9_rewrite_workflow=rewrite_workflow
V10_STEP=(
    '\n      - name: Record and select YTUHD decoder (v10)\n'
    '        env:\n'
    "          USE_MODERN: ${{ inputs.modern_ytuhd && '1' || '0' }}\n"
    '        run: |\n'
    '          if [ "$USE_MODERN" = "1" ]; then\n'
    '            echo "Modern upstream YTUHD requested; compiling with SIDELOAD=1"\n'
    '            rm -rf main/Tweaks/YTUHD\n'
    '            git clone --depth 1 --recurse-submodules --shallow-submodules --branch master https://github.com/PoomSmart/YTUHD.git main/Tweaks/YTUHD\n'
    '          else\n'
    '            echo "Using pinned uYouEnhanced YTUHD fork"\n'
    '          fi\n'
    '          git -C main/Tweaks/YTUHD rev-parse HEAD\n'
)
V10_PATCH=(
    '\n      - name: Add 4K 2x playback diagnostics v10\n'
    '        run: python3 main/Scripts/apply_lc_performance_v10.py\n'
)
MODERN_INPUT=(
    '      modern_ytuhd:\n'
    '        description: "Use newer upstream PoomSmart YTUHD decoder (experimental; fallback is bundled fork)"\n'
    '        default: true\n'
    '        required: false\n'
    '        type: boolean\n'
)

def rewrite_workflow(source: str) -> str:
    s=source.replace('\r\n','\n')
    if V10_PATCH.strip() in s:
        if s.count(V10_PATCH.strip()) != 1 or s.count(V10_STEP.strip()) != 1:
            raise ValueError('v10 steps incomplete or duplicated')
        if s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1')!=1 or 'SIDELOAD=1' not in s:
            raise ValueError('v10 requires YTUHD=1, SponsorBlock=1 and sideload mode')
        return s
    s=_v9_rewrite_workflow(s)
    s=replace_once(s, V9_STEP, V9_STEP+V10_PATCH, 'v9 to v10')
    # Insert updater after checkout, before any source patch.
    piP='      - name: Apply LiveContainer PiP Lab\n'
    s=replace_once(s,piP,V10_STEP+'\n'+piP,'YTUHD version selection')
    s=replace_once(s,'      upload_artifact:\n',MODERN_INPUT+'      upload_artifact:\n','experimental decoder checkbox')
    build='YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1'
    s=replace_once(s,build,build+' SIDELOAD=1','sideload compatibility')
    return s


# v11: transparent hardware-decoder probe + AVPlayer-only streaming controls.
# NOTE: These cannot remove server-side throughput limits.
_v10_rewrite_workflow=rewrite_workflow
V11_HW_STEP=(
    '\n      - name: Register supplemental VP9 hardware if available v11\n'
    '        if: ${{ inputs.modern_ytuhd }}\n'
    '        run: python3 main/Scripts/apply_lc_hwvp9.py\n'
)
V11_HW_UI_STEP=(
    '\n      - name: Add hardware VP9 readout v11\n'
    '        run: python3 main/Scripts/apply_lc_hardware_diagnostic.py\n'
)
V11_DECODER_STEP=(
    '\n      - name: Report YTUHD selected decoder path v11\n'
    '        if: ${{ inputs.modern_ytuhd }}\n'
    '        run: python3 main/Scripts/apply_lc_decoder_path_v11.py\n'
)
V11_CODEC_STEP=(
    '\n      - name: Prefer hardware AV1 then hardware VP9 v11\n'
    '        if: ${{ inputs.modern_ytuhd }}\n'
    '        run: python3 main/Scripts/apply_lc_codec_priority_v11.py\n'
)
V11_STREAM_STEP=(
    '\n      - name: Add automatic buffer and client rate controls v11\n'
    '        run: python3 main/Scripts/apply_lc_streaming_v11.py\n'
)

def rewrite_workflow(source: str) -> str:
    s=source.replace('\r\n','\n')
    if V11_STREAM_STEP.strip() in s:
        if V11_CODEC_STEP.strip() not in s:
            s=replace_once(s,V11_DECODER_STEP,V11_DECODER_STEP+V11_CODEC_STEP,'v11 AV1 preference upgrade')
        required=(V11_HW_STEP.strip(),V11_HW_UI_STEP.strip(),V11_DECODER_STEP.strip(),V11_CODEC_STEP.strip(),V11_STREAM_STEP.strip())
        if any(s.count(x)!=1 for x in required):
            raise ValueError('v11 source steps missing or duplicated')
        if 'YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1 SIDELOAD=1' not in s:
            raise ValueError('YTUHD, iSponsorBlock, or sideload support disabled')
        return s
    s=_v10_rewrite_workflow(s)
    s=replace_once(s,V10_STEP,V10_STEP+V11_HW_STEP,'VP9 registration after decoder selection')
    s=replace_once(s,V10_PATCH,V10_PATCH+V11_HW_UI_STEP+V11_DECODER_STEP+V11_CODEC_STEP+V11_STREAM_STEP,'streaming settings after existing playback diagnostic')
    return s

# v12: hardware AV1 before hardware VP9 among equivalent renditions.
_v11_rewrite_workflow=rewrite_workflow
V12_AV1_STEP=(
    '\n      - name: Prefer hardware AV1 then VP9 v12\n'
    '        if: ${{ inputs.modern_ytuhd }}\n'
    '        run: python3 main/Scripts/apply_lc_av1_priority_v12.py\n'
)

def rewrite_workflow(source: str) -> str:
    s=source.replace('\r\n','\n')
    if V12_AV1_STEP.strip() in s:
        if s.count(V12_AV1_STEP.strip())!=1 or s.count('YTUHD_ENABLED=1 SPONSORBLOCK_ENABLED=1 SIDELOAD=1')!=1:
            raise ValueError('v12 codec preference step duplicated or mandatory tweaks disabled')
        if V11_CODEC_STEP.strip() in s:
            raise ValueError('v11 and v12 codec preference steps must not both run')
        if V11_DECODER_STEP.strip() not in s or V11_STREAM_STEP.strip() not in s:
            raise ValueError('v12 prerequisite diagnostics are missing')
        return s
    s=_v11_rewrite_workflow(s)
    # Replace the older v11 AV1 preference, do not run both patches against
    # the same YTUHD format hook. v12 supersedes v11 for fresh and upgrade builds.
    return replace_once(s,V11_CODEC_STEP,V12_AV1_STEP,'v11 to v12 codec preference replacement')

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'), help='Local Git clone root')
    a = parser.parse_args()
    repo = a.repo.resolve()
    workflow = repo / '.github/workflows/buildapp.yml'
    if not workflow.is_file():
        raise FileNotFoundError(f'Cannot find {workflow}')
    for script in ['apply_lc_pip.py', 'apply_lc_shorts.py', 'apply_lc_preview.py', 'apply_lc_counts.py', 'apply_lc_playback.py', 'apply_lc_miniplayer.py', 'apply_lc_miniplayer_v9.py', 'apply_lc_performance_v10.py', 'apply_lc_hwvp9.py', 'apply_lc_hardware_diagnostic.py', 'apply_lc_decoder_path_v11.py', 'apply_lc_streaming_v11.py', 'verify_ipa.py']:
        if not (repo/'Scripts'/script).is_file():
            raise FileNotFoundError(f'Copy Scripts/{script} into this repo before running')
    original = workflow.read_text(encoding='utf-8')
    new = rewrite_workflow(original)
    # Optional syntactic sanity check when PyYAML is installed; not required.
    try:
        import yaml
    except ImportError:
        pass
    else:
        payload = yaml.safe_load(new)
        if 'jobs' not in payload:
            raise ValueError('Invalid YAML: jobs missing')
        steps = payload['jobs']['build']['steps']
        names = [step.get('name') for step in steps]
        for label in ('Apply LiveContainer PiP Lab', 'Apply unified edge hold v4 adapter', 'Fix overlapping feed preview audio v5', 'Restore missing like and dislike counts v6', 'Repair 2x audio and guard failed load v7', 'Protect floating MiniPlayer gestures v8', 'Repair MiniPlayer touch and early rendering v9', 'Add 4K 2x playback diagnostics v10', 'Record and select YTUHD decoder (v10)', 'Register supplemental VP9 hardware if available v11', 'Add hardware VP9 readout v11', 'Report YTUHD selected decoder path v11', 'Prefer hardware AV1 then VP9 v12', 'Add automatic buffer and client rate controls v11', 'Verify mandatory YouPiP, YTUHD and iSponsorBlock'):
            if names.count(label) != 1:
                raise ValueError(f'Invalid YAML: missing/duplicate {label}')
    workflow.write_text(new, encoding='utf-8', newline='\n')
    print(f'Updated: {workflow}')
    print('Required components: YouPiP=ON; YTUHD=ON; iSponsorBlock=ON (cannot be unchecked)')
    print('Added v12 hardware AV1>VP9 preference and report, with hardware VP9 registration and AVPlayer buffer/bitrate controls (Auto default).')
    print('Next: inspect git diff, commit and push, then run GitHub Actions.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
