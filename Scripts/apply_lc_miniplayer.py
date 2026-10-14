#!/usr/bin/env python3
"""PiP Lab v8: isolate native floating MiniPlayer from speed-gesture recognizers.

Runs AFTER v7 on a fresh recursive submodule checkout. Does not change
YouTube's native pan/pinch handlers, video renderer, or preferred speed path.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TWEAK = ROOT / 'Tweaks' / 'YouPiP' / 'Tweak.x'
SETTINGS = ROOT / 'Tweaks' / 'YouPiP' / 'Settings.x'
MARKER = 'LC_MINIPLAYER_GESTURE_GUARD_V8'

HELPERS = r'''
// LC_MINIPLAYER_GESTURE_GUARD_V8
// YouTube's floating MiniPlayer owns its pinch/drag gestures. Our custom
// press-to-speed recognizers must NEVER join their arbitration while floating.
// Changes only our recognizers, not native YouTube MiniPlayer constraints.
#import <QuartzCore/QuartzCore.h>
// v7 helpers are defined later; explicit prototypes keep Clang/Logos happy.
static BOOL LCAudioSafeSpeed(void);
static BOOL LCGuardedRecoveryEnabled(void);
static void LCReconcileOriginalHold(YTPlayerViewController *vc, BOOL unifiedEnabled);
static BOOL LCPlayerHasVisibleLoadError(UIView *view, NSInteger depth, NSInteger *budget);

static BOOL LCMiniplayerGuardV8(void) {
    NSUserDefaults *prefs = [NSUserDefaults standardUserDefaults];
    return [prefs objectForKey:@"LCMiniplayerGuardV8"] == nil
        ? YES : [prefs boolForKey:@"LCMiniplayerGuardV8"];
}

static BOOL LCIsFloatingMiniV8(YTPlayerViewController *vc) {
    if (!vc || !vc.isViewLoaded) return NO;
    UIView *player = [vc playerView];
    if (!player || !player.window) return NO;
    // YouTube's feed preview also needs native gestures, not hold-to-speed.
    if ([vc isInlinePlaybackActive]) return YES;

    UIView *current = player;
    for (NSInteger depth = 0; current && depth < 14; ++depth, current = current.superview) {
        NSString *className = NSStringFromClass(current.class).lowercaseString;
        if ([className containsString:@"miniplayer"] ||
            [className containsString:@"mini_player"] ||
            [className containsString:@"floatingplayer"] ||
            [className containsString:@"floating_player"])
            return YES;
    }

    // Fallback for YouTube revisions that rename MiniPlayer container classes.
    // Unlike regular watch player and Shorts, a floating player covers only a
    // portion of both the window width and height. Require BOTH constraints.
    CGRect rect = [player convertRect:player.bounds toView:player.window];
    CGRect windowBounds = player.window.bounds;
    if (windowBounds.size.width < 1 || windowBounds.size.height < 1) return NO;
    CGFloat widthRatio = CGRectGetWidth(rect) / CGRectGetWidth(windowBounds);
    CGFloat heightRatio = CGRectGetHeight(rect) / CGRectGetHeight(windowBounds);
    return widthRatio < 0.94 && heightRatio < 0.70;
}
'''

OLD_REFRESH = '''%new(v@:)
- (void)lcEdgeRefreshHold {
    LCReconcileOriginalHold(self, LCEdgeHoldEnabled() && LCAudioSafeSpeed());
    if (!LCEdgeHoldEnabled()) {'''
NEW_REFRESH = '''%new(v@:)
- (void)lcEdgeRefreshHold {
    // v8: quarantine MiniPlayer from custom hold recognizers. Pinch and drag
    // remain entirely owned by YouTube's own MiniPlayer interaction controller.
    if (LCMiniplayerGuardV8() && LCIsFloatingMiniV8(self)) {
        [self lcEdgeRestorePlayback];
        if (self.lcEdgeHoldGesture.view) {
            [self.lcEdgeHoldGesture.view removeGestureRecognizer:self.lcEdgeHoldGesture];
            if (LCVideoGestureDiagnostics())
                NSLog(@"[LC v8] Detached edge hold from floating MiniPlayer");
        }
        // Keep YTHoldForSpeed *library* installed but stop its competing
        // UILongPressGestureRecognizer while floating. Normal playback untouched.
        LCReconcileOriginalHold(self, YES);
        return;
    }
    LCReconcileOriginalHold(self, LCEdgeHoldEnabled() && LCAudioSafeSpeed());
    if (!LCEdgeHoldEnabled()) {'''

OLD_BEGAN = '''    if (state != UIGestureRecognizerStateBegan || !LCEdgeHoldEnabled()) return;
    // An inline recommendation is handled by the feed-preview guard, not speed hooks.
    if (![self activeVideo] || [self isInlinePlaybackActive]) return;'''
NEW_BEGAN = '''    if (state != UIGestureRecognizerStateBegan || !LCEdgeHoldEnabled()) return;
    // A view can transition into MiniPlayer *after* recognizing a touch.
    // Guard again here so a late callback cannot change its playback speed.
    if (LCMiniplayerGuardV8() && LCIsFloatingMiniV8(self)) return;
    // An inline recommendation is handled by the feed-preview guard, not speed hooks.
    if (![self activeVideo] || [self isInlinePlaybackActive]) return;'''

OLD_FILTER = '''    return x <= v.bounds.size.width * 0.20 || x >= v.bounds.size.width * 0.80;
}
@end'''
NEW_FILTER = '''    return x <= v.bounds.size.width * 0.20 || x >= v.bounds.size.width * 0.80;
}
// Do not force YouTube's own pinch or pan to fail while our edge-hold exists.
// The MiniPlayer's recognizers still retain final control of their gestures.
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gesture
    shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer *)other {
    return [other isKindOfClass:[UIPinchGestureRecognizer class]] ||
           [other isKindOfClass:[UIPanGestureRecognizer class]];
}
@end'''

# Capture the MiniPlayer transition even when the watch VC is not relaid out.
# The playerView can move between containers without viewDidLayoutSubviews
# firing on its owning YTPlayerViewController.
VIEW_HOOK = r'''
// v8: send one refresh whenever the player view is attached to a different
// container. This is NOT a gesture hook or custom resizing implementation.
%hook YTPlayerView
- (void)didMoveToSuperview {
    %orig;
    if (!LCMiniplayerGuardV8()) return;
    __weak YTPlayerView *weakView = self;
    dispatch_async(dispatch_get_main_queue(), ^{
        YTPlayerView *v = weakView;
        if (!v) return;
        UIResponder *next = [v nextResponder];
        NSInteger maxDepth = 18;
        while (next && maxDepth-- > 0) {
            if ([next isKindOfClass:%c(YTPlayerViewController)]) {
                YTPlayerViewController *vc = (YTPlayerViewController *)next;
                SEL action = NSSelectorFromString(@"lcEdgeRefreshHold");
                if ([vc respondsToSelector:action])
                    ((void (*)(id, SEL))objc_msgSend)(vc, action);
                break;
            }
            next = [next nextResponder];
        }
    });
}
%end
'''

SETTINGS_PATCH = r'''
    // LC_MINIPLAYER_GESTURE_GUARD_V8
    NSUserDefaults *lcMiniPrefs = [NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *lcMiniGuard = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Protect floating MiniPlayer pinch and drag (v8)"
        titleDescription:@"Recommended ON. Disables our custom hold-to-speed recognizers only while the player is floating, so YouTube's native pinch, double-tap and dragging can work independently. Restart after changing."
        accessibilityIdentifier:nil
        switchOn:[lcMiniPrefs objectForKey:@"LCMiniplayerGuardV8"] == nil ? YES : [lcMiniPrefs boolForKey:@"LCMiniplayerGuardV8"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL value) {
            [lcMiniPrefs setBool:value forKey:@"LCMiniplayerGuardV8"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcMiniGuard];
'''


def replace_once(source: str, original: str, updated: str, label: str) -> str:
    occurrences = source.count(original)
    if occurrences != 1:
        raise RuntimeError(f'{label}: expected exactly one v7 source anchor, found {occurrences}')
    return source.replace(original, updated, 1)


def patch_sources(tweak: str, settings: str) -> tuple[str, str]:
    if MARKER in tweak or MARKER in settings:
        raise RuntimeError('v8 already applied; refusing to duplicate hooks')
    if 'LC_PLAYBACK_STABILITY_V7' not in tweak or 'LC_EDGE_HOLD_V4' not in tweak:
        raise RuntimeError('Expected v7 patch before applying MiniPlayer gesture guard')
    tweak = replace_once(tweak, OLD_REFRESH, NEW_REFRESH, 'v8 floating miniplayer guard')
    tweak = replace_once(tweak, OLD_BEGAN, NEW_BEGAN, 'v8 late gesture guard')
    tweak = replace_once(tweak, OLD_FILTER, NEW_FILTER, 'v8 native pan/pinch coexistence')
    tweak = replace_once(tweak, '%hook YTPlayerViewController\n', HELPERS + '\n' + VIEW_HOOK + '\n%hook YTPlayerViewController\n', 'v8 miniplayer helpers and view transition hook')
    settings = replace_once(settings, '    YTSettingsSectionItem *lcSnapshot =', SETTINGS_PATCH + '\n    YTSettingsSectionItem *lcSnapshot =', 'v8 settings toggle')
    if tweak.count(MARKER) != 1 or settings.count(MARKER) != 1:
        raise AssertionError('v8 markers missing or duplicated')
    return tweak, settings


def main():
    if not TWEAK.is_file() or not SETTINGS.is_file():
        raise FileNotFoundError('Missing YouPiP submodule; enable recursive checkout')
    original_tweak = TWEAK.read_text(encoding='utf-8')
    original_settings = SETTINGS.read_text(encoding='utf-8')
    patched_tweak, patched_settings = patch_sources(original_tweak, original_settings)
    TWEAK.write_text(patched_tweak, encoding='utf-8')
    SETTINGS.write_text(patched_settings, encoding='utf-8')
    print('v8 MiniPlayer: isolates floating player from right/left speed hold gestures.')
    print('v8 MiniPlayer: original YouTube pinch, drag, and double-tap are not modified.')
    print('Preserved: PiP, YTHoldForSpeed, Return Dislikes, YTUHD=ON, iSponsorBlock=ON.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'::error::{error}', file=sys.stderr)
        sys.exit(1)
