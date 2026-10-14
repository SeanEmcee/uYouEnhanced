#!/usr/bin/env python3
"""PiP Lab v10-HW: attempt supplemental VP9 registration on iOS 26.2+.

This instruments the maintained PoomSmart YTUHD _before_ its initial VideoToolbox
hardware checks; does NOT inject entitlements, force AVPlayer, or claim HW active.
When using the original YTUHD fork, this patch is skipped deliberately.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
YTUHD=ROOT/'Tweaks'/'YTUHD'/'Tweak.xm'
MAKE=ROOT/'Tweaks'/'YTUHD'/'Makefile'
MARK='LC_HWVP9_REGISTER_V10_HARDWARE'
ANCHOR='%ctor {\n    vtSupportsVP9 = VTIsHardwareDecodeSupported(kCMVideoCodecType_VP9);'

# Dynamic symbol lookup because Apple headers historically declare this macOS-only.
# Maintainer reports that modern iOS YouTube may register this decoder from 26.2.
# Never mask platform failures or try to bypass signing entitlements.
IMPL=r'''// LC_HWVP9_REGISTER_V10_HARDWARE
#include <dlfcn.h>

static void LCRegisterSupplementalVP9IfAvailable(void) {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    [defaults registerDefaults:@{@"LCHWVP9RegistrationEnabled": @YES}];
    // Distinguish decoder availability from proof of active HW decode.
    BOOL before = VTIsHardwareDecodeSupported(kCMVideoCodecType_VP9);
    [defaults setBool:before forKey:@"LCHWVP9SupportBefore"];
    [defaults setBool:NO forKey:@"LCHWVP9RegistrationInvoked"];
    [defaults setBool:NO forKey:@"LCHWVP9SymbolAvailable"];
    // No automatic registration on iOS below 26.2. It was not observed there.
    if (@available(iOS 26.2, *)) {
        if ([defaults boolForKey:@"LCHWVP9RegistrationEnabled"]) {
            // Look up dynamically to avoid a hard dependency on a symbol which
            // might not be present on a particular iOS build.
            void *sym = dlsym(RTLD_DEFAULT, "VTRegisterSupplementalVideoDecoderIfAvailable");
            [defaults setBool:(sym != NULL) forKey:@"LCHWVP9SymbolAvailable"];
            if (sym) {
                typedef void (*LCVideoDecoderRegister)(CMVideoCodecType);
                ((LCVideoDecoderRegister)sym)(kCMVideoCodecType_VP9);
                [defaults setBool:YES forKey:@"LCHWVP9RegistrationInvoked"];
            }
        }
    }
    BOOL after = VTIsHardwareDecodeSupported(kCMVideoCodecType_VP9);
    [defaults setBool:after forKey:@"LCHWVP9SupportAfter"];
    NSLog(@"[PiP Lab hardware] VP9 before=%d after=%d supplemental invoked=%d", before, after,
          [defaults boolForKey:@"LCHWVP9RegistrationInvoked"]);
}

'''

def transform(code):
    if MARK in code:
        raise RuntimeError('hardware registration already applied')
    if code.count(ANCHOR)!=1:
        raise RuntimeError('Pinned modern YTUHD source changed; safe stop rather than modifying unknown code')
    if 'VTIsHardwareDecodeSupported(kCMVideoCodecType_VP9)' not in code:
        raise RuntimeError('No VideoToolbox VP9 hardware check in decoder source')
    # Place call right at the beginning of the ctor, before VP9 capability is cached.
    modified=code.replace(ANCHOR,'%ctor {\n    LCRegisterSupplementalVP9IfAvailable();\n    vtSupportsVP9 = VTIsHardwareDecodeSupported(kCMVideoCodecType_VP9);',1)
    header='#import "Header.h"\n'
    if modified.count(header)!=1: raise RuntimeError('YTUHD imports changed; refusing unsafe insert')
    return modified.replace(header,header+'\n'+IMPL+'\n',1)

def main():
    if not YTUHD.exists():
        print('Hardware supplemental VP9 patch skipped: original YTUHD fork selected (no Tweak.xm).')
        return 0
    code=YTUHD.read_text(encoding='utf-8')
    updated=transform(code)
    YTUHD.write_text(updated,encoding='utf-8')
    print('Applied opt-out experimental supplemental VP9 registration before YTUHD probe.')
    print('The runtime can still deny hardware decoding; inspect stats for nerds HV and dropped frames.')
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except Exception as e:
        print(f'::error::{e}',file=sys.stderr)
        sys.exit(1)
