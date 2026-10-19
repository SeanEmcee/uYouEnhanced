#!/usr/bin/env python3
import sys,zipfile,plistlib
def verify(path):
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        if bad: raise ValueError("Corrupt ZIP member "+bad)
        plist=plistlib.loads(z.read("Payload/Nyxian.app/Info.plist"))
        if plist.get("CFBundleExecutable")!="Nyxian": raise ValueError("Unexpected executable")
        if "Payload/Nyxian.app/Nyxian" not in z.namelist(): raise ValueError("Executable missing")
        if "Payload/Nyxian.app/Assets.car" not in z.namelist(): raise ValueError("Compiled assets missing")
        if len(z.read("Payload/Nyxian.app/Assets.car"))<1000: raise ValueError("Assets.car too small")
        if "CrimsonAlternate" not in str(plist.get("CFBundleIcons",{})):
            raise ValueError("Alternate icon not declared by compiled Info.plist")
    print("Unsigned Nyxian IPA has expected structure and icon declaration")
if __name__=="__main__": verify(sys.argv[1])
