#!/usr/bin/env python3
"""Safely extract the exact four approved PNG images."""
import pathlib, sys, zipfile

def unpack(zippath, dest):
    dest = pathlib.Path(dest)
    expected = {'primary.png', 'alternate.png', 'dark-boot.png', 'light-boot.png'}
    with zipfile.ZipFile(zippath) as z:
        names = z.namelist()
        if set(names) != expected or len(names) != 4:
            raise ValueError('Expected precisely four approved PNG files')
        if sum(x.file_size for x in z.infolist()) > 20_000_000:
            raise ValueError('Approved assets exceed limit')
        for info in z.infolist():
            if info.is_dir() or info.file_size > 8_000_000 or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Unsafe asset entry')
        dest.mkdir(parents=True, exist_ok=True)
        for name in sorted(expected):
            (dest / name).write_bytes(z.read(name))

if __name__ == '__main__':
    unpack(sys.argv[1], sys.argv[2])
    print('Four approved PNG assets checked')
