#!/usr/bin/env python3
"""v11 — YTUHD decoder selection disclosure, never fake hardware proof."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'Tweaks/YTUHD/Tweak.xm'
SETTINGS=ROOT/'Tweaks/YTUHD/Settings.x'
MARK='LC_DECODER_PATH_V11'
SOURCE_ANCHOR='%hook MLVideoDecoderFactory\n'
SETTINGS_ANCHOR='    [sectionItems addObject:vp9av1];'

IMPL=r'''// LC_DECODER_PATH_V11 — record the decoder factory's selection.
// A VideoToolbox capability bit or native factory class alone CANNOT prove
// that the video stream is actually using hardware acceleration.
static id LCRecordDecoderV11(id decoder, CMVideoCodecType codecType, NSString *selectedPath) {
    NSUserDefaults *prefs=[NSUserDefaults standardUserDefaults];
    NSString *codec=codecType==kCMVideoCodecType_VP9?@"VP9":
                    codecType==kCMVideoCodecType_AV1?@"AV1":
                    [NSString stringWithFormat:@"0x%08x",(unsigned int)codecType];
    [prefs setObject:codec forKey:@"LCDecoderLastCodecV11"];
    [prefs setObject:selectedPath forKey:@"LCDecoderLastPathV11"];
    [prefs setObject:decoder?NSStringFromClass([decoder class]):@"decoder not created"
           forKey:@"LCDecoderLastClassV11"];
    return decoder;
}
'''
UI=r'''    // LC_DECODER_PATH_V11
    YTSettingsSectionItem *lcDecoderState=[YTSettingsSectionItemClass
        itemWithTitle:@"Decoder selected (copy report)"
        titleDescription:@"Shows last decoder factory selection, codec, VideoToolbox capability check and supplemental VP9 registration. Native decoder path is NOT proof of hardware acceleration."
        accessibilityIdentifier:nil detailTextBlock:nil
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            NSUserDefaults *p=[NSUserDefaults standardUserDefaults];
            NSString *last=[p stringForKey:@"LCDecoderLastPathV11"]?:@"not recorded yet";
            NSString *lastCodec=[p stringForKey:@"LCDecoderLastCodecV11"]?:@"not recorded yet";
            NSString *lastClass=[p stringForKey:@"LCDecoderLastClassV11"]?:@"not recorded yet";
            NSString *report=[NSString stringWithFormat:
                @"YTUHD decoder selection (not definitive hardware proof)\nCodec: %@\nSelected factory path: %@\nDecoder instance class: %@\nVP9 hardware capability after registration: %@\nAV1 hardware capability: %@\nSupplemental registration invoked: %@\n\nThe native path can use HW or SW. Confirm sustained performance and frame drops in Stats for Nerds; a hardware decoder needs VideoToolbox session-level evidence.",
                lastCodec,last,lastClass,vtSupportsVP9?@"yes":@"no",vtSupportsAV1?@"yes":@"no",
                [p boolForKey:@"LCHWVP9RegistrationInvoked"]?@"yes":@"no"];
            [UIPasteboard generalPasteboard].string=report;
            UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Decoder path copied"
                message:report preferredStyle:UIAlertControllerStyleAlert];
            [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
            UIViewController *vc=[UIApplication sharedApplication].keyWindow.rootViewController;
            while (vc.presentedViewController) vc=vc.presentedViewController;
            if (vc) [vc presentViewController:alert animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcDecoderState];
'''

def patch(source,settings):
    if MARK in source or MARK in settings:
        raise RuntimeError('v11 decoder instrumentation already present')
    if source.count(SOURCE_ANCHOR)!=1:
        raise RuntimeError('modern YTUHD decoder factory missing; pin source version')
    if settings.count(SETTINGS_ANCHOR)!=1:
        raise RuntimeError('modern YTUHD settings changed; no safe insertion anchor')
    source=source.replace(SOURCE_ANCHOR,IMPL+'\n'+SOURCE_ANCHOR,1)
    # Software return statements in MLVideoDecoderFactory and HAMDefaultVideoDecoderFactory.
    pattern=r'(?m)^(\s*)return (YTUHDCreate(VPX|Dav1d)Decoder\([^;\n]+\));'
    def wrap(match):
        codec=match.group(3)
        label='software/libvpx' if codec=='VPX' else 'software/dav1d'
        return f'{match.group(1)}return LCRecordDecoderV11({match.group(2)}, codecType, @"{label}");'
    source,count=re.subn(pattern,wrap,source)
    if count!=12:
        raise RuntimeError(f'expected twelve software fallback paths, got {count}; upstream source changed')
    marker='    id decoder = %orig;'
    n=source.count(marker)
    if n!=6: raise RuntimeError(f'expected six native factory paths, got {n}')
    source=source.replace(marker, marker+'\n    LCRecordDecoderV11(decoder, codecType, @"system/YouTube factory (HW unverified)");')
    settings=settings.replace(SETTINGS_ANCHOR, SETTINGS_ANCHOR+'\n'+UI,1)
    return source,settings

def main():
    if not SOURCE.exists():
        print('::warning::legacy YTUHD selected; detailed factory selection requires modern YTUHD. No instrumentation applied.')
        return
    source,settings=patch(SOURCE.read_text(encoding='utf-8'),SETTINGS.read_text(encoding='utf-8'))
    SOURCE.write_text(source,encoding='utf-8')
    SETTINGS.write_text(settings,encoding='utf-8')
    print('YTUHD native/software factory selection and explicit HW-unverified label installed')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'::error::{e}',file=sys.stderr);sys.exit(1)
