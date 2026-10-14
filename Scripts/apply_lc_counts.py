#!/usr/bin/env python3
"""PiP Lab v6: add a guarded count-display fallback to bundled Return YouTube Dislike.

Works on source checked out via `git submodule update --init --recursive`.
Does not replace the upstream API, remove tweaks, or bypass the user's settings.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TWEAK = ROOT / 'Tweaks/Return-YouTube-Dislikes/Tweak.x'
SETTINGS = ROOT / 'Tweaks/Return-YouTube-Dislikes/Settings.x'
MARKER = 'LC_RYD_COUNT_RESCUE_V6'

CODE = r'''
// LC_RYD_COUNT_RESCUE_V6
static NSString *getVideoId(ASDisplayNode *containerNode);
// Fallback for modern 21.x watch actionbars without old ELM count nodes.
// Return YouTube Dislike's existing vote cache/API are reused. No fabricated counts.
#import <objc/runtime.h>

static const char kLCRescueLabelKey;
static const char kLCRescueVideoKey;

static BOOL LCRescueCountsEnabled(void) {
    NSUserDefaults *prefs = [NSUserDefaults standardUserDefaults];
    return [prefs objectForKey:@"LCRescueCountsEnabled"] == nil ? YES :
        [prefs boolForKey:@"LCRescueCountsEnabled"];
}

static ASDisplayNode *LCFindCountButton(ASDisplayNode *node, NSString *identifier, NSUInteger depth) {
    if (!node || depth > 24) return nil;
    if ([node.accessibilityIdentifier isEqualToString:identifier]) return node;
    NSArray *children = node.yogaChildren;
    if (![children isKindOfClass:[NSArray class]]) return nil;
    for (id child in children) {
        if (![child isKindOfClass:[ASDisplayNode class]]) continue;
        ASDisplayNode *found = LCFindCountButton((ASDisplayNode *)child, identifier, depth + 1);
        if (found) return found;
    }
    return nil;
}

// Skip a fallback if a readable numeric title is already on screen.
static BOOL LCHasVisibleNumericTitle(UIView *view, UIView *rescue, NSUInteger depth) {
    if (!view || depth > 9 || view.hidden || view.alpha < 0.05 || view == rescue) return NO;
    NSString *s = nil;
    if ([view isKindOfClass:[UILabel class]]) s = ((UILabel *)view).text;
    if ([view isKindOfClass:[UIButton class]]) s = [((UIButton *)view) titleForState:UIControlStateNormal];
    if (s.length && [s rangeOfCharacterFromSet:[NSCharacterSet decimalDigitCharacterSet]].location != NSNotFound)
        return YES;
    for (UIView *child in view.subviews)
        if (LCHasVisibleNumericTitle(child, rescue, depth + 1)) return YES;
    return NO;
}

static void LCUpdateCountBadge(UIView *view, NSString *videoId, NSString *count) {
    if (!LCRescueCountsEnabled() || !view || !videoId.length || !count.length) return;
    NSString *expected = objc_getAssociatedObject(view, &kLCRescueVideoKey);
    if (![expected isEqualToString:videoId] || !view.window) return;
    UILabel *badge = objc_getAssociatedObject(view, &kLCRescueLabelKey);
    if (LCHasVisibleNumericTitle(view, badge, 0)) {
        badge.hidden = YES; // Native count already displayed: never duplicate it.
        return;
    }
    if (!badge) {
        badge = [[UILabel alloc] initWithFrame:CGRectZero];
        badge.translatesAutoresizingMaskIntoConstraints = NO;
        badge.userInteractionEnabled = NO;
        badge.numberOfLines = 1;
        badge.adjustsFontSizeToFitWidth = YES;
        badge.minimumScaleFactor = 0.7;
        badge.textAlignment = NSTextAlignmentCenter;
        badge.font = [UIFont systemFontOfSize:10.5 weight:UIFontWeightMedium];
        badge.textColor = [UIColor labelColor];
        badge.accessibilityElementsHidden = YES;
        [view addSubview:badge];
        [NSLayoutConstraint activateConstraints:@[
            [badge.centerXAnchor constraintEqualToAnchor:view.centerXAnchor],
            [badge.bottomAnchor constraintEqualToAnchor:view.bottomAnchor constant:-1.0],
            [badge.widthAnchor constraintLessThanOrEqualToAnchor:view.widthAnchor],
            [badge.heightAnchor constraintEqualToConstant:14.0]
        ]];
        objc_setAssociatedObject(view, &kLCRescueLabelKey, badge, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    badge.text = count;
    badge.hidden = NO;
}

static void LCStartCountRescue(NSString *videoId, UIView *likeView, UIView *dislikeView) {
    if (!LCRescueCountsEnabled() || !videoId.length || (!likeView && !dislikeView)) return;
    // Video identity prevents stale asynchronous API responses appearing on reused cells.
    if (likeView) objc_setAssociatedObject(likeView, &kLCRescueVideoKey, videoId, OBJC_ASSOCIATION_COPY_NONATOMIC);
    if (dislikeView) objc_setAssociatedObject(dislikeView, &kLCRescueVideoKey, videoId, OBJC_ASSOCIATION_COPY_NONATOMIC);
    __weak UIView *weakLike = likeView;
    __weak UIView *weakDislike = dislikeView;
    getVoteFromVideoWithHandler(cache, videoId, maxRetryCount, ^(NSDictionary *data, NSString *error) {
        if (error || ![data isKindOfClass:[NSDictionary class]]) return;
        NSNumber *likes = getLikeData(data);
        NSNumber *dislikes = getDislikeData(data);
        // RYD like data can differ from YouTube's own count; mark it as approximate.
        NSString *likeText = likes ? [@"≈ " stringByAppendingString:getNormalizedLikes(likes, nil)] : nil;
        NSString *dislikeText = dislikes ? [@"≈ " stringByAppendingString:getNormalizedDislikes(dislikes, nil)] : nil;
        dispatch_async(dispatch_get_main_queue(), ^{
            if (weakLike && likeText.length) LCUpdateCountBadge(weakLike, videoId, likeText);
            if (weakDislike && dislikeText.length) LCUpdateCountBadge(weakDislike, videoId, dislikeText);
        });
    });
}

static void LCScheduleWatchCountRescue(ELMCellNode *cell) {
    if (!LCRescueCountsEnabled() || !cell) return;
    __weak ELMCellNode *weakCell = cell;
    // The node is produced before UIKit finishes materializing its views.
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.2 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        ELMCellNode *root = weakCell;
        if (!root) return;
        ASDisplayNode *like = LCFindCountButton(root, @"id.video.like.button", 0);
        ASDisplayNode *dislike = LCFindCountButton(root, @"id.video.dislike.button", 0);
        if (!like && !dislike) return;
        NSString *videoId = nil;
        @try { videoId = getVideoId(root); } @catch (NSException *e) {
            NSLog(@"[LC Counts v6] Video ID lookup skipped: %@", e.name);
        }
        if (!videoId.length) return;
        LCStartCountRescue(videoId, like.view, dislike.view);
    });
}
'''

SETTINGS_CODE = r'''
    // LC_RYD_COUNT_RESCUE_V6 — modern watch / Shorts missing-number fallback.
    NSUserDefaults *lcCountPrefs = [NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *lcCountRescue = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Restore missing like/dislike counts (v6)"
        titleDescription:@"Shows fallback counts when YouTube's number labels are missing. Uses Return YouTube Dislike's estimated data, not official YouTube dislike totals. Does not duplicate visible counts."
        accessibilityIdentifier:nil
        switchOn:[lcCountPrefs objectForKey:@"LCRescueCountsEnabled"] ? [lcCountPrefs boolForKey:@"LCRescueCountsEnabled"] : YES
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcCountPrefs setBool:enabled forKey:@"LCRescueCountsEnabled"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcCountRescue];
'''


def replace_one(s: str, before: str, after: str, label: str) -> str:
    n = s.count(before)
    if n != 1:
        raise ValueError(f'{label}: expected one anchor, found {n}; check checked-out submodule')
    return s.replace(before, after, 1)


def patch_tweak(s: str) -> str:
    if MARKER in s:
        raise ValueError('Counts patch already applied. Do not apply twice.')
    anchor = '%hook ASCollectionView\n\n%property (nonatomic, assign) BOOL hasDislikeIntent;'
    s = replace_one(s, anchor, CODE + '\n' + anchor, 'RYD actionbar hook')
    anchor2 = '    ELMCellNode *node = %orig;\n    if (!TweakEnabled()) return node;'
    patched = '''    ELMCellNode *node = %orig;
    if (!TweakEnabled()) return node;
    if (isVideoScrollableActionBar(self, node)) LCScheduleWatchCountRescue(node);'''
    s = replace_one(s, anchor2, patched, 'RYD watch-node interception')
    # Shorts already have RYD button-title updates; add a fallback for title-less
    # modern Shorts button views without replacing the existing titles.
    shorts_anchor = '''    YTQTMButton *dislikeButton = self.dislikeButton;
    [dislikeButton setTitle:FETCHING forState:UIControlStateNormal];'''
    shorts_new = '''    YTQTMButton *dislikeButton = self.dislikeButton;
    if (LCRescueCountsEnabled() && renderer.target.videoId.length) {
        // Delayed so the original Shorts title update gets the first chance.
        NSString *shortId = [renderer.target.videoId copy];
        __weak YTQTMButton *weakLike = self.likeButton;
        __weak YTQTMButton *weakDislike = dislikeButton;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.25 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            LCStartCountRescue(shortId, weakLike, weakDislike);
        });
    }
    [dislikeButton setTitle:FETCHING forState:UIControlStateNormal];'''
    # C helper functions must be defined before first use in the Shorts hook.
    # Move CODE above the first RYD hook, not above ASCollectionView.
    s = replace_one(s, CODE + '\n' + anchor, anchor, 'move shared helper')
    first_hook = '%hook YTReelWatchLikesController\n'
    s = replace_one(s, first_hook, CODE + '\n' + first_hook, 'RYD Shorts hook')
    s = replace_one(s, shorts_anchor, shorts_new, 'RYD Shorts fallback')
    return s


def patch_settings(s: str) -> str:
    if MARKER in s:
        raise ValueError('Settings already patched')
    anchor = '    [sectionItems addObject:enabled];\n'
    return replace_one(s, anchor, anchor + SETTINGS_CODE, 'RYD settings enabled switch')


def main() -> int:
    for p in (TWEAK, SETTINGS):
        if not p.is_file():
            raise FileNotFoundError(f'Missing Return YouTube Dislike submodule source: {p}')
    old_t = TWEAK.read_text(encoding='utf-8')
    old_s = SETTINGS.read_text(encoding='utf-8')
    new_t = patch_tweak(old_t)
    new_s = patch_settings(old_s)
    TWEAK.write_text(new_t, encoding='utf-8', newline='\n')
    SETTINGS.write_text(new_s, encoding='utf-8', newline='\n')
    print('Applied RYD v6 count-rescue fallback to original RYD source')
    print('Regular watch actionbars and Shorts; original RYD API/hooks preserved')
    print('No other tweak is disabled or removed')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        raise SystemExit(1)
