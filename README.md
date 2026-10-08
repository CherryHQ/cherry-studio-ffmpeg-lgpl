# cherry-studio-ffmpeg-lgpl

Reproducible Linux x64 and arm64 LGPL-2.1 shared FFmpeg 8.1.2 runtime for Cherry Studio.

The release tag is `ffmpeg-lgpl-v8.1.2-r1`. Assets are:

- `ffmpeg-lgpl-v8.1.2-linux-x64.tar.gz`
- `ffmpeg-lgpl-v8.1.2-linux-x64.manifest.json`
- `ffmpeg-lgpl-v8.1.2-linux-arm64.tar.gz`
- `ffmpeg-lgpl-v8.1.2-linux-arm64.manifest.json`
- `SHA256SUMS`

x64 builds on the native `ubuntu-24.04` runner. arm64 builds on the native `ubuntu-24.04-arm` runner. The workflow does not use QEMU, Docker, or cross-architecture compilation.

Ubuntu 24.04 ships glibc newer than 2.28. Each job uses Zig 0.14.1 only to pin the same architecture to the glibc 2.28 ABI (`x86_64-linux-gnu.2.28` or `aarch64-linux-gnu.2.28`). The runtime does not bundle Zig or glibc.

FFmpeg is configured with `--disable-everything` and an explicit component allowlist. zlib is disabled and is not linked. The only bundled LGPL component is FFmpeg, shipped as replaceable `lib/*.so*` files. `bin/ffmpeg` and `bin/ffprobe` use `DT_RPATH` `$ORIGIN/../lib`. The shared libraries use `DT_RPATH` `$ORIGIN`.

Each archive contains `bin/ffmpeg`, `bin/ffprobe`, `lib/*.so*`, `licenses/COPYING.LGPLv2.1`, `licenses/ffmpeg/COPYING.LGPLv2.1`, `licenses/components/ffmpeg-LGPL-2.1.txt`, `SOURCE.txt`, and `manifest.json`.
