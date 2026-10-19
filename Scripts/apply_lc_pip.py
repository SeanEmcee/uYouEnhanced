#!/usr/bin/env python3
"""Apply a minimal, repeatable LC PiP compatibility patch to the pinned
uYouEnhanced YouPiP submodule after 'actions/checkout' (submodules: recursive).

A nonzero exit stops the build instead of silently producing an unpatched IPA.
Do not run twice against the same uncommitted submodule checkout.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
PIP = ROOT / 'Tweaks' / 'YouPiP'
SOURCE = PIP / 'Tweak.x'
SETTINGS = PIP / 'Settings.x'
MARKER = 'LC_PIP_LAB_V1'

TWEAK_HOOK = r'''
// LC_PIP_LAB_V1: Observe all AVKit PiP start requests, including YouTube's
// A/B menu PiP button. Never attempt to background before PiP is active.
// Uses a *private*, best-effort selector. Disable in YouPiP settings if your
// LiveContainer version does not support it. Normal PiP remains untouched.
static BOOL lcPiPHomePending = NO;

%hook AVPictureInPictureController

- (void)startPictureInPicture {
    %orig;
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    BOOL diagnostics = [defaults boolForKey:@"LCPlaybackLabPiPDiagnostics"];
    if (diagnostics) NSLog(@"[LC PiP Lab] PiP start requested");
    if (![defaults boolForKey:@"LCPlaybackLabAutoHome"] || lcPiPHomePending)
        return;

    lcPiPHomePending = YES;
    __weak AVPictureInPictureController *weakPiP = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.70 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        lcPiPHomePending = NO;
        AVPictureInPictureController *pip = weakPiP;
        UIApplication *app = [UIApplication sharedApplication];
        if (!pip || !pip.isPictureInPictureActive ||
            app.applicationState != UIApplicationStateActive) {
            if (diagnostics) NSLog(@"[LC PiP Lab] Auto Home skipped: PiP inactive or app backgrounded");
            return;
        }
        SEL homeSelector = NSSelectorFromString(@"suspend");
        if (![app respondsToSelector:homeSelector]) {
            if (diagnostics) NSLog(@"[LC PiP Lab] Auto Home unsupported: selector absent");
            return;
        }
        if (diagnostics) NSLog(@"[LC PiP Lab] Attempting experimental Auto Home after PiP started");
        IMP implementation = [app methodForSelector:homeSelector];
        if (implementation) {
            ((void (*)(id, SEL))implementation)(app, homeSelector);
        }
    });
}

%end

'''

SETTINGS_HELPERS = r'''
// LC_PIP_LAB_V1: A/B flags are owned by YTABConfig and persisted under
// "YTABC.<ConfigClass>.<selector>". Only touch selectors implemented by
// this particular YouTube version. Settings take effect after app restart.
static NSArray<NSString *> *LCConfigClasses(void) {
    return @[@"YTHotConfig", @"YTColdConfig", @"YTGlobalConfig"];
}

static BOOL LCConfigHasSelector(NSString *configClassName, NSString *flagName) {
    Class configClass = NSClassFromString(configClassName);
    return configClass && [configClass instancesRespondToSelector:NSSelectorFromString(flagName)];
}

static NSString *LCConfigKey(NSString *configClassName, NSString *flagName) {
    return [NSString stringWithFormat:@"YTABC.%@.%@", configClassName, flagName];
}

static BOOL LCABFlagOn(NSString *flagName) {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    for (NSString *configClass in LCConfigClasses()) {
        if (LCConfigHasSelector(configClass, flagName) &&
            [defaults boolForKey:LCConfigKey(configClass, flagName)]) return YES;
    }
    return NO;
}

static void LCSetABFlag(NSString *flagName, BOOL enabled) {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    for (NSString *configClass in LCConfigClasses()) {
        if (LCConfigHasSelector(configClass, flagName))
            [defaults setBool:enabled forKey:LCConfigKey(configClass, flagName)];
    }
}

static UIViewController *LCPresenter(void) {
    // Use the active scene's key window instead of deprecated UIApplication.keyWindow.
    // This also avoids accidentally showing alerts over a background scene.
    UIApplication *application = [UIApplication sharedApplication];
    UIWindow *selectedWindow = nil;
    for (UIScene *scene in application.connectedScenes) {
        if (![scene isKindOfClass:[UIWindowScene class]] ||
            scene.activationState != UISceneActivationStateForegroundActive) continue;
        UIWindowScene *windowScene = (UIWindowScene *)scene;
        for (UIWindow *candidate in windowScene.windows) {
            if (candidate.isKeyWindow) { selectedWindow = candidate; break; }
        }
        if (!selectedWindow) {
            for (UIWindow *candidate in windowScene.windows) {
                if (!candidate.hidden && candidate.windowLevel == UIWindowLevelNormal) {
                    selectedWindow = candidate;
                    break;
                }
            }
        }
        if (selectedWindow) break;
    }
    UIViewController *controller = selectedWindow.rootViewController;
    while (controller.presentedViewController) controller = controller.presentedViewController;
    return controller;
}

'''

SETTINGS_UI = r'''
    // LC_PIP_LAB_V1: One place for all three settings that solved PiP.
    NSUserDefaults *lcDefaults = [NSUserDefaults standardUserDefaults];
    BOOL lcPresetIsOn = TweakEnabled() && LCABFlagOn(@"addPipMenuItem") &&
                        LCABFlagOn(@"enablePipMenuItem");
    YTSettingsSectionItem *lcPreset = [%c(YTSettingsSectionItem) switchItemWithTitle:@"LiveContainer native PiP preset"
        titleDescription:@"Sets addPipMenuItem, enablePipMenuItem and YouPiP together. Restart YouTube in LiveContainer after changing."
        accessibilityIdentifier:nil
        switchOn:lcPresetIsOn
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            LCSetABFlag(@"addPipMenuItem", enabled);
            LCSetABFlag(@"enablePipMenuItem", enabled);
            [lcDefaults setBool:enabled forKey:EnabledKey];
            if (enabled) [lcDefaults setBool:YES forKey:PiPAllActivationMethodKey];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcPreset];

    YTSettingsSectionItem *lcABAdd = [%c(YTSettingsSectionItem) switchItemWithTitle:@"A/B: addPipMenuItem"
        titleDescription:@"YouTube internal menu flag. Changes require restarting the app."
        accessibilityIdentifier:nil
        switchOn:LCABFlagOn(@"addPipMenuItem")
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            LCSetABFlag(@"addPipMenuItem", enabled);
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcABAdd];

    YTSettingsSectionItem *lcABEnable = [%c(YTSettingsSectionItem) switchItemWithTitle:@"A/B: enablePipMenuItem"
        titleDescription:@"YouTube internal menu flag. Changes require restarting the app."
        accessibilityIdentifier:nil
        switchOn:LCABFlagOn(@"enablePipMenuItem")
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            LCSetABFlag(@"enablePipMenuItem", enabled);
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcABEnable];

    YTSettingsSectionItem *lcHome = [%c(YTSettingsSectionItem) switchItemWithTitle:@"Auto Home after PiP button (EXPERIMENTAL)"
        titleDescription:@"Attempts to minimize LiveContainer only after native PiP is active. Uses an unsupported private iOS selector; may do nothing or disrupt PiP. OFF is safest."
        accessibilityIdentifier:nil
        switchOn:[lcDefaults boolForKey:@"LCPlaybackLabAutoHome"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcDefaults setBool:enabled forKey:@"LCPlaybackLabAutoHome"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcHome];

    YTSettingsSectionItem *lcLogging = [%c(YTSettingsSectionItem) switchItemWithTitle:@"PiP lifecycle diagnostic logs"
        titleDescription:@"Log PiP activation and Auto Home checks to the system console; no video URLs or account information."
        accessibilityIdentifier:nil
        switchOn:[lcDefaults boolForKey:@"LCPlaybackLabPiPDiagnostics"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcDefaults setBool:enabled forKey:@"LCPlaybackLabPiPDiagnostics"];
            return YES;
        }
        settingItemId:0];
    [sectionItems addObject:lcLogging];

    YTSettingsSectionItem *lcSnapshot = [%c(YTSettingsSectionItem) itemWithTitle:@"Playback Lab: audio / PiP snapshot"
        titleDescription:@"Displays active audio output properties and PiP preferences. Not source audio codec or stream bitrate."
        accessibilityIdentifier:nil
        detailTextBlock:nil
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            AVAudioSession *audioSession = [AVAudioSession sharedInstance];
            AVAudioSessionPortDescription *port = audioSession.currentRoute.outputs.firstObject;
            NSString *status = [NSString stringWithFormat:
                @"YouPiP: %@\naddPipMenuItem: %@\nenablePipMenuItem: %@\nAuto Home: %@\nAudio output: %@\nOutput sample rate: %.0f Hz\nOutput channels: %ld\n\nSource codec, HDR, network bitrate: not yet instrumented.",
                TweakEnabled() ? @"ON" : @"OFF",
                LCABFlagOn(@"addPipMenuItem") ? @"ON" : @"OFF",
                LCABFlagOn(@"enablePipMenuItem") ? @"ON" : @"OFF",
                [lcDefaults boolForKey:@"LCPlaybackLabAutoHome"] ? @"ON" : @"OFF",
                port.portName ?: @"Unavailable", audioSession.sampleRate,
                (long)audioSession.outputNumberOfChannels];
            UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Playback Lab v1"
                message:status preferredStyle:UIAlertControllerStyleAlert];
            [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
            UIViewController *presenter = LCPresenter();
            if (presenter) [presenter presentViewController:alert animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcSnapshot];
'''


def replace_one(content: str, before: str, after: str, filename: str) -> str:
    count = content.count(before)
    if count != 1:
        raise RuntimeError(f'{filename}: expected exactly 1 insertion point, found {count}. Upstream changed; update patch first.')
    return content.replace(before, after, 1)


def apply():
    for filename in [SOURCE, SETTINGS]:
        if not filename.is_file():
            raise RuntimeError(f'Missing {filename}. GitHub checkout MUST use submodules: recursive.')
    tweak = SOURCE.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')
    if MARKER in tweak or MARKER in settings:
        raise RuntimeError('Patch already applied; refusing to double-install hooks.')
    # Fail closed if the underlying version does not look like the inspected source.
    for needle in ('#pragma mark - PiP Support', '%hook MLPIPControllerImpl', '%hook AVPictureInPicturePlatformAdapter'):
        if needle not in tweak:
            raise RuntimeError(f'Unexpected YouPiP/Tweak.x; missing {needle}')
    for needle in ('- (void)updateYouPiPSectionWithEntry:(id)entry {',
                   'NSBundle *tweakBundle = YouPiPBundle();',
                   'switchItemWithTitle:LOC(@"ENABLED")'):
        if needle not in settings:
            raise RuntimeError(f'Unexpected YouPiP/Settings.x; missing {needle}')

    tweak = replace_one(tweak, '#pragma mark - PiP Support', TWEAK_HOOK + '#pragma mark - PiP Support', 'Tweak.x')
    settings = replace_one(settings, '#define LOC(x) [tweakBundle localizedStringForKey:x value:nil table:nil]',
        '#import <AVFoundation/AVFoundation.h>\n#define LOC(x) [tweakBundle localizedStringForKey:x value:nil table:nil]\n' + SETTINGS_HELPERS, 'Settings.x')
    settings = replace_one(settings,
        '    NSBundle *tweakBundle = YouPiPBundle();\n',
        '    NSBundle *tweakBundle = YouPiPBundle();\n' + SETTINGS_UI + '\n', 'Settings.x')

    # Verify before mutating either file.
    assert MARKER in tweak and MARKER in settings
    assert '%hook AVPictureInPictureController' in tweak
    assert 'LiveContainer native PiP preset' in settings
    SOURCE.write_text(tweak, encoding='utf-8')
    SETTINGS.write_text(settings, encoding='utf-8')
    print('[LC PiP Lab] Patched YouPiP/Tweak.x and Settings.x successfully.')
    print('[LC PiP Lab] Native PiP flag preset + optional experimental Auto Home + diagnostics.')
    print('[LC PiP Lab] YouPiP remains included in uYouEnhanced. No other tweak altered.')

if __name__ == '__main__':
    try:
        apply()
    except Exception as exc:
        print(f'::error::{exc}', file=sys.stderr)
        sys.exit(1)
