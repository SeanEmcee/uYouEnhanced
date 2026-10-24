#!/usr/bin/env python3
"""PiP Lab v14: repair gesture collisions, reliable seek-back, feedback and speed UI.

Apply AFTER v12, before the Theos package step. Patches checked-out submodules
at build time; do not write to the original YouTube binary. Idempotency is
intentionally strict to catch unexpected upstream revisions.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
PIP = ROOT / "Tweaks/YouPiP/Tweak.x"
PIP_SETTINGS = ROOT / "Tweaks/YouPiP/Settings.x"
SPEED = ROOT / "Tweaks/YouSpeed/Tweak.x"
HOLD = ROOT / "Tweaks/YTHoldForSpeed/YTHFSTweak.x"
MARK = "LC_CONTROLS_V14"

def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one matching anchor, found {count}")
    return text.replace(old, new, 1)

METHODS = r'''
// LC_CONTROLS_V14: feedback is owned by our unified recognizer, NOT by
// YTHoldForSpeed (whose competing gesture is detached by v7).
%new(v@:@)
- (void)lcHoldFeedbackV14:(NSString *)message {
    UIView *host = self.playerView;
    if (!host || !self.view.window) return;
    const NSInteger kFeedbackTag = 802014;
    UILabel *label = (UILabel *)[host viewWithTag:kFeedbackTag];
    if (![label isKindOfClass:[UILabel class]]) {
        label = [[UILabel alloc] initWithFrame:CGRectZero];
        label.tag = kFeedbackTag;
        label.textAlignment = NSTextAlignmentCenter;
        label.font = [UIFont boldSystemFontOfSize:17.0];
        label.textColor = [UIColor whiteColor];
        label.backgroundColor = [[UIColor blackColor] colorWithAlphaComponent:0.65];
        label.layer.cornerRadius = 9.0;
        label.layer.masksToBounds = YES;
        label.userInteractionEnabled = NO;
        [host addSubview:label];
    }
    if (message.length) {
        label.text = message;
        label.hidden = NO;
        CGFloat width = MIN(host.bounds.size.width - 24, 100);
        label.frame = CGRectMake((host.bounds.size.width-width)/2.0, 16.0, width, 36.0);
        if ([NSUserDefaults.standardUserDefaults objectForKey:@"LCHoldHapticsV14"] == nil ||
            [NSUserDefaults.standardUserDefaults boolForKey:@"LCHoldHapticsV14"]) {
            UIImpactFeedbackGenerator *feedback =
                [[UIImpactFeedbackGenerator alloc] initWithStyle:UIImpactFeedbackStyleMedium];
            [feedback prepare];
            [feedback impactOccurred];
        }
    } else {
        label.hidden = YES;
    }
}

%new(v@:@)
- (void)lcRewindTickV14:(NSTimer *)timer {
    if (self.lcEdgeHoldMode != 4 || !self.view.window ||
        [self isInlinePlaybackActive] || ![self activeVideo]) {
        [self lcEdgeRestorePlayback];
        return;
    }
    NSString *currentID = nil;
    @try { currentID = [self contentVideoID]; } @catch (NSException *ignored) {}
    if (self.lcRewindVideoIDV14.length &&
        ![self.lcRewindVideoIDV14 isEqualToString:currentID]) {
        [self lcEdgeRestorePlayback];
        return;
    }
    CGFloat now = 0;
    @try { now = [self currentVideoMediaTime]; } @catch (NSException *ignored) {}
    if (!isfinite(now) || now <= 0.05) return;
    // Use YouTube's own seek route. Most DASH/HAM streams cannot play at a
    // negative AVPlayer rate. Seeking retains normal video/audio decoders.
    [self seekToTime:MAX(0.0, now - 0.85)];
}
'''

def patch_pip(text):
    if MARK in text:
        raise ValueError("YouPiP v14 already applied")
    for required in ("LC_EDGE_HOLD_V4", "LC_PLAYBACK_STABILITY_V7", "LC_4K_PERFORMANCE_V10"):
        if required not in text:
            raise ValueError(f"Previous patch missing: {required}")

    text = once(text,
        "%property (nonatomic, retain) AVPlayerItem *lcEdgeAVItem;",
        "%property (nonatomic, retain) AVPlayerItem *lcEdgeAVItem;\n"
        "%property (nonatomic, retain) NSTimer *lcRewindTimerV14;\n"
        "%property (nonatomic, copy) NSString *lcRewindVideoIDV14;",
        "v14 gesture state")
    text = once(text,
        "@property (nonatomic, retain) AVPlayerItem *lcEdgeAVItem;\\n"
        "@property (nonatomic, copy) NSString *lcEdgeSpeedVideoID;",
        "@property (nonatomic, retain) AVPlayerItem *lcEdgeAVItem;\\n"
        "@property (nonatomic, retain) NSTimer *lcRewindTimerV14;\\n"
        "@property (nonatomic, copy) NSString *lcRewindVideoIDV14;\\n"
        "@property (nonatomic, copy) NSString *lcEdgeSpeedVideoID;",
        "v14 compile-visible state")
    text = once(text,
        "- (void)lcEdgeRestorePlayback;",
        "- (void)lcHoldFeedbackV14:(NSString *)message;\n"
        "- (void)lcRewindTickV14:(NSTimer *)timer;\n"
        "- (void)lcEdgeRestorePlayback;",
        "v14 compile declarations")
    text = once(text, "%new(v@:)\n- (void)lcEdgeRestorePlayback {",
        METHODS + "\n%new(v@:)\n- (void)lcEdgeRestorePlayback {",
        "v14 methods")

    text = once(text,
        "    self.lcEdgeHoldMode = 0;\n    if (mode == 1) {",
        "    self.lcEdgeHoldMode = 0;\n"
        "    [self.lcRewindTimerV14 invalidate];\n"
        "    self.lcRewindTimerV14 = nil;\n"
        "    self.lcRewindVideoIDV14 = nil;\n"
        "    [self lcHoldFeedbackV14:nil];\n"
        "    if (mode == 4) return; // rewind only sought; rate was untouched\n"
        "    if (mode == 1) {",
        "v14 restore/cleanup")

    text = once(text,
        "                if (fabsf(previous - 2.0f) > 0.01f)\n"
        "                    ((void (*)(id,SEL,id,float))objc_msgSend)(self, set, speedController, 2.0f);",
        "                if (fabsf(previous - 2.0f) > 0.01f)\n"
        "                    ((void (*)(id,SEL,id,float))objc_msgSend)(self, set, speedController, 2.0f);\n"
        "                [self lcHoldFeedbackV14:@\"2×\"];",
        "v14 speed feedback")

    text = once(text,
        "    return x <= v.bounds.size.width * 0.20 || x >= v.bounds.size.width * 0.80;",
        "    return x <= v.bounds.size.width * 0.43 || x >= v.bounds.size.width * 0.57;",
        "v14 left/right gesture hit zone")
    text = once(text, "    if (x >= w * 0.80) { // RIGHT: temporary forward 2x",
        "    if (x >= w * 0.57) { // RIGHT: temporary forward 2x",
        "v14 right hit zone")

    start = "    } else if (x <= w * 0.20 && LCNativeReverseVideoEnabled()) {"
    end = "\n    }\n}\n\n%new(v@:)\n- (void)lcEdgeRefreshHold {"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("v14 left-hold original section not uniquely found")
    left = r'''    } else if (x <= w * 0.43 && LCNativeReverseVideoEnabled()) {
        // Actual backward scrubbing instead of unsupported AVPlayer -2x.
        if (![self activeVideo] || [self isInlinePlaybackActive]) return;
        NSString *videoID = nil;
        @try { videoID = [self contentVideoID]; } @catch (NSException *ignored) {}
        if (!videoID.length) return;
        self.lcEdgeHoldMode = 4;
        self.lcRewindVideoIDV14 = [videoID copy];
        [self lcHoldFeedbackV14:@"⏪ 2×"];
        [self lcRewindTickV14:nil];
        self.lcRewindTimerV14 = [NSTimer scheduledTimerWithTimeInterval:0.40
            target:self selector:@selector(lcRewindTickV14:)
            userInfo:nil repeats:YES];
        if (LCVideoGestureDiagnostics())
            NSLog(@"[LC v14] Left edge seek-back active");
'''
    i = text.index(start)
    j = text.index(end, i)
    text = text[:i] + left + text[j:]

    text = once(text,
        "            player.rate = 2.0f;\n            if (LCVideoGestureDiagnostics())",
        "            player.rate = 2.0f;\n"
        "            [self lcHoldFeedbackV14:@\"2×\"];\n"
        "            if (LCVideoGestureDiagnostics())",
        "v14 optional AVPlayer compatibility feedback")
    return text

def patch_pip_settings(text):
    if MARK in text:
        raise ValueError("Settings v14 already applied")
    text = once(text,
        'switchItemWithTitle:@"Left edge: try native reverse VIDEO (-2x, experimental)"',
        'switchItemWithTitle:@"Hold left side to rewind (seek backward)"',
        "v14 rewind setting title")
    text = once(text,
        'titleDescription:@"Only works for AVPlayer-backed videos that support fast reverse. Does NOT reverse audio. Unsupported YouTube streams are unchanged. Restart to apply."',
        'titleDescription:@"Seeks backward while held, using the current YouTube player, including DASH/HAM streams. Reverse audio is not available. Restart to apply."',
        "v14 rewind setting description")
    return text.replace('    // LC_EDGE_HOLD_V4 — supports regular player + Shorts when hosted by YTPlayerViewController.',
                        '    // LC_CONTROLS_V14: improved left seek-back and 2x hold feedback.\n'
                        '    // LC_EDGE_HOLD_V4 — supports regular player + Shorts when hosted by YTPlayerViewController.',1)

def patch_speed(text):
    if "LC_SPEED_UI_V14" in text:
        raise ValueError("YouSpeed v14 already applied")
    # The center item is the text-value label; on the pinned source it appears
    # as a blank tappable-looking slot between '-' and '+'. Omit that view but
    # retain functional plus/minus and speed presets. Slider remains intact.
    text = once(text, "    [contentView addSubview:currentValueLabel];",
                "    // LC_SPEED_UI_V14: omit empty center value slot.\n"
                "    // Speed remains visible in YouSpeed's overlay button.\n",
                "v14 blank middle slot")
    # Presets must no longer depend on the now-hidden label's zero frame.
    text = once(text,
        "    CGFloat buttonY = currentValueLabel.frame.origin.y + currentValueLabel.frame.size.height + 15;",
        "    CGFloat buttonY = slider.frame.origin.y + slider.frame.size.height + 35;",
        "v14 preset placement")
    # More Speeds uses a custom internalSetRate path above 2x. For <=2x,
    # defer to the YouTube HAM player's normal synchronized A/V setter.
    text = once(text,
        '''- (void)setRate:(float)newRate {
    float rate = [[self valueForKey:@"_rate"] floatValue];''',
        '''- (void)setRate:(float)newRate {
    // LC_NATIVE_AUDIO_2X_V14: stock HAM speed route preserves A/V sync.
    if (newRate > 0.0f && newRate <= 2.0f) { %orig; return; }
    float rate = [[self valueForKey:@"_rate"] floatValue];''',
        "v14 <=2x native A/V path")
    return text

def patch_hold(text):
    if "LC_HOLD_ROTATION_V14" in text:
        raise ValueError("YTHoldForSpeed v14 already applied")
    # v7 suppresses this recognizer, but its delayed AUTO APPLY action can
    # still fire on cold launch/orientation handoff and overwrite playback rate.
    # Preserve auto-apply if the unified LC edge gesture was explicitly disabled.
    original = "    if ([YTHFSPrefsManager autoApplyRateEnabled] && self.YTHFSNeedsAutoApply &&"
    replacement = (
        "    // LC_HOLD_ROTATION_V14: avoid the second, delayed speed writer while\n"
        "    // the unified gesture owns speed changes. Cold-launch rotation safe.\n"
        "    NSUserDefaults *prefsV14 = [NSUserDefaults standardUserDefaults];\n"
        "    BOOL unifiedV14 = [prefsV14 objectForKey:@\"LCEdgeHoldEnabled\"] == nil ? YES :\n"
        "                      [prefsV14 boolForKey:@\"LCEdgeHoldEnabled\"];\n"
        "    if (!unifiedV14 && [YTHFSPrefsManager autoApplyRateEnabled] && self.YTHFSNeedsAutoApply &&"
    )
    return once(text, original, replacement, "v14 YTHFS auto speed collision")

def main():
    files = [
        (PIP, patch_pip),
        (PIP_SETTINGS, patch_pip_settings),
        (SPEED, patch_speed),
        (HOLD, patch_hold),
    ]
    for file, _ in files:
        if not file.is_file():
            raise FileNotFoundError(f"Missing submodule source: {file}; use recursive checkout")
    # All-or-nothing: validate and transform before writing any file.
    revisions = [(file, fn(file.read_text(encoding="utf-8"))) for file, fn in files]
    for file, modified in revisions:
        file.write_text(modified, encoding="utf-8")
        print(f"v14 patched {file.relative_to(ROOT)}")
    print("v14: long-hold feedback, left-side seek-back, clear speed UI and rotation rate arbitration.")
    print("2K 2x still depends on native decoder throughput; no false buffering or audio hacks.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
