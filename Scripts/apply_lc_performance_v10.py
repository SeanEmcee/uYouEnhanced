#!/usr/bin/env python3
# v10: read-only 4K/2x snapshot; does not change streaming.
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
TWEAK=ROOT/'Tweaks/YouPiP/Tweak.x'
SETTINGS=ROOT/'Tweaks/YouPiP/Settings.x'
MARK='LC_4K_PERFORMANCE_V10'
TWEAK_ANCHOR='%hook YTPlayerViewController\n\n%property (nonatomic, retain) UILongPressGestureRecognizer *lcEdgeHoldGesture;'
TWEAK_SOURCE=r'''
// LC_4K_PERFORMANCE_V10
// Read-only diagnostic. Local controller pointer is weak, no polling, no API calls.
// Only AVPlayer-backed streams yield access logs; YouTube's custom path might not.
static __weak YTPlayerViewController *lcV10RecentPlayer=nil;
NSString *LCUHDCollectSnapshotV10(void) {
    YTPlayerViewController *vc=lcV10RecentPlayer;
    NSMutableString *report=[NSMutableString stringWithString:@"PiP Lab v10 4K/2x diagnostic\n"];
    if (!vc || !vc.isViewLoaded || !vc.view.window)
        return [report stringByAppendingString:@"No visible watch player recorded. Play a video first.\nUse YouTube Stats for Nerds for network/codec.\n"];
    NSString *videoID=nil;
    @try { videoID=[vc contentVideoID]; } @catch (NSException *ignored) {}
    // Don't export video IDs: diagnostic stays generic.
    [report appendFormat:@"Video identified: %@\n", videoID.length ? @"yes" : @"no"];
    AVPlayer *player=LCPlayerInLayer(vc.playerView.layer,0);
    if (!player || !player.currentItem) {
        [report appendString:@"AVPlayer layer: not exposed (custom YouTube renderer).\n"];
        [report appendString:@"Open Stats for Nerds: compare Connection Speed, Buffer Health, Dropped Frames, Codecs, and HV hardware decoder indicator.\n"];
        return report;
    }
    AVPlayerItem *item=player.currentItem;
    [report appendFormat:@"AVPlayer: present; rate=%.2fx; item status=%ld\n",player.rate,(long)item.status];
    [report appendFormat:@"Buffer: empty=%@ likelyToKeepUp=%@ full=%@\n",item.playbackBufferEmpty?@"yes":@"no",item.playbackLikelyToKeepUp?@"yes":@"no",item.playbackBufferFull?@"yes":@"no"];
    double now=CMTimeGetSeconds(player.currentTime);
    double ahead=0.0;
    if (isfinite(now)) {
        for (NSValue *entry in item.loadedTimeRanges) {
            CMTimeRange r=entry.CMTimeRangeValue;
            double start=CMTimeGetSeconds(r.start), end=CMTimeGetSeconds(CMTimeRangeGetEnd(r));
            if (isfinite(start)&&isfinite(end)&&start<=now&&end>=now)
                ahead=MAX(ahead,end-now);
        }
    }
    [report appendFormat:@"AVPlayer buffer ahead: %.1f sec\n",ahead];
    AVPlayerItemAccessLogEvent *event=item.accessLog.events.lastObject;
    if (event) {
        [report appendFormat:@"Observed network bitrate: %.2f Mbps\n",event.observedBitrate/1000000.0];
        [report appendFormat:@"Indicated stream bitrate: %.2f Mbps\n",event.indicatedBitrate/1000000.0];
        [report appendFormat:@"Stalls: %ld; transferred: %.1f MB\n",(long)event.numberOfStalls,event.numberOfBytesTransferred/1000000.0];
    } else [report appendString:@"AVPlayer access log: unavailable.\n"];
    [report appendString:@"AVPlayer logs may exclude YouTube's native decoder and streaming path; Stats for Nerds remains authoritative.\n"];
    return report;
}
'''
SETTINGS_SOURCE=r'''
    // LC_4K_PERFORMANCE_V10
    YTSettingsSectionItem *lcV10Snapshot=[%c(YTSettingsSectionItem)
        itemWithTitle:@"4K/2x playback diagnostic (copy)"
        titleDescription:@"Read-only player and buffer details. Copies a snapshot; use YouTube Stats for Nerds for actual codec and network measurements."
        accessibilityIdentifier:nil
        detailTextBlock:nil
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            NSString *snapshot=LCUHDCollectSnapshotV10();
            [UIPasteboard generalPasteboard].string=snapshot;
            UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"4K/2x diagnostic (copied)"
                message:snapshot preferredStyle:UIAlertControllerStyleAlert];
            [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
            UIViewController *presenter=LCPresenter();
            if (presenter) [presenter presentViewController:alert animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcV10Snapshot];
'''
def insert_one(body,old,new,what):
    n=body.count(old)
    if n!=1: raise RuntimeError(f'{what}: expected one anchor; got {n}')
    return body.replace(old,new,1)
def patch_sources(tweak,settings):
    if MARK in tweak or MARK in settings: raise RuntimeError('v10 already applied')
    if 'LC_MINIPLAYER_TOUCH_FIX_V9' not in tweak or 'LC_PLAYBACK_STABILITY_V7' not in tweak:
        raise RuntimeError('Expected v7 and v9 patches; run the full workflow in order')
    tweak=insert_one(tweak,TWEAK_ANCHOR,TWEAK_SOURCE+'\n'+TWEAK_ANCHOR,'v10 source position')
    tweak=insert_one(tweak,'    [self lcCheckVisibleLoadErrorV7];','    [self lcCheckVisibleLoadErrorV7];\n    lcV10RecentPlayer=self;','v10 active player reference')
    settings=insert_one(settings,'    YTSettingsSectionItem *lcSnapshot =',SETTINGS_SOURCE+'\n    YTSettingsSectionItem *lcSnapshot =','v10 button')
    settings='#import <AVFoundation/AVFoundation.h>\nextern NSString *LCUHDCollectSnapshotV10(void);\n'+settings
    if tweak.count(MARK)!=1 or settings.count(MARK)!=1:raise RuntimeError('v10 duplicated')
    return tweak,settings
if __name__=='__main__':
    try:
        a,b=patch_sources(TWEAK.read_text(),SETTINGS.read_text())
        TWEAK.write_text(a);SETTINGS.write_text(b)
        print('v10 playback snapshot available in YouPiP. Read-only; no automatic speed/network hacks.')
    except Exception as e:
        print(f'::error::{e}',file=sys.stderr);sys.exit(1)
