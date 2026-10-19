#!/usr/bin/env python3
"""v11 — opt-in AVPlayer buffer targets and client bitrate ceilings.

The controls are not YouTube server throughput unlocks. They only apply to
AVPlayer-based playback. Defaults make no changes to YouTube behavior.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'Sources/LCStreamingBuffer.xm'
SETTINGS = ROOT / 'Tweaks/YTUHD/Settings.x'
MARK = 'LC_STREAMING_V11'
ANCHORS = ('    [sectionItems addObject:vp9av1];', '    [sectionItems addObject:tweakVersion];')

SOURCE_CONTENT = r'''// LC_STREAMING_V11: Optional AVFoundation buffering preferences.
// Does not interfere with YouTube custom HAM player, network request pacing,
// codecs, ABR, sign-in, YouPiP, YTUHD, or iSponsorBlock.
#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>

static void LCStreamingApply(AVPlayerItem *item) {
    if (!item) return;
    NSUserDefaults *prefs = [NSUserDefaults standardUserDefaults];
    NSInteger seconds = [prefs integerForKey:@"LCStreamingBufferSecondsV11"];
    double ceilingMbps = [prefs doubleForKey:@"LCStreamingClientBitrateMbpsV11"];
    // 0/0 means automatic, so don't modify the item's native settings.
    if (seconds > 0 && seconds <= 180)
        item.preferredForwardBufferDuration = (NSTimeInterval)seconds;
    if (ceilingMbps > 0 && ceilingMbps <= 80)
        item.preferredPeakBitRate = ceilingMbps * 1000000.0;
    // An item with these preferences is only an application hint. It is NOT
    // evidence that YouTube fetched the requested seconds/bitrate.
    [prefs setObject:@(seconds) forKey:@"LCStreamingLastBufferRequestedV11"];
    [prefs setObject:@(ceilingMbps) forKey:@"LCStreamingLastBitrateRequestedV11"];
    [prefs setBool:YES forKey:@"LCStreamingAVPlayerObservedV11"];
}

%hook AVPlayerItem
- (instancetype)initWithAsset:(AVAsset *)asset {
    AVPlayerItem *result = %orig;
    LCStreamingApply(result);
    return result;
}
- (instancetype)initWithAsset:(AVAsset *)asset automaticallyLoadedAssetKeys:(NSArray<NSString *> *)keys {
    AVPlayerItem *result = %orig;
    LCStreamingApply(result);
    return result;
}
%end

%hook AVPlayer
- (void)replaceCurrentItemWithPlayerItem:(AVPlayerItem *)item {
    LCStreamingApply(item);
    %orig;
}
%end

%ctor {
    NSUserDefaults *prefs = [NSUserDefaults standardUserDefaults];
    [prefs setBool:NO forKey:@"LCStreamingAVPlayerObservedV11"];
    [prefs removeObjectForKey:@"LCStreamingLastBufferRequestedV11"];
    [prefs removeObjectForKey:@"LCStreamingLastBitrateRequestedV11"];
}
'''

SETTINGS_CONTENT = r'''    // LC_STREAMING_V11: Values are AVPlayer hints, NOT CDN throttling bypass.
    NSUserDefaults *lcStreamPrefs=[NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *lcBuffer=[YTSettingsSectionItemClass
        itemWithTitle:@"Buffer ahead target (AVPlayer)"
        titleDescription:@"Automatic by default. Request 30/60/120/180 seconds ahead on compatible AVPlayer streams. YouTube's custom streaming player may ignore this; more buffering uses memory and data."
        accessibilityIdentifier:nil
        detailTextBlock:^NSString *() {
            NSInteger v=[lcStreamPrefs integerForKey:@"LCStreamingBufferSecondsV11"];
            return v==0?@"Automatic":[NSString stringWithFormat:@"%ld sec",(long)v];
        }
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            UIAlertController *sheet=[UIAlertController alertControllerWithTitle:@"Buffer ahead target"
                message:@"AVPlayer preference only. Automatic makes no override. Changes apply to new player items."
                preferredStyle:UIAlertControllerStyleAlert];
            NSArray<NSNumber *> *vals=@[@0,@30,@60,@120,@180];
            for (NSNumber *n in vals) {
                NSString *name=n.integerValue==0?@"Automatic (default)":[NSString stringWithFormat:@"%@ seconds",n];
                [sheet addAction:[UIAlertAction actionWithTitle:name style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
                    [lcStreamPrefs setInteger:n.integerValue forKey:@"LCStreamingBufferSecondsV11"];
                    [settingsViewController reloadData];
                }]];
            }
            [sheet addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
            UIViewController *presenter=LCPresenter();
            while (presenter.presentedViewController) presenter=presenter.presentedViewController;
            if (presenter) [presenter presentViewController:sheet animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcBuffer];
    YTSettingsSectionItem *lcCeiling=[YTSettingsSectionItemClass
        itemWithTitle:@"Client bitrate ceiling (AVPlayer)"
        titleDescription:@"Automatic by default. Can only LOWER the requested bitrate. This CANNOT raise YouTube CDN throughput or unlock a server-side speed cap."
        accessibilityIdentifier:nil
        detailTextBlock:^NSString *() {
            NSInteger v=[lcStreamPrefs integerForKey:@"LCStreamingClientBitrateMbpsV11"];
            return v==0?@"Automatic / no override":[NSString stringWithFormat:@"%ld Mbps maximum",(long)v];
        }
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            UIAlertController *sheet=[UIAlertController alertControllerWithTitle:@"Client bitrate ceiling"
                message:@"Zero is automatic/no override. A nonzero ceiling may REDUCE video quality; it does not speed up downloads. Changes apply to new player items."
                preferredStyle:UIAlertControllerStyleAlert];
            NSArray<NSNumber *> *vals=@[@0,@20,@40,@80];
            for (NSNumber *n in vals) {
                NSString *name=n.integerValue==0?@"Automatic (default)":[NSString stringWithFormat:@"%@ Mbps maximum",n];
                [sheet addAction:[UIAlertAction actionWithTitle:name style:UIAlertActionStyleDefault handler:^(UIAlertAction *a) {
                    [lcStreamPrefs setInteger:n.integerValue forKey:@"LCStreamingClientBitrateMbpsV11"];
                    [settingsViewController reloadData];
                }]];
            }
            [sheet addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
            UIViewController *presenter=LCPresenter();
            while (presenter.presentedViewController) presenter=presenter.presentedViewController;
            if (presenter) [presenter presentViewController:sheet animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcCeiling];
    YTSettingsSectionItem *lcStreamState=[YTSettingsSectionItemClass
        itemWithTitle:@"Buffer / throughput state (copy)"
        titleDescription:@"Reports saved targets and whether an AVPlayerItem was observed this launch. Does NOT prove the server honored them. For live throughput, see Stats for Nerds."
        accessibilityIdentifier:nil detailTextBlock:nil
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            NSInteger target=[lcStreamPrefs integerForKey:@"LCStreamingBufferSecondsV11"];
            NSInteger ceiling=[lcStreamPrefs integerForKey:@"LCStreamingClientBitrateMbpsV11"];
            NSString *report=[NSString stringWithFormat:
                @"PiP Lab v11 — streaming settings\nBuffer requested: %@\nClient bitrate ceiling: %@\nAVPlayer item observed this launch: %@\nLast buffer request sent to AVPlayer: %@\n\nA requested buffer duration does not guarantee download ahead. YouTube custom renderer may bypass AVPlayerItem. A client bitrate ceiling CANNOT raise CDN throughput. See Stats for Nerds: Connection Speed, Network Activity, Buffer Health, Dropped Frames.",
                target?[NSString stringWithFormat:@"%ld sec",(long)target]:@"Auto",
                ceiling?[NSString stringWithFormat:@"%ld Mbps maximum",(long)ceiling]:@"Auto / no override",
                [lcStreamPrefs boolForKey:@"LCStreamingAVPlayerObservedV11"]?@"yes":@"no",
                [lcStreamPrefs objectForKey:@"LCStreamingLastBufferRequestedV11"]?:@"not observed"];
            [UIPasteboard generalPasteboard].string=report;
            UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Streaming state copied"
                message:report preferredStyle:UIAlertControllerStyleAlert];
            [a addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
            UIViewController *p=LCPresenter();
            while (p.presentedViewController) p=p.presentedViewController;
            if (p) [p presentViewController:a animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcStreamState];
'''

def patch_settings(text):
    if MARK in text: raise RuntimeError('v11 streaming settings already installed')
    options=[anchor for anchor in ANCHORS if text.count(anchor)==1]
    if len(options)!=1: raise RuntimeError('YTUHD settings changed: no unique modern/legacy insertion anchor')
    anchor=options[0]
    return text.replace(anchor,anchor+'\n'+SETTINGS_CONTENT,1)

def main():
    if SOURCE.exists(): raise RuntimeError('refusing to overwrite existing streaming module')
    if not SETTINGS.exists():
        print('::warning::YTUHD does not contain Settings.x; experimental streamer skipped.')
        return
    modified=patch_settings(SETTINGS.read_text(encoding='utf-8'))
    SOURCE.parent.mkdir(parents=True,exist_ok=True)
    SOURCE.write_text(SOURCE_CONTENT,encoding='utf-8')
    SETTINGS.write_text(modified,encoding='utf-8')
    print('v11 buffer and client bitrate preferences added (Auto by default; AVPlayer only)')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(f'::error::{exc}',file=sys.stderr);sys.exit(1)
