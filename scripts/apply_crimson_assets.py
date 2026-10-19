#!/usr/bin/env python3
"""Place approved icons in the upstream Nyxian Xcode asset catalog."""
from pathlib import Path
import argparse, json, shutil, sys

def png_ok(path):
    data = path.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) < 24:
        raise ValueError(f'Not a PNG: {path.name}')
    w, h = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    if (w, h) != (1024, 1024):
        raise ValueError(f'Requires 1024x1024 PNG: {path.name}')

def icon_manifest(name):
    entry = {'filename': name, 'idiom': 'universal', 'platform': 'ios', 'size': '1024x1024'}
    return {'images': [entry, {**entry, 'appearances': [{'appearance': 'luminosity','value': 'dark'}]}],
            'info': {'author': 'xcode', 'version': 1}}

def preview_manifest():
    return {'images':[{'filename':'preview.png','idiom':'universal','scale':'1x'}],
            'info': {'author':'xcode','version':1}}

def install(source, assets):
    source, assets = Path(source), Path(assets)
    base = source / 'Nyxian/Assets.xcassets'
    project = source / 'Nyxian.xcodeproj/project.pbxproj'
    if not project.is_file() or not (base/'Icons/AppIcon.appiconset').is_dir():
        raise RuntimeError('Missing expected upstream Nyxian source layout')
    primary, alternate = assets/'primary.png', assets/'alternate.png'
    for p in (primary, alternate): png_ok(p)
    orig = project.read_text()
    needle = 'AppIcon Drawn Nyxcat Nyxcat2 Nyxcat3'
    new = orig.replace(needle, needle + ' CrimsonAlternate') if 'CrimsonAlternate' not in orig else orig
    if orig == new and 'CrimsonAlternate' not in orig:
        raise RuntimeError('Xcode alternate icon setting changed upstream')
    project.write_text(new)
    def save_icon(name, source_file, output_name):
        dst = base / f'Icons/{name}.appiconset'
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, dst/output_name)
        (dst/'Contents.json').write_text(json.dumps(icon_manifest(output_name), indent=2) + '\n')
    def save_preview(name, source_file):
        dst = base / f'IconPreviews/IconPreview{name}.imageset'
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, dst/'preview.png')
        (dst/'Contents.json').write_text(json.dumps(preview_manifest(),indent=2)+'\n')
    save_icon('AppIcon', primary, 'CrimsonPrimary.png')
    save_icon('CrimsonAlternate', alternate, 'CrimsonAlternate.png')
    save_preview('Default', primary)
    save_preview('CrimsonAlternate', alternate)
    print('Prepared AppIcon, CrimsonAlternate and both Settings previews')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('assets')
    args = parser.parse_args()
    try: install(args.source, args.assets)
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(2)
