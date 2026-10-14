#!/usr/bin/env python3
"""PiP Lab v4: unified edge-hold gestures for YouTube & Shorts.

This script replaces the v3 Shorts-only patch at build time, without editing
YouPiP's existing logic, or disabling YTUHD, iSponsorBlock, YTHoldForSpeed.

Important: native fast-reverse video is conditional on the AVPlayerItem's
capabilities. This is NOT a reverse-audio implementation; YouTube streams
normally do not expose an AVPlayer that provides reverse audio.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TWEAK = ROOT / 'Tweaks' / 'YouPiP' / 'Tweak.x'
SETTINGS = ROOT / 'Tweaks' / 'YouPiP' / 'Settings.x'
MARKER = 'LC_EDGE_HOLD_V4'

SOURCE_PATCH = r'''
// LC_EDGE_HOLD_V4
// Left edge: attempt native video reverse only if AVPlayer supports -2.0.
//           Reversed audio is NOT implemented by AVPlayer. Unsupported items
//           are left playing normally, with an optional diagnostic message.
// Right edge: temporarily play at 2.0x; return to prior rate on release.
// Both modes share the player; do not switch video rendering engines.
#import <objc/message.h>
#import <math.h>

static BOOL LCEdgeHoldEnabled(void) {
    NSUserDefaults *d = NSUserDefaults.standardUserDefaults;
    return [d objectForKey:@"LCEdgeHoldEnabled"] == nil ? YES : [d boolForKey:@"LCEdgeHoldEnabled"];
}
static BOOL LCNativeReverseVideoEnabled(void) {
    NSUserDefaults *d = NSUserDefaults.standardUserDefaults;
    return [d objectForKey:@"LCNativeReverseVideoEnabled"] == nil ? YES : [d boolForKey:@"LCNativeReverseVideoEnabled"];
}
static BOOL LCVideoGestureDiagnostics(void) {
    return [NSUserDefaults.standardUserDefaults boolForKey:@"LCPlaybackLabPiPDiagnostics"];
}

@interface LCEdgeTouchFilter : NSObject <UIGestureRecognizerDelegate>
@end
@implementation LCEdgeTouchFilter
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)g shouldReceiveTouch:(UITouch *)touch {
    UIView *v = g.view;
    if (!v || v.bounds.size.width < 1.0) return NO;
    CGFloat x = [touch locationInView:v].x;
    return x <= v.bounds.size.width * 0.20 || x >= v.bounds.size.width * 0.80;
}
@end
static id<UIGestureRecognizerDelegate> LCEdgeFilter(void) {
    static LCEdgeTouchFilter *filter;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ filter = [LCEdgeTouchFilter new]; });
    return filter;
}

static AVPlayer *LCPlayerInLayer(CALayer *layer, NSInteger depth) {
    if (!layer || depth > 12) return nil;
    if ([layer isKindOfClass:[AVPlayerLayer class]]) {
        AVPlayer *p = ((AVPlayerLayer *)layer).player;
        if (p && p.currentItem) return p;
    }
    for (CALayer *child in layer.sublayers) {
        AVPlayer *p = LCPlayerInLayer(child, depth + 1);
        if (p) return p;
    }
    return nil;
}

%hook YTPlayerViewController

%property (nonatomic, retain) UILongPressGestureRecognizer *lcEdgeHoldGesture;
%property (nonatomic, assign) NSInteger lcEdgeHoldMode; // 0 none, 1 YouTube speed, 2 AVPlayer speed, 3 AVPlayer video reverse
%property (nonatomic, assign) float lcEdgeSavedSpeed;
%property (nonatomic, retain) AVPlayer *lcEdgeAVPlayer;
%property (nonatomic, retain) AVPlayerItem *lcEdgeAVItem;

%new(v@:)
- (void)lcEdgeRestorePlayback {
    NSInteger mode = self.lcEdgeHoldMode;
    if (!mode) return;
    self.lcEdgeHoldMode = 0;
    if (mode == 1) {
        SEL sel = @selector(varispeedSwitchController:didSelectRate:);
        id speedController = nil;
        @try { speedController = [self valueForKey:@"varispeedController"]; }
        @catch (NSException *ignored) {}
        if (speedController && [self respondsToSelector:sel]) {
            ((void (*)(id,SEL,id,float))objc_msgSend)(self, sel, speedController, self.lcEdgeSavedSpeed);
        }
    } else {
        AVPlayer *player = self.lcEdgeAVPlayer;
        // Do not apply the saved speed to another video after a clip switch.
        if (player && player.currentItem == self.lcEdgeAVItem) {
            player.rate = self.lcEdgeSavedSpeed;
        }
    }
    self.lcEdgeAVPlayer = nil;
    self.lcEdgeAVItem = nil;
}

%new(v@:@)
- (void)lcEdgeHoldChanged:(UILongPressGestureRecognizer *)g {
    UIGestureRecognizerState state = g.state;
    if (state == UIGestureRecognizerStateEnded ||
        state == UIGestureRecognizerStateCancelled ||
        state == UIGestureRecognizerStateFailed) {
        [self lcEdgeRestorePlayback];
        return;
    }
    if (state != UIGestureRecognizerStateBegan || !LCEdgeHoldEnabled()) return;
    if (self.lcEdgeHoldMode) [self lcEdgeRestorePlayback];
    UIView *v = g.view;
    CGFloat w = v.bounds.size.width;
    CGFloat x = [g locationInView:v].x;
    if (w <= 0) return;

    if (x >= w * 0.80) { // RIGHT: temporary forward 2x
        SEL read = @selector(currentPlaybackRateForVarispeedSwitchController:);
        SEL set = @selector(varispeedSwitchController:didSelectRate:);
        id speedController = nil;
        @try { speedController = [self valueForKey:@"varispeedController"]; }
        @catch (NSException *ignored) {}
        if (speedController && [self respondsToSelector:read] && [self respondsToSelector:set]) {
            float previous = ((float (*)(id,SEL,id))objc_msgSend)(self, read, speedController);
            if (isfinite(previous) && previous > 0 && previous <= 16) {
                self.lcEdgeSavedSpeed = previous;
                self.lcEdgeHoldMode = 1;
                ((void (*)(id,SEL,id,float))objc_msgSend)(self, set, speedController, 2.0f);
                if (LCVideoGestureDiagnostics()) NSLog(@"[LC Edge v4] Right 2x via YouTube playback control");
                return;
            }
        }
        AVPlayer *player = LCPlayerInLayer(self.playerView.layer, 0);
        if (player) {
            self.lcEdgeSavedSpeed = player.rate;
            self.lcEdgeAVPlayer = player;
            self.lcEdgeAVItem = player.currentItem;
            self.lcEdgeHoldMode = 2;
            player.rate = 2.0f;
            if (LCVideoGestureDiagnostics()) NSLog(@"[LC Edge v4] Right 2x via AVPlayer");
        } else if (LCVideoGestureDiagnostics()) {
            NSLog(@"[LC Edge v4] Right: no compatible playback-rate API found");
        }
    } else if (x <= w * 0.20 && LCNativeReverseVideoEnabled()) {
        AVPlayer *player = LCPlayerInLayer(self.playerView.layer, 0);
        AVPlayerItem *item = player.currentItem;
        if (player && item && item.canPlayFastReverse) {
            self.lcEdgeSavedSpeed = player.rate;
            self.lcEdgeAVPlayer = player;
            self.lcEdgeAVItem = item;
            self.lcEdgeHoldMode = 3;
            player.rate = -2.0f;
            if (LCVideoGestureDiagnostics()) NSLog(@"[LC Edge v4] Left: native reverse video -2x requested (reverse audio unavailable)");
        } else if (LCVideoGestureDiagnostics()) {
            NSLog(@"[LC Edge v4] Left: reverse video unsupported by active player/item; reverse audio requires PCM buffer");
        }
    }
}

%new(v@:)
- (void)lcEdgeRefreshHold {
    if (!LCEdgeHoldEnabled()) {
        [self lcEdgeRestorePlayback];
        if (self.lcEdgeHoldGesture) {
            [self.lcEdgeHoldGesture.view removeGestureRecognizer:self.lcEdgeHoldGesture];
            self.lcEdgeHoldGesture = nil;
        }
        return;
    }
    UIView *view = self.playerView;
    if (!view) return;
    UILongPressGestureRecognizer *g = self.lcEdgeHoldGesture;
    if (!g) {
        g = [[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(lcEdgeHoldChanged:)];
        g.minimumPressDuration = 0.22;
        g.allowableMovement = 12.0;
        g.numberOfTouchesRequired = 1;
        g.cancelsTouchesInView = NO;
        g.delaysTouchesBegan = NO;
        g.delegate = LCEdgeFilter();
        self.lcEdgeHoldGesture = g;
    }
    if (g.view != view) {
        [g.view removeGestureRecognizer:g];
        [view addGestureRecognizer:g];
        if (LCVideoGestureDiagnostics()) NSLog(@"[LC Edge v4] Attached to %@",NSStringFromClass(view.class));
    }
}

- (void)viewDidAppear:(BOOL)animated {
    %orig;
    [self lcEdgeRefreshHold];
}
- (void)viewDidLayoutSubviews {
    %orig;
    [self lcEdgeRefreshHold];
}
- (void)viewWillDisappear:(BOOL)animated {
    [self lcEdgeRestorePlayback];
    %orig;
}

%end
'''

SETTINGS_PATCH = r'''
    // LC_EDGE_HOLD_V4 — supports regular player + Shorts when hosted by YTPlayerViewController.
    NSUserDefaults *lcEdgePrefs = [NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *lcEdgeHold = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Hold right edge for temporary 2x (videos and Shorts)"
        titleDescription:@"Hold the right outer 20% of the player for 2x; lift to restore previous speed. Available where player rate APIs are exposed. Restart to apply."
        accessibilityIdentifier:nil
        switchOn:[lcEdgePrefs objectForKey:@"LCEdgeHoldEnabled"] ? [lcEdgePrefs boolForKey:@"LCEdgeHoldEnabled"] : YES
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcEdgePrefs setBool:enabled forKey:@"LCEdgeHoldEnabled"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcEdgeHold];
    YTSettingsSectionItem *lcVideoReverse = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Left edge: try native reverse VIDEO (-2x, experimental)"
        titleDescription:@"Only works for AVPlayer-backed videos that support fast reverse. Does NOT reverse audio. Unsupported YouTube streams are unchanged. Restart to apply."
        accessibilityIdentifier:nil
        switchOn:[lcEdgePrefs objectForKey:@"LCNativeReverseVideoEnabled"] ? [lcEdgePrefs boolForKey:@"LCNativeReverseVideoEnabled"] : YES
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcEdgePrefs setBool:enabled forKey:@"LCNativeReverseVideoEnabled"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcVideoReverse];
'''


def insert_before_once(text: str, anchor: str, payload: str, label: str) -> str:
    n = text.count(anchor)
    if n != 1:
        raise RuntimeError(f'{label}: expected 1 insertion anchor, got {n}; review upstream revision')
    return text.replace(anchor, payload + anchor, 1)


def main():
    if not TWEAK.is_file() or not SETTINGS.is_file():
        raise RuntimeError('YouPiP source unavailable; checkout needs submodules: recursive')
    tweak = TWEAK.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')
    if 'LC_PIP_LAB_V1' not in tweak or 'LC_PIP_LAB_V1' not in settings:
        raise RuntimeError('Run apply_lc_pip.py first')
    if MARKER in tweak or MARKER in settings:
        raise RuntimeError('v4 source already applied; refusing duplicate hooks')
    if 'LC_SHORTS_HOLD_2X_V3' in tweak or 'LC_SHORTS_HOLD_2X_V3' in settings:
        raise RuntimeError('v3 source already patched in checkout; use a clean submodule tree')
    tweak = insert_before_once(tweak, '// LC_PIP_LAB_V1: Observe all AVKit PiP start requests', SOURCE_PATCH, 'Tweak.x')
    settings = insert_before_once(settings, '    YTSettingsSectionItem *lcSnapshot =', SETTINGS_PATCH, 'Settings.x')
    assert MARKER in tweak and MARKER in settings
    TWEAK.write_text(tweak, encoding='utf-8')
    SETTINGS.write_text(settings, encoding='utf-8')
    print('PiP Lab v4: edge speed enabled on regular videos and Shorts where YouTube player API is accessible.')
    print('Left edge: *video-only* native fast-reverse attempt for supported AVPlayer content. Reverse audio NOT implemented.')
    print('Preserving: YouPiP, YTUHD, iSponsorBlock, YTHoldForSpeed.')


if __name__ == '__main__':
    try:
        main()
    except Exception as ex:
        print(f'::error::{ex}', file=sys.stderr)
        sys.exit(1)
