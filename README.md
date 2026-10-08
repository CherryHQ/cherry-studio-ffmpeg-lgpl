# cherry-studio-ffmpeg-lgpl

Reproducible Linux x64 and arm64 LGPL-2.1 shared FFmpeg 8.1.2 runtime for Cherry Studio.

The release tag is `ffmpeg-lgpl-v8.1.2-r1`. Assets are:

- `ffmpeg-lgpl-v8.1.2-linux-x64.tar.gz`
- `ffmpeg-lgpl-v8.1.2-linux-x64.manifest.json`
- `ffmpeg-lgpl-v8.1.2-linux-arm64.tar.gz`
- `ffmpeg-lgpl-v8.1.2-linux-arm64.manifest.json`
- `SHA256SUMS`

x64 builds on the native `ubuntu-24.04` runner. arm64 builds on the native `ubuntu-24.04-arm` runner. The workflow does not use QEMU, Docker, or cross-architecture compilation.

Ubuntu 24.04 ships glibc newer than 2.28. Each job uses Zig 0.14.1 only to pin the same architecture to the glibc 2.28 ABI (`x86_64-linux-gnu.2.28` or `aarch64-linux-gnu.2.28`). Zig is build-toolchain provenance, not a shipped runtime component. The runtime does not bundle Zig or glibc.

`manifest.json` and `SOURCE.txt` record the exact Zig URL, version, SHA256, and target used for that archive:

- x64: `https://ziglang.org/download/0.14.1/zig-x86_64-linux-0.14.1.tar.xz`, SHA256 `24aeeec8af16c381934a6cd7d95c807a8cb2cf7df9fa40d359aa884195c4716c`, target `x86_64-linux-gnu.2.28`
- arm64: `https://ziglang.org/download/0.14.1/zig-aarch64-linux-0.14.1.tar.xz`, SHA256 `f7a654acc967864f7a050ddacfaa778c7504a0eca8d2b678839c21eea47c992b`, target `aarch64-linux-gnu.2.28`

`SOURCE_DATE_EPOCH` is pinned to `1747785600` (`2025-05-21T00:00:00Z`). After the stage is verified, member metadata is normalized and the archive is packed with:

```bash
find "$STAGE" -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/bin/ffmpeg" "$STAGE/bin/ffprobe"
tar --sort=name --mtime="@${SOURCE_DATE_EPOCH}" --owner=0 --group=0 --numeric-owner \
  -C "$WORK/stage" -cf - "$ARTIFACT" | gzip -n > "$ARTIFACT.tar.gz"
```

Names are sorted, mtimes are the pinned epoch, uid and gid are 0, and `gzip -n` omits the gzip filename and timestamp.

FFmpeg is configured with `--disable-everything` and an explicit component allowlist. zlib is disabled and is not linked. The only bundled LGPL component is FFmpeg, shipped as replaceable `lib/*.so*` files. `bin/ffmpeg` and `bin/ffprobe` use `DT_RPATH` `$ORIGIN/../lib`. The shared libraries use `DT_RPATH` `$ORIGIN`.

Each archive contains `bin/ffmpeg`, `bin/ffprobe`, `lib/*.so*`, `licenses/COPYING.LGPLv2.1`, `licenses/ffmpeg/COPYING.LGPLv2.1`, `licenses/components/ffmpeg-LGPL-2.1.txt`, `SOURCE.txt`, and `manifest.json`.
