#!/usr/bin/env python3
"""Add an opt-out VP9 hardware-registration control and diagnostic to YouPiP v10."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
SETTINGS=ROOT/'Tweaks/YouPiP/Settings.x'
MARK='LC_HWVP9_SETTINGS_V10_HARDWARE'
ANCHOR='    YTSettingsSectionItem *lcV10Snapshot='
UI=r'''    // LC_HWVP9_SETTINGS_V10_HARDWARE
    NSUserDefaults *lcHWPrefs=[NSUserDefaults standardUserDefaults];
    [lcHWPrefs registerDefaults:@{@"LCHWVP9RegistrationEnabled": @YES}];
    YTSettingsSectionItem *lcHWToggle=[%c(YTSettingsSectionItem)
        switchItemWithTitle:@"Try supplemental hardware VP9 on next launch"
        titleDescription:@"Experimental on iOS 26.2+. Requests an available system decoder before YTUHD checks support. Restart app; not a guarantee that this video uses HW decode. Rebuild with modern_ytuhd OFF if unstable."
        accessibilityIdentifier:nil
        switchOn:[lcHWPrefs boolForKey:@"LCHWVP9RegistrationEnabled"]
        switchBlock:^BOOL (YTSettingsCell *cell, BOOL enabled) {
            [lcHWPrefs setBool:enabled forKey:@"LCHWVP9RegistrationEnabled"];
            return YES;
        } settingItemId:0];
    [sectionItems addObject:lcHWToggle];
    YTSettingsSectionItem *lcHWInfo=[%c(YTSettingsSectionItem)
        itemWithTitle:@"Hardware VP9 probe (copy)"
        titleDescription:@"Shows VideoToolbox registration and capability check from YTUHD initialization. Does NOT prove hardware decoding of a particular video."
        accessibilityIdentifier:nil detailTextBlock:nil
        selectBlock:^BOOL (YTSettingsCell *cell, NSUInteger arg1) {
            NSString *report=[NSString stringWithFormat:
                @"Supplemental VP9 hardware probe\nRegistration allowed: %@\nRegistration symbol available: %@\nRegistration invoked: %@\nVP9 capability before: %@\nVP9 capability after: %@\n\nNote: the capability API can give false negatives. Compare Stats for Nerds HV and 30-second dropped-frame delta.",
                [lcHWPrefs boolForKey:@"LCHWVP9RegistrationEnabled"]?@"yes":@"no",
                [lcHWPrefs boolForKey:@"LCHWVP9SymbolAvailable"]?@"yes":@"no",
                [lcHWPrefs boolForKey:@"LCHWVP9RegistrationInvoked"]?@"yes":@"no",
                [lcHWPrefs boolForKey:@"LCHWVP9SupportBefore"]?@"yes":@"no",
                [lcHWPrefs boolForKey:@"LCHWVP9SupportAfter"]?@"yes":@"no"];
            [UIPasteboard generalPasteboard].string=report;
            UIAlertController *alert=[UIAlertController alertControllerWithTitle:@"VP9 hardware check copied"
                message:report preferredStyle:UIAlertControllerStyleAlert];
            [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
            UIViewController *presenter=LCPresenter();
            if (presenter) [presenter presentViewController:alert animated:YES completion:nil];
            return YES;
        }];
    [sectionItems addObject:lcHWInfo];
'''

def transform(source):
    if MARK in source: raise RuntimeError('hardware diagnostic already applied')
    if source.count(ANCHOR)!=1: raise RuntimeError('v10 diagnostics missing; run patches in workflow order')
    return source.replace(ANCHOR,UI+'\n'+ANCHOR,1)

def main():
    SETTINGS.write_text(transform(SETTINGS.read_text(encoding='utf-8')),encoding='utf-8')
    print('Added hardware VP9 probe/readout to unified settings.')
if __name__=='__main__':
    try: main()
    except Exception as e:
        print('::error::'+str(e),file=sys.stderr)
        sys.exit(1)
