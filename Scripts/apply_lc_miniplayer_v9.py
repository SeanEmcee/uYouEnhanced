#!/usr/bin/env python3
"""V9 source patch: MiniPlayer overlay touch routing and early-render recovery."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
TWEAK=ROOT/'Tweaks/YouPiP/Tweak.x'
SETTINGS=ROOT/'Tweaks/YouPiP/Settings.x'
MARK='LC_MINIPLAYER_TOUCH_FIX_V9'
SOURCE=r'''
// LC_MINIPLAYER_TOUCH_FIX_V9
// Only active on a confirmed floating player. Never changes native pan/pinch
// recognizer delegates, playback speed, AVAudioSession, or video position.
#import <objc/runtime.h>
#import <YouTubeHeader/YTMainAppVideoPlayerOverlayView.h>
#import <YouTubeHeader/YTPlayerView.h>
static char kLCMiniV9State;
static char kLCMiniV9Generation;
static BOOL LCMiniV9Pref(NSString *key) {
    NSUserDefaults *p = [NSUserDefaults standardUserDefaults];
    return [p objectForKey:key] == nil ? YES : [p boolForKey:key];
}
static BOOL LCMiniV9Floating(YTPlayerView *view) {
    if (!view || !view.window) return NO;
    UIView *v=view;
    for (int i=0; v && i<18; ++i, v=v.superview) {
        NSString *name=NSStringFromClass(v.class).lowercaseString;
        if ([name containsString:@"minibar"] || [name containsString:@"miniplayer"] ||
            [name containsString:@"floatingplayer"] || [name containsString:@"floating_player"])
            return YES;
    }
    CGRect r=[view convertRect:view.bounds toView:view.window];
    CGSize screen=view.window.bounds.size;
    return screen.width>0 && screen.height>0 &&
        CGRectGetWidth(r)>1 && CGRectGetHeight(r)>1 &&
        CGRectGetWidth(r)/screen.width<0.985 &&
        CGRectGetHeight(r)/screen.height<0.80;
}
static YTPlayerView *LCMiniV9ParentPlayer(UIView *v) {
    for (int i=0; v && i<18; ++i,v=v.superview) {
        if ([v isKindOfClass:%c(YTPlayerView)]) return (YTPlayerView *)v;
    }
    return nil;
}
static BOOL LCMiniV9ButtonTouch(UIView *hit, UIView *overlay) {
    for (UIView *v=hit; v && v!=overlay; v=v.superview)
        if ([v isKindOfClass:[UIControl class]]) return YES;
    return NO;
}
static void LCMiniV9RefreshRender(YTPlayerView *view) {
    if (!view || !view.window || !LCMiniV9Floating(view) ||
        !LCMiniV9Pref(@"LCMiniV9RenderWake")) return;
    UIView *render=nil;
    @try { render=[view renderingView]; } @catch (NSException *ignored) {}
    if ([render isKindOfClass:[UIView class]]) {
        [render setNeedsLayout];
        [render.layer setNeedsLayout];
        [render.layer setNeedsDisplay];
    }
    [view setNeedsLayout];
    if (LCVideoGestureDiagnostics()) NSLog(@"[LC v9] MiniPlayer render refresh: %@", NSStringFromClass(render.class));
}
static void LCMiniV9Transition(YTPlayerView *view) {
    if (!view || !view.window) return;
    BOOL mini=LCMiniV9Floating(view);
    NSNumber *previous=objc_getAssociatedObject(view,&kLCMiniV9State);
    if (previous && previous.boolValue==mini) return;
    objc_setAssociatedObject(view,&kLCMiniV9State,@(mini),OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    NSUInteger generation=[objc_getAssociatedObject(view,&kLCMiniV9Generation) unsignedIntegerValue]+1;
    objc_setAssociatedObject(view,&kLCMiniV9Generation,@(generation),OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    if (LCVideoGestureDiagnostics()) NSLog(@"[LC v9] MiniPlayer transition floating=%d",(int)mini);
    if (!mini || !LCMiniV9Pref(@"LCMiniV9RenderWake")) return;
    __weak YTPlayerView *weakView=view;
    for (NSNumber *delay in @[@0.05,@0.28,@0.75]) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,(int64_t)(delay.doubleValue*NSEC_PER_SEC)),
                       dispatch_get_main_queue(),^{
            YTPlayerView *v=weakView;
            if (!v || [objc_getAssociatedObject(v,&kLCMiniV9Generation) unsignedIntegerValue]!=generation) return;
            LCMiniV9RefreshRender(v);
        });
    }
}
%hook YTMainAppVideoPlayerOverlayView
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *target=%orig;
    if (!target || !LCMiniV9Pref(@"LCMiniV9TouchPassThrough")) return target;
    YTPlayerView *player=LCMiniV9ParentPlayer(self);
    if (!player || !LCMiniV9Floating(player)) return target;
    // Keep genuine buttons working; pass empty-overlay touches through to
    // YouTube's floating container to allow its original drag/pinch gestures.
    return LCMiniV9ButtonTouch(target,self) ? target : nil;
}
%end
'''
VIEW_METHOD=r'''- (void)layoutSubviews {
    %orig;
    if (LCMiniplayerGuardV8()) LCMiniV9Transition(self);
}
- (void)didMoveToWindow {
    %orig;
    __weak YTPlayerView *weakView=self;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (weakView && LCMiniplayerGuardV8()) LCMiniV9Transition(weakView);
    });
}
'''
SETTINGS_PATCH=r'''
    // LC_MINIPLAYER_TOUCH_FIX_V9
    NSUserDefaults *lcV9Prefs = [NSUserDefaults standardUserDefaults];
    YTSettingsSectionItem *lcV9Touches = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"MiniPlayer drag/pinch pass-through (v9)"
        titleDescription:@"ON by default. Routes touches on the floating video's empty overlay to the MiniPlayer container. Keeps standard buttons. Restart if changed."
        accessibilityIdentifier:nil
        switchOn:[lcV9Prefs objectForKey:@"LCMiniV9TouchPassThrough"] == nil ? YES : [lcV9Prefs boolForKey:@"LCMiniV9TouchPassThrough"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL value) {
            [lcV9Prefs setBool:value forKey:@"LCMiniV9TouchPassThrough"]; return YES;
        } settingItemId:0];
    [sectionItems addObject:lcV9Touches];
    YTSettingsSectionItem *lcV9Render = [%c(YTSettingsSectionItem)
        switchItemWithTitle:@"MiniPlayer early-frame renderer refresh (v9)"
        titleDescription:@"ON by default. Performs a bounded layout/display refresh immediately after minimizing. Does not force playback, seek or reload."
        accessibilityIdentifier:nil
        switchOn:[lcV9Prefs objectForKey:@"LCMiniV9RenderWake"] == nil ? YES : [lcV9Prefs boolForKey:@"LCMiniV9RenderWake"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL value) {
            [lcV9Prefs setBool:value forKey:@"LCMiniV9RenderWake"]; return YES;
        } settingItemId:0];
    [sectionItems addObject:lcV9Render];
'''
def rep(source,old,new,name):
    if source.count(old)!=1: raise RuntimeError(f'{name}: expected one anchor; found {source.count(old)}')
    return source.replace(old,new,1)
def patch_sources(tweak,settings):
    if MARK in tweak or MARK in settings: raise RuntimeError('v9 already applied')
    if 'LC_MINIPLAYER_GESTURE_GUARD_V8' not in tweak: raise RuntimeError('Apply v8 first')
    tweak=rep(tweak,'%hook YTPlayerView\n- (void)didMoveToSuperview {',
        SOURCE+'\n%hook YTPlayerView\n'+VIEW_METHOD+'- (void)didMoveToSuperview {','YTPlayerView hook')
    tweak=rep(tweak,'return widthRatio < 0.94 && heightRatio < 0.70;',
              'return widthRatio < 0.985 && heightRatio < 0.80;', 'expanded MiniPlayer geometric recognition')
    settings=rep(settings,'    YTSettingsSectionItem *lcSnapshot =',
                 SETTINGS_PATCH+'\n    YTSettingsSectionItem *lcSnapshot =','settings')
    assert tweak.count(MARK)==1 and settings.count(MARK)==1
    return tweak,settings
if __name__=='__main__':
    try:
        if not TWEAK.is_file() or not SETTINGS.is_file(): raise RuntimeError('YouPiP submodule missing')
        t,s=patch_sources(TWEAK.read_text(),SETTINGS.read_text())
        TWEAK.write_text(t);SETTINGS.write_text(s)
        print('v9 MiniPlayer touch pass-through and renderer refresh applied.')
        print('YouPiP, YTUHD, iSponsorBlock, RYD, YTHoldForSpeed preserved.')
    except Exception as e:
        print(f'::error::{e}',file=sys.stderr);sys.exit(1)
