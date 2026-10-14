#!/usr/bin/env python3
"""PiP Lab v7: audio-safe 2x and guarded visible-error retry.

Runs after v6's source patches on the checked-out YouPiP submodule.
Never changes the original YouTube app, audio session, YTUHD or SponsorBlock.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TWEAK = ROOT / 'Tweaks/YouPiP/Tweak.x'
SETTINGS = ROOT / 'Tweaks/YouPiP/Settings.x'
MARKER = 'LC_PLAYBACK_STABILITY_V7'

# Code is purposely kept in the existing YTPlayerViewController hook introduced
# by the v4 script. This avoids a second Logos hook for the same method.
SOURCE = r'''
#import <QuartzCore/QuartzCore.h>
// LC_PLAYBACK_STABILITY_V7
// 2x is routed ONLY through the active YouTube varispeed controller by default.
// Directly manipulating the underlying AVPlayer's rate may desynchronize its
// audio renderer. All transitions are one-shot and checked against video ID.
static BOOL LCAudioSafeSpeed(void) {
    NSUserDefaults *p = NSUserDefaults.standardUserDefaults;
    return [p objectForKey:@"LCAudioSafeSpeedV7"] == nil ? YES : [p boolForKey:@"LCAudioSafeSpeedV7"];
}
static BOOL LCGuardedRecoveryEnabled(void) {
    NSUserDefaults *p = NSUserDefaults.standardUserDefaults;
    return [p objectForKey:@"LCGuardedRecoveryV7"] == nil ? YES : [p boolForKey:@"LCGuardedRecoveryV7"];
}

// The separately bundled YTHoldForSpeed installs a second recognizer on the
// same YTPlayerView. While our unified edge gesture is active, remove only
// that *gesture instance*, not its code/settings or other tweak features.
static void LCReconcileOriginalHold(YTPlayerViewController *vc, BOOL unifiedEnabled) {
    SEL getter = NSSelectorFromString(@"YTHFSLongPressGesture");
    if (![vc respondsToSelector:getter]) return; // source version varies
    id candidate = ((id (*)(id,SEL))objc_msgSend)(vc, getter);
    if (![candidate isKindOfClass:[UILongPressGestureRecognizer class]]) return;
    UILongPressGestureRecognizer *original = (UILongPressGestureRecognizer *)candidate;
    UIView *playerView = [vc playerView];
    if (!playerView) return;
    if (unifiedEnabled && original.view == playerView) {
        [playerView removeGestureRecognizer:original];
        if (LCVideoGestureDiagnostics()) NSLog(@"[LC v7] Suppressed competing YTHoldForSpeed recognizer (module retained)");
    } else if (!unifiedEnabled && original.view == nil) {
        [playerView addGestureRecognizer:original];
    }
}

static BOOL LCPlayerHasVisibleLoadError(UIView *view, NSInteger depth, NSInteger *budget) {
    if (!view || depth > 9 || *budget <= 0) return NO;
    --(*budget);
    NSString *str = nil;
    if ([view isKindOfClass:[UILabel class]]) str = ((UILabel *)view).text;
    else if ([view isKindOfClass:[UITextView class]]) str = ((UITextView *)view).text;
    if (str.length) {
        NSString *lower = str.lowercaseString;
        // Only match a concrete visible error, not a generic loading spinner.
        if ([lower containsString:@"failed to load"] ||
            ([lower containsString:@"uh oh"] && [lower containsString:@"load"])) return YES;
    }
    for (UIView *child in view.subviews) {
        if (LCPlayerHasVisibleLoadError(child, depth + 1, budget)) return YES;
        if (*budget <= 0) break;
    }
    return NO;
}
'''

# Replaces the single risky rate-change section, not the entire v4 recognizer.
OLD_FALLBACK = r'''        AVPlayer *player = LCPlayerInLayer(self.playerView.layer, 0);
        if (player) {
            self.lcEdgeSavedSpeed = player.rate;
            self.lcEdgeAVPlayer = player;
            self.lcEdgeAVItem = player.currentItem;
            self.lcEdgeHoldMode = 2;
            player.rate = 2.0f;
            if (LCVideoGestureDiagnostics()) NSLog(@"[LC Edge v4] Right 2x via AVPlayer");
        } else if (LCVideoGestureDiagnostics()) {
            NSLog(@"[LC Edge v4] Right: no compatible playback-rate API found");
        }'''
NEW_FALLBACK = r'''        // Default: never accelerate AVPlayer directly behind YouTube's audio pipeline.
        // On versions without an accessible YT varispeed API, fail safely.
        if (LCAudioSafeSpeed()) {
            if (LCVideoGestureDiagnostics())
                NSLog(@"[LC v7] Skipped 2x: native YouTube varispeed control unavailable");
            return;
        }
        // Legacy compatibility option (OFF by default, may lose audio).
        AVPlayer *player = LCPlayerInLayer(self.playerView.layer, 0);
        if (player && player.currentItem && player.currentItem.status == AVPlayerItemStatusReadyToPlay) {
            self.lcEdgeSavedSpeed = player.rate;
            self.lcEdgeAVPlayer = player;
            self.lcEdgeAVItem = player.currentItem;
            self.lcEdgeHoldMode = 2;
            player.rate = 2.0f;
            if (LCVideoGestureDiagnostics()) NSLog(@"[LC v7] Legacy AVPlayer 2x fallback engaged");
        } else if (LCVideoGestureDiagnostics()) {
            NSLog(@"[LC v7] No ready/compatible player for right-edge gesture");
        }'''

OLD_BEGIN = '    if (state != UIGestureRecognizerStateBegan || !LCEdgeHoldEnabled()) return;\n'
NEW_BEGIN = '''    if (state != UIGestureRecognizerStateBegan || !LCEdgeHoldEnabled()) return;
    // An inline recommendation is handled by the feed-preview guard, not speed hooks.
    if (![self activeVideo] || [self isInlinePlaybackActive]) return;
'''

OLD_RESTORE = r'''    if (mode == 1) {
        SEL sel = @selector(varispeedSwitchController:didSelectRate:);'''
NEW_RESTORE = r'''    if (mode == 1) {
        NSString *savedID = self.lcEdgeSpeedVideoID;
        NSString *currentID = nil;
        @try { currentID = [self contentVideoID]; } @catch (NSException *ignored) {}
        // Never restore a rate onto the next video/Short after navigation.
        if (savedID.length && ![savedID isEqualToString:currentID]) {
            self.lcEdgeSpeedVideoID = nil;
            self.lcEdgeAVPlayer = nil;
            self.lcEdgeAVItem = nil;
            return;
        }
        self.lcEdgeSpeedVideoID = nil;
        SEL sel = @selector(varispeedSwitchController:didSelectRate:);'''

OLD_NATIVE = r'''                self.lcEdgeSavedSpeed = previous;
                self.lcEdgeHoldMode = 1;
                ((void (*)(id,SEL,id,float))objc_msgSend)(self, set, speedController, 2.0f);'''
NEW_NATIVE = r'''                self.lcEdgeSavedSpeed = previous;
                @try { self.lcEdgeSpeedVideoID = [[self contentVideoID] copy]; }
                @catch (NSException *ignored) { self.lcEdgeSpeedVideoID = nil; }
                self.lcEdgeHoldMode = 1;
                // Call YouTube's selected speed route once (audio/video together).
                if (fabsf(previous - 2.0f) > 0.01f)
                    ((void (*)(id,SEL,id,float))objc_msgSend)(self, set, speedController, 2.0f);'''

OLD_REFRESH = r'''%new(v@:)
- (void)lcEdgeRefreshHold {
    if (!LCEdgeHoldEnabled()) {'''
NEW_REFRESH = r'''%new(v@:)
- (void)lcEdgeRefreshHold {
    LCReconcileOriginalHold(self, LCEdgeHoldEnabled() && LCAudioSafeSpeed());
    if (!LCEdgeHoldEnabled()) {'''

OLD_LAYOUT = r'''- (void)viewDidLayoutSubviews {
    %orig;
    [self lcEdgeRefreshHold];
}'''
NEW_LAYOUT = r'''- (void)viewDidLayoutSubviews {
    %orig;
    [self lcEdgeRefreshHold];
    [self lcCheckVisibleLoadErrorV7];
}'''

# Store retry metadata per controller. Reset when a new video ID is selected.
PROPERTY_ANCHOR = '%property (nonatomic, retain) AVPlayerItem *lcEdgeAVItem;\n'
PROPERTIES = '''%property (nonatomic, copy) NSString *lcEdgeSpeedVideoID;
%property (nonatomic, copy) NSString *lcRecoveryVideoIDV7;
%property (nonatomic, assign) BOOL lcRecoveryTriedV7;
%property (nonatomic, assign) BOOL lcRecoveryPendingV7;
%property (nonatomic, assign) CFTimeInterval lcRecoveryNextCheckV7;
'''

RETRY_METHOD = r'''
// v7: one error-triggered retry per VIDEO ID. No periodic timers; check only on
// existing layout callbacks and only while this watch player is visible.
%new(v@:)
- (void)lcCheckVisibleLoadErrorV7 {
    if (!LCGuardedRecoveryEnabled() || !self.isViewLoaded || !self.view.window) return;
    CFTimeInterval now = CACurrentMediaTime();
    if (now < self.lcRecoveryNextCheckV7) return;
    self.lcRecoveryNextCheckV7 = now + 1.0; // bounded traversal, at most 1/sec

    NSString *videoID = nil;
    @try { videoID = [self contentVideoID]; } @catch (NSException *ignored) {}
    if (!videoID.length || [self isInlinePlaybackActive]) return;
    if (![self.lcRecoveryVideoIDV7 isEqualToString:videoID]) {
        self.lcRecoveryVideoIDV7 = [videoID copy];
        self.lcRecoveryTriedV7 = NO;
        self.lcRecoveryPendingV7 = NO;
    }
    if (self.lcRecoveryTriedV7 || self.lcRecoveryPendingV7) return;
    NSInteger budget = 240;
    if (!LCPlayerHasVisibleLoadError(self.view, 0, &budget)) return;
    self.lcRecoveryTriedV7 = YES;
    self.lcRecoveryPendingV7 = YES;
    if (LCVideoGestureDiagnostics()) NSLog(@"[LC v7] Visible load failure on %@; scheduling one native replay", videoID);

    NSString *guardVideoID = [videoID copy];
    __weak __typeof(self) weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.6 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        __strong __typeof(weakSelf) vc = weakSelf;
        if (!vc) return;
        vc.lcRecoveryPendingV7 = NO;
        NSString *currentID = nil;
        @try { currentID = [vc contentVideoID]; } @catch (NSException *ignored) {}
        if (![currentID isEqualToString:guardVideoID] || !vc.view.window) return;
        // Abort if the player recovered while we were waiting.
        NSInteger checkBudget = 240;
        if (!LCPlayerHasVisibleLoadError(vc.view, 0, &checkBudget)) return;
        [vc lcEdgeRestorePlayback];
        CGFloat restoreTime = 0;
        @try { restoreTime = [vc currentVideoMediaTime]; } @catch (NSException *ignored) {}
        [vc replay]; // Use YouTube's own replay route, never touch stream URLs.
        // Playback position restore only for established on-demand playback.
        if (isfinite(restoreTime) && restoreTime > 5 && restoreTime < 36000) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.25 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                __strong __typeof(weakSelf) current = weakSelf;
                if (!current || !current.view.window) return;
                NSString *checkID = nil;
                @try { checkID = [current contentVideoID]; } @catch (NSException *ignored) {}
                if (![checkID isEqualToString:guardVideoID]) return;
                [current seekToTime:restoreTime];
            });
        }
    });
}
'''

SETTINGS_PATCH = r'''
    // LC_PLAYBACK_STABILITY_V7
    NSUserDefaults *lcV7Prefs = [NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *safeSpeed = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Audio-safe 2x speed (recommended)"
        titleDescription:@"Uses YouTube's video+audio speed controller. Never directly accelerates AVPlayer when unsupported; also avoids duplicate hold gestures. Keep ON to prevent silent audio dropout. Restart to apply."
        accessibilityIdentifier:nil
        switchOn:[lcV7Prefs objectForKey:@"LCAudioSafeSpeedV7"] == nil ? YES : [lcV7Prefs boolForKey:@"LCAudioSafeSpeedV7"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL value) {
            [lcV7Prefs setBool:value forKey:@"LCAudioSafeSpeedV7"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:safeSpeed];
    YTSettingsSectionItem *retryErrors = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Retry visible 'Failed to load' errors once"
        titleDescription:@"Experimental: if the active watch player shows 'Failed to load', request one native replay for that video, preserving position when possible. No infinite retries. Does not conceal network/codec errors."
        accessibilityIdentifier:nil
        switchOn:[lcV7Prefs objectForKey:@"LCGuardedRecoveryV7"] == nil ? YES : [lcV7Prefs boolForKey:@"LCGuardedRecoveryV7"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL value) {
            [lcV7Prefs setBool:value forKey:@"LCGuardedRecoveryV7"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:retryErrors];
'''


def replace_once(source: str, old: str, new: str, name: str) -> str:
    n = source.count(old)
    if n != 1:
        raise ValueError(f'{name}: expected one exact v6 anchor, got {n}')
    return source.replace(old, new, 1)


def patch_sources(tweak: str, settings: str) -> tuple[str, str]:
    if MARKER in tweak or MARKER in settings:
        raise ValueError('v7 already applied')
    for need in ('LC_EDGE_HOLD_V4', 'LC_PREVIEW_HANDOFF_V5'):
        if need not in tweak:
            raise ValueError(f'Expected earlier source patch: {need}')
    if 'LC_PIP_LAB_V1' not in tweak:
        raise ValueError('Expected PiP Lab v1 setup')
    tweak = replace_once(tweak, '// LC_PREVIEW_HANDOFF_V5', SOURCE + '\n// LC_PREVIEW_HANDOFF_V5', 'v7 helper insertion')
    tweak = replace_once(tweak, OLD_FALLBACK, NEW_FALLBACK, 'unsafe AVPlayer right hold')
    tweak = replace_once(tweak, OLD_BEGIN, NEW_BEGIN, 'right-hold preview guard')
    tweak = replace_once(tweak, OLD_RESTORE, NEW_RESTORE, 'video identity rate restoration')
    tweak = replace_once(tweak, OLD_NATIVE, NEW_NATIVE, 'native video/audio rate path')
    tweak = replace_once(tweak, OLD_REFRESH, NEW_REFRESH, 'recognizer arbitration')
    tweak = replace_once(tweak, PROPERTY_ANCHOR, PROPERTY_ANCHOR + PROPERTIES, 'v7 state properties')
    tweak = replace_once(tweak, OLD_LAYOUT, NEW_LAYOUT, 'load error layout callback')
    tweak = replace_once(tweak, '%new(v@:)\n- (void)lcEdgeRestorePlayback {', RETRY_METHOD + '\n%new(v@:)\n- (void)lcEdgeRestorePlayback {', 'v7 bounded retry method')
    settings = replace_once(settings, '    YTSettingsSectionItem *lcSnapshot =', SETTINGS_PATCH + '\n    YTSettingsSectionItem *lcSnapshot =', 'new safe speed + retry settings')
    if tweak.count(MARKER) != 1 or settings.count(MARKER) != 1:
        raise AssertionError('v7 markers must appear once each')
    return tweak, settings


def main() -> None:
    if not TWEAK.is_file() or not SETTINGS.is_file():
        raise FileNotFoundError('Missing Tweaks/YouPiP source: use recursive Git submodule checkout')
    original_tweak = TWEAK.read_text(encoding='utf-8')
    original_settings = SETTINGS.read_text(encoding='utf-8')
    updated_tweak, updated_settings = patch_sources(original_tweak, original_settings)
    TWEAK.write_text(updated_tweak, encoding='utf-8')
    SETTINGS.write_text(updated_settings, encoding='utf-8')
    print('PiP Lab v7: guarded audio-safe 2x (YouTube varispeed first; AVPlayer fallback OFF by default).')
    print('PiP Lab v7: one-shot UI-visible playback error recovery enabled (may not detect all renderer layouts).')
    print('YTUHD, iSponsorBlock, YouPiP, YTHoldForSpeed and RYD remain included.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'v7 patch error: {exc}', file=sys.stderr)
        sys.exit(1)
