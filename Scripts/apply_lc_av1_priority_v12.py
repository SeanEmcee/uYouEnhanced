#!/usr/bin/env python3
"""Prefer HW AV1 > HW VP9 among equal YouTube video renditions.

Retains every codec as a fall-through option. Format array ordering is advisory
and cannot guarantee selection by adaptive bitrate. Never forces AV1 software.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'Tweaks/YTUHD/Tweak.xm'
SETTINGS=ROOT/'Tweaks/YTUHD/Settings.x'
MARK='LC_AV1_HW_PRIORITY_V12'
SOURCE_ANCHOR='// Remove any <= 1080p VP9 formats if AllVP9 is disabled.'
UI_ANCHOR='    [sectionItems addObject:vp9av1];'
SOURCE_PATCH=r'''// LC_AV1_HW_PRIORITY_V12
// Only reorder between equivalent resolution, frame rate, and quality label.
// Leave all formats available to allow YouTube to recover from decoder failures.
static NSInteger LCCodecRankV12(MLFormat *format) {
    if (![format isKindOfClass:%c(MLFormat)] || ![format isVideo]) return 10;
    unsigned int codec=[[format MIMEType] videoCodec];
    if (codec=='av01') return vtSupportsAV1 ? 0 : 4;
    if (codec=='vp09') return vtSupportsVP9 ? 1 : 3;
    return 2;
}
static BOOL LCSameRenditionV12(MLFormat *a, MLFormat *b) {
    if (![a isKindOfClass:%c(MLFormat)] || ![b isKindOfClass:%c(MLFormat)]) return NO;
    if (![a isVideo] || ![b isVideo]) return NO;
    if (a.width<=0 || a.height<=0 || b.width<=0 || b.height<=0) return NO;
    NSString *qa=[a qualityLabel], *qb=[b qualityLabel];
    if (!qa.length || !qb.length) return NO;
    // Avoid moving an HDR format in front of a visually distinct SDR format.
    YTIColorInfo *colorA=[[a formatStream] colorInfo];
    YTIColorInfo *colorB=[[b formatStream] colorInfo];
    if ((colorA==nil)!=(colorB==nil)) return NO;
    if (colorA && colorA.transferCharacteristics!=colorB.transferCharacteristics) return NO;
    return a.width==b.width && a.height==b.height &&
        fabs((double)(a.FPS-b.FPS))<0.02 && [qa isEqualToString:qb];
}
static NSArray<MLFormat *> *LCPreferHardwareRenditionsV12(NSArray<MLFormat *> *formats) {
    NSUserDefaults *prefs=[NSUserDefaults standardUserDefaults];
    [prefs registerDefaults:@{@"LCPreferHWAV1V12":@YES}];
    if (![prefs boolForKey:@"LCPreferHWAV1V12"] || formats.count<2) return formats;
    NSMutableArray<MLFormat *> *list=[formats mutableCopy];
    NSUInteger changed=0;
    for (NSUInteger i=0;i<list.count;i++) {
        MLFormat *current=list[i];
        if (![current isKindOfClass:%c(MLFormat)] || ![current isVideo]) continue;
        NSUInteger best=i;
        NSInteger bestRank=LCCodecRankV12(current);
        for (NSUInteger j=i+1;j<list.count;j++) {
            MLFormat *candidate=list[j];
            if (!LCSameRenditionV12(current,candidate)) continue;
            NSInteger rank=LCCodecRankV12(candidate);
            if (rank<bestRank) {bestRank=rank;best=j;}
        }
        if (best!=i) { [list exchangeObjectAtIndex:i withObjectAtIndex:best]; changed++; }
    }
    [prefs setInteger:changed forKey:@"LCAV1PriorityLastReordersV12"];
    return list;
}
'''
UI_PATCH=r'''    // LC_AV1_HW_PRIORITY_V12
    NSUserDefaults *lcAV1Prefs=[NSUserDefaults standardUserDefaults];
    [lcAV1Prefs registerDefaults:@{@"LCPreferHWAV1V12":@YES}];
    YTSettingsSectionItem *lcHWCodecOrder=[YTSettingsSectionItemClass
        switchItemWithTitle:@"Prefer hardware AV1, then VP9"
        titleDescription:@"Prioritizes available hardware AV1 over hardware VP9 within equivalent renditions, while retaining all streams. An older device with no hardware AV1 prefers hardware VP9. Adaptive bitrate may ignore this ordering. Restart after changing."
        accessibilityIdentifier:nil
        switchOn:[lcAV1Prefs boolForKey:@"LCPreferHWAV1V12"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcAV1Prefs setBool:enabled forKey:@"LCPreferHWAV1V12"];
            return YES;
        } settingItemId:0];
    [sectionItems addObject:lcHWCodecOrder];
    YTSettingsSectionItem *lcHWCodecReport=[YTSettingsSectionItemClass
        itemWithTitle:@"Codec priority & capability (copy)"
        titleDescription:@"Shows selected preference, hardware support and the last decoder factory route. VideoToolbox support does NOT by itself prove active hardware decoding."
        accessibilityIdentifier:nil detailTextBlock:nil
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            NSString *path=[lcAV1Prefs stringForKey:@"LCDecoderLastPathV11"]?:@"unknown";
            NSString *codec=[lcAV1Prefs stringForKey:@"LCDecoderLastCodecV11"]?:@"unknown";
            NSString *clazz=[lcAV1Prefs stringForKey:@"LCDecoderLastClassV11"]?:@"unknown";
            NSString *report=[NSString stringWithFormat:
                @"PiP Lab v12 codec order\nPreference: %@\nAV1 hardware capability: %@\nVP9 hardware capability: %@\nYTUHD Use VP9/AV1: %@\nLast swaps: %ld\n\nLast decoder codec: %@\nFactory path: %@\nDecoder class: %@\n\nAdaptive playback can choose a different format. Factory class/capability are not confirmation of active hardware decoding. Use Stats for Nerds dropped frames and buffer metrics.",
                [lcAV1Prefs boolForKey:@"LCPreferHWAV1V12"]?@"on":@"off",
                vtSupportsAV1?@"YES":@"NO",vtSupportsVP9?@"YES":@"NO",UseVP9AV1()?@"ON":@"OFF",
                (long)[lcAV1Prefs integerForKey:@"LCAV1PriorityLastReordersV12"],codec,path,clazz];
            [UIPasteboard generalPasteboard].string=report;
            UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"Codec report copied"
                message:report preferredStyle:UIAlertControllerStyleAlert];
            [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
            UIViewController *v=LCPresenter();
            while (v.presentedViewController) v=v.presentedViewController;
            if (v) [v presentViewController:alert animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcHWCodecReport];
'''
def patch_source(source):
    if MARK in source: raise RuntimeError('v12 source patch already present')
    for anchor in (SOURCE_ANCHOR,'if (AllVP9()) return formats;', 'return [formats filteredArrayUsingPredicate:predicate];'):
        if source.count(anchor)!=1: raise RuntimeError(f'Modern YTUHD source changed at: {anchor}')
    source=source.replace(SOURCE_ANCHOR,SOURCE_PATCH+'\n'+SOURCE_ANCHOR,1)
    source=source.replace('if (AllVP9()) return formats;', 'if (AllVP9()) return LCPreferHardwareRenditionsV12(formats);',1)
    source=source.replace('return [formats filteredArrayUsingPredicate:predicate];','return LCPreferHardwareRenditionsV12([formats filteredArrayUsingPredicate:predicate]);',1)
    source=source.replace('#import <CoreMedia/CoreMedia.h>', '#include <math.h>\n#import <CoreMedia/CoreMedia.h>',1)
    return source

def patch_settings(settings):
    if MARK in settings: raise RuntimeError('v12 settings patch already present')
    if settings.count(UI_ANCHOR)!=1: raise RuntimeError('Modern YTUHD settings source changed')
    return settings.replace(UI_ANCHOR,UI_ANCHOR+'\n'+UI_PATCH,1)

def main():
    if not SOURCE.exists():
        print('::warning::Legacy YTUHD selected: hardware AV1/VP9 priority requires modern_ytuhd=true. Retaining mandatory YTUHD.')
        return
    a=patch_source(SOURCE.read_text(encoding='utf-8'))
    b=patch_settings(SETTINGS.read_text(encoding='utf-8'))
    SOURCE.write_text(a,encoding='utf-8')
    SETTINGS.write_text(b,encoding='utf-8')
    print('Installed optional AV1 HW > VP9 HW preference; all formats remain available')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(f'::error::{exc}',file=sys.stderr);sys.exit(1)
