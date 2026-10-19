#!/usr/bin/env python3
"""Verified Mach-O load-command injector for Theos Jailed on modern iOS.

The bundled Theos Jailed insert_dylib binary silently fails on the supplied
YouTube 21.41.5 executable. This replacement supports its exact CLI, uses a
current LIEF Mach-O writer and proves the load command was added before
atomically replacing the original binary. It does not sign an executable.
SideStore must sign the resulting IPA later.
"""
import argparse
import os
from pathlib import Path
import stat
import sys
import tempfile


def slices(parsed):
    if parsed is None:
        raise ValueError("Not a readable Mach-O binary")
    if hasattr(parsed, "size") and hasattr(parsed, "at"):
        return [parsed.at(i) for i in range(parsed.size)]
    if hasattr(parsed, "size") and hasattr(parsed, "__getitem__"):
        return [parsed[i] for i in range(parsed.size)]
    return [parsed]


def current_libraries(binary):
    return {str(library.name) for library in binary.libraries}


def inject(binary_path: Path, library: str, lief_module=None):
    """Return a structured result and preserve original bytes on any failure."""
    if not library.startswith("@rpath/") or len(library) > 512:
        raise ValueError("Expected a validated @rpath dylib load command")
    if any(ord(c) < 33 or ord(c) == 127 for c in library):
        raise ValueError("Invalid characters in dylib load command")
    if not binary_path.is_file() or binary_path.is_symlink():
        raise ValueError("Mach-O input missing or unexpectedly symlinked")
    if lief_module is None:
        import lief as lief_module
    parsed = lief_module.MachO.parse(str(binary_path))
    architectures = slices(parsed)
    if not architectures or any(arch is None for arch in architectures):
        raise ValueError("Mach-O architecture parse failed")
    for arch in architectures:
        if library in current_libraries(arch):
            continue
        # LIEF 1.0.0 requires all Mach-O dylib version fields explicitly.
        cmd = lief_module.MachO.DylibCommand.weak_lib(library, 0, 0, 0)
        if arch.add(cmd) is None:
            raise ValueError("LIEF refused to append a Mach-O load command")

    fd, tmpname = tempfile.mkstemp(
        prefix=".circleci-macho-inject-", suffix=".bin",
        dir=str(binary_path.parent)
    )
    os.close(fd)
    tmp = Path(tmpname)
    try:
        parsed.write(str(tmp))
        if not tmp.is_file() or tmp.stat().st_size < 4096:
            raise ValueError("Mach-O writer returned a truncated binary")
        verified = slices(lief_module.MachO.parse(str(tmp)))
        if len(verified) != len(architectures) or any(
            arch is None or library not in current_libraries(arch)
            for arch in verified
        ):
            raise ValueError("Written Mach-O did not retain the load command")
        original_mode = stat.S_IMODE(binary_path.stat().st_mode)
        tmp.chmod(original_mode)
        os.replace(tmp, binary_path)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inplace", action="store_true")
    parser.add_argument("--weak", action="store_true")
    parser.add_argument("--no-strip-codesig", action="store_true")
    parser.add_argument("--all-yes", action="store_true")
    parser.add_argument("library")
    parser.add_argument("binary", type=Path)
    options = parser.parse_args()
    if not options.inplace or not options.weak:
        parser.error("Theos Jailed must use --inplace --weak")
    try:
        import lief
        inject(options.binary, options.library, lief)
    except (OSError, RuntimeError, ValueError, ImportError, AttributeError) as exc:
        # Avoid printing a binary path that might contain sensitive filenames.
        print("Mach-O load-command injection failed: " + type(exc).__name__,
              file=sys.stderr)
        return 2
    print("Verified Mach-O load command added: " + options.library)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
