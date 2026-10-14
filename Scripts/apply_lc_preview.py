#!/usr/bin/env python3
"""PiP Lab v5: narrowly scoped feed-preview audio handoff guard.

Run *after* apply_lc_pip.py and v4 apply_lc_shorts.py. Patches the
in-tree YouPiP source already hooked by v4, not the YouTube IPA binary.

This is a best-effort mitigation of arichornlover/uYouEnhanced issues #880
and #979. It mutes stale YouTube feed preview players when a full watch
player appears; it pauses only AVPlayer layers tied to the stale preview.
It does NOT alter the process-wide AVAudioSession, background playback,
PiP, main video, SponsorBlock, YTUHD, or the original gestures.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TWEAK = ROOT / 'Tweaks' / 'YouPiP' / 'Tweak.x'
SETTINGS = ROOT / 'Tweaks' / 'YouPiP' / 'Settings.x'
MARKER = 'LC_PREVIEW_HANDOFF_V5'

SOURCE_PATCH = r'''
// LC_PREVIEW_HANDOFF_V5 — addresses feed-preview audio continuing after opening watch view.
// Guard targets only an inline feed preview, not the newly opened watch player.
// No global audio-session manipulation or playback-mode / PiP changes.
static BOOL LCPreviewHandoffEnabled(void) {
    NSUserDefaults *prefs = [NSUserDefaults standardUserDefaults];
    return [prefs objectForKey:@"LCPreviewHandoffEnabled"] == nil ? YES :
        [prefs boolForKey:@"LCPreviewHandoffEnabled"];
}

static NSHashTable<YTPlayerViewController *> *LCPreviewSeenPlayers(void) {
    static NSHashTable<YTPlayerViewController *> *seen;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ seen = [NSHashTable weakObjectsHashTable]; });
    return seen;
}

static NSMapTable<YTPlayerViewController *, NSString *> *LCPreviewSeenVideoIDs(void) {
    static NSMapTable<YTPlayerViewController *, NSString *> *ids;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{ ids = [NSMapTable weakToStrongObjectsMapTable]; });
    return ids;
}

static void LCRememberFeedPreview(YTPlayerViewController *player) {
    [LCPreviewSeenPlayers() addObject:player];
    NSString *videoID = nil;
    @try { videoID = [player contentVideoID]; } @catch (NSException *ignored) {}
    if (videoID.length) [LCPreviewSeenVideoIDs() setObject:[videoID copy] forKey:player];
}

static BOOL LCIsFeedPreviewPlayer(YTPlayerViewController *player) {
    if (!player) return NO;
    // YouTubeHeader documents the inline overlay class alongside the
    // standard watch overlay. Prefer this to generic visibility guessing.
    @try {
        id overlay = [player activeVideoPlayerOverlay];
        NSString *type = NSStringFromClass([overlay class]);
        if ([type containsString:@"InlineMutedPlayback"]) return YES;
        return [player isInlinePlaybackActive];
    } @catch (NSException *e) {
        if (LCVideoGestureDiagnostics()) NSLog(@"[LC Preview v5] Preview classification unavailable: %@", e.name);
        return NO;
    }
}

static BOOL LCPreviewInActivePiP(YTPlayerViewController *player) {
    @try {
        id local = [player valueForKey:@"_playbackController"];
        id pip = [local valueForKey:@"_playerPIPController"];
        if ([pip respondsToSelector:@selector(isPictureInPictureActive)] &&
            ((BOOL (*)(id,SEL))objc_msgSend)(pip, @selector(isPictureInPictureActive))) return YES;
    } @catch (NSException *e) {
        // Private controller layout can differ on newer YouTube versions.
    }
    return NO;
}

static void LCQuiesceStalePreview(YTPlayerViewController *player, NSString *reason) {
    if (!LCPreviewHandoffEnabled() || !player || LCPreviewInActivePiP(player)) return;
    // A YTPlayerViewController can be reused across preview -> watch navigation.
    // Never mute or pause it if its video identity has already changed.
    NSString *oldID = [LCPreviewSeenVideoIDs() objectForKey:player];
    if (oldID.length) {
        NSString *currentID = nil;
        @try { currentID = [player contentVideoID]; } @catch (NSException *ignored) {}
        if (currentID.length && ![oldID isEqualToString:currentID]) {
            [LCPreviewSeenPlayers() removeObject:player];
            [LCPreviewSeenVideoIDs() removeObjectForKey:player];
            return;
        }
    }
    // The registry ONLY contains instances previously identified as inline players.
    // Keep the full-watch player's audio and media playback completely untouched.
    @try {
        YTSingleVideoController *single = [player activeVideo];
        if (single && [single respondsToSelector:@selector(setMuted:)]) {
            [single setMuted:YES];
        }
        UIView *render = [player playerView];
        AVPlayer *av = LCPlayerInLayer(render.layer, 0);
        if (av && av.rate != 0) [av pause];
        if (LCVideoGestureDiagnostics())
            NSLog(@"[LC Preview v5] Quiesced old feed preview (%@); watch player not touched",reason);
    } @catch (NSException *e) {
        if (LCVideoGestureDiagnostics()) NSLog(@"[LC Preview v5] Guard skipped: %@",e.name);
    }
}

static void LCPreviewPlayerAppeared(YTPlayerViewController *player) {
    if (!LCPreviewHandoffEnabled() || !player) return;
    if (LCIsFeedPreviewPlayer(player)) {
        LCRememberFeedPreview(player);
        return;
    }
    // A full watch player has appeared. Any *different*, previously seen feed
    // preview must not keep its audio playing beneath the newly opened video.
    if (![player activeVideo]) return;
    for (YTPlayerViewController *preview in [LCPreviewSeenPlayers() allObjects]) {
        if (preview != player) LCQuiesceStalePreview(preview, @"full player appeared");
    }
}

static void LCPreviewPlayerDisappearing(YTPlayerViewController *player) {
    if (!LCPreviewHandoffEnabled() || !player) return;
    if (LCIsFeedPreviewPlayer(player)) LCRememberFeedPreview(player);
    if ([LCPreviewSeenPlayers() containsObject:player]) {
        LCQuiesceStalePreview(player, @"inline view disappeared");
    }
}
'''

SETTINGS_PATCH = r'''
    // LC_PREVIEW_HANDOFF_V5 — opt-out for a guarded fix to issues #880 and #979.
    NSUserDefaults *lcPreviewPrefs = [NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *lcPreviewHandoff = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Fix doubled audio after feed preview"
        titleDescription:@"Stops old inline preview sound when opening a video. Preview playback remains available. This is experimental and only pauses video when it uses an AVPlayer layer. Restart to apply."
        accessibilityIdentifier:nil
        switchOn:[lcPreviewPrefs objectForKey:@"LCPreviewHandoffEnabled"] ? [lcPreviewPrefs boolForKey:@"LCPreviewHandoffEnabled"] : YES
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcPreviewPrefs setBool:enabled forKey:@"LCPreviewHandoffEnabled"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcPreviewHandoff];
'''


def exactly_once(data: str, needle: str, label: str) -> None:
    count = data.count(needle)
    if count != 1:
        raise ValueError(f'{label}: need one exact v4 anchor; found {count}. Use clean v4 checkout.')


def patch_sources(tweak: str, settings: str) -> tuple[str, str]:
    if MARKER in tweak or MARKER in settings:
        raise ValueError('v5 already applied; refusing duplicate hook edits')
    if 'LC_EDGE_HOLD_V4' not in tweak or 'LC_EDGE_HOLD_V4' not in settings:
        raise ValueError('Run apply_lc_shorts.py (v4) first')
    hooks = '%hook YTPlayerViewController\n'
    appeared = '''- (void)viewDidAppear:(BOOL)animated {
    %orig;
    [self lcEdgeRefreshHold];
}'''
    appearing = '''- (void)viewDidAppear:(BOOL)animated {
    %orig;
    [self lcEdgeRefreshHold];
    LCPreviewPlayerAppeared(self);
}'''
    disappeared = '''- (void)viewWillDisappear:(BOOL)animated {
    [self lcEdgeRestorePlayback];
    %orig;
}'''
    disappearing = '''- (void)viewWillDisappear:(BOOL)animated {
    LCPreviewPlayerDisappearing(self);
    [self lcEdgeRestorePlayback];
    %orig;
}'''
    menu = '    YTSettingsSectionItem *lcSnapshot ='
    for label, data, needle in [
        ('YTPlayerViewController hook', tweak, hooks),
        ('viewDidAppear', tweak, appeared),
        ('viewWillDisappear', tweak, disappeared),
        ('settings location', settings, menu),
    ]:
        exactly_once(data, needle, label)
    tweak = tweak.replace(hooks, SOURCE_PATCH + '\n' + hooks, 1)
    tweak = tweak.replace(appeared, appearing, 1).replace(disappeared, disappearing, 1)
    settings = settings.replace(menu, SETTINGS_PATCH + '\n' + menu, 1)
    if tweak.count(MARKER) != 1 or settings.count(MARKER) != 1:
        raise AssertionError('v5 marker validation failed')
    return tweak, settings


def main() -> None:
    if not TWEAK.is_file() or not SETTINGS.is_file():
        raise FileNotFoundError('YouPiP sources missing: checkout submodules recursively')
    tweak = TWEAK.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')
    new_tweak, new_settings = patch_sources(tweak, settings)
    TWEAK.write_text(new_tweak, encoding='utf-8')
    SETTINGS.write_text(new_settings, encoding='utf-8')
    print('PiP Lab v5: guarded feed preview handoff applied; full watch audio untouched.')
    print('YouPiP/YTUHD/iSponsorBlock/YTHoldForSpeed unchanged.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Preview patch error: {exc}', file=sys.stderr)
        sys.exit(1)
