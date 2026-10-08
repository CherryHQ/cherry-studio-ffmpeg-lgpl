#!/bin/bash
# Native LGPL-2.1 shared FFmpeg 8.1.2 build.
# x64 runs on ubuntu-24.04. arm64 runs on ubuntu-24.04-arm.
# Ubuntu 24.04's own libc is newer than glibc 2.28, so compilation uses Zig
# only as a same-architecture glibc 2.28 ABI pin. This is not QEMU, not a
# container, and not a cross-architecture compile.
set -euo pipefail

ARCH="${1:?arch must be x64 or arm64}"
MACHINE="$(uname -m)"
case "$ARCH" in
  x64)
    [ "$MACHINE" = "x86_64" ] || { echo "x64 build requires native x86_64, found $MACHINE" >&2; exit 1; }
    ZIG_ARCH="x86_64"
    ZIG_SHA256="24aeeec8af16c381934a6cd7d95c807a8cb2cf7df9fa40d359aa884195c4716c"
    ZIG_TARGET="x86_64-linux-gnu.2.28"
    ELF_MACHINE="Advanced Micro Devices X86-64"
    ;;
  arm64)
    [ "$MACHINE" = "aarch64" ] || { echo "arm64 build requires native aarch64, found $MACHINE" >&2; exit 1; }
    ZIG_ARCH="aarch64"
    ZIG_SHA256="f7a654acc967864f7a050ddacfaa778c7504a0eca8d2b678839c21eea47c992b"
    ZIG_TARGET="aarch64-linux-gnu.2.28"
    ELF_MACHINE="AArch64"
    ;;
  *)
    echo "unsupported arch: $ARCH" >&2
    exit 1
    ;;
esac

VERSION="8.1.2"
ZIG_VERSION="0.14.1"
# Pinned archive clock: 2025-05-21T00:00:00Z. Runner mtimes must not enter the tarball.
SOURCE_DATE_EPOCH=1747785600
SOURCE_URL="https://ffmpeg.org/releases/ffmpeg-${VERSION}.tar.xz"
SOURCE_SHA256="464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"
ZIG_URL="https://ziglang.org/download/${ZIG_VERSION}/zig-${ZIG_ARCH}-linux-${ZIG_VERSION}.tar.xz"
ARTIFACT="ffmpeg-lgpl-v${VERSION}-linux-${ARCH}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${ROOT}/.work-${ARCH}"
PREFIX="${WORK}/prefix"
STAGE="${WORK}/stage/${ARTIFACT}"
DIST="${ROOT}/dist"

sudo apt-get update
sudo apt-get install -y --no-install-recommends build-essential nasm pkg-config xz-utils curl python3 ca-certificates patchelf

rm -rf "$WORK"
mkdir -p "$WORK/zig" "$DIST"
curl -fL --retry 5 --retry-delay 2 -o "$WORK/zig.tar.xz" "$ZIG_URL"
echo "${ZIG_SHA256}  $WORK/zig.tar.xz" | sha256sum -c -
tar -xJf "$WORK/zig.tar.xz" -C "$WORK/zig" --strip-components=1
export PATH="${WORK}/zig:${PATH}"

cd "$WORK"
curl -fL --retry 5 --retry-delay 2 -o "ffmpeg-${VERSION}.tar.xz" "$SOURCE_URL"
echo "${SOURCE_SHA256}  ffmpeg-${VERSION}.tar.xz" | sha256sum -c -
tar -xf "ffmpeg-${VERSION}.tar.xz"
cd "ffmpeg-${VERSION}"

CC="zig cc -target ${ZIG_TARGET}"
./configure \
  --prefix="$PREFIX" \
  --cc="$CC" \
  --ar="zig ar" \
  --ranlib="zig ranlib" \
  --nm="nm" \
  --disable-everything \
  --disable-static \
  --enable-shared \
  --enable-ffmpeg \
  --enable-ffprobe \
  --enable-avcodec \
  --enable-avformat \
  --enable-avutil \
  --enable-swresample \
  --enable-swscale \
  --enable-avfilter \
  --disable-gpl \
  --disable-nonfree \
  --disable-version3 \
  --disable-debug \
  --disable-doc \
  --disable-autodetect \
  --disable-avdevice \
  --disable-network \
  --disable-iconv \
  --disable-bzlib \
  --disable-lzma \
  --disable-zlib \
  --enable-encoder=pcm_s16le,mjpeg \
  --enable-decoder=h264,hevc,aac,mp3,mp3float,pcm_s16le,pcm_s16be,pcm_s24le,pcm_f32le,vp8,vp9,opus,vorbis,mjpeg,ppm \
  --enable-muxer=wav,image2 \
  --enable-demuxer=mov,matroska,flv,mpegts,mp3,wav,ogg,avi,aac,image2,pcm_s16le \
  --enable-parser=h264,hevc,aac,opus,vp8,vp9,mjpeg \
  --enable-bsf=aac_adtstoasc \
  --enable-filter=scale,aresample,aformat,format \
  --enable-protocol=file,pipe,crypto

# Zig 0.14.1 has no nm subcommand, so configure uses the native binutils nm.
# Its glibc 2.28 headers omit sys/sysctl.h even when the symbol links.
sed -i 's/^#define HAVE_SYSCTL 1$/#define HAVE_SYSCTL 0/' config.h
sed -i 's/^HAVE_SYSCTL=yes$/!HAVE_SYSCTL=yes/' ffbuild/config.mak
if grep -q '^#define HAVE_SYSCTL 1$' config.h; then
  echo "HAVE_SYSCTL is still enabled" >&2
  exit 1
fi

make -j"$(nproc)"
make install

mkdir -p "$STAGE/bin" "$STAGE/lib" "$STAGE/licenses/ffmpeg" "$STAGE/licenses/components"
cp "$PREFIX/bin/ffmpeg" "$PREFIX/bin/ffprobe" "$STAGE/bin/"
find "$PREFIX/lib" -maxdepth 1 \( -type f -o -type l \) \( -name 'lib*.so' -o -name 'lib*.so.*' \) -exec cp -a {} "$STAGE/lib/" \;
cp COPYING.LGPLv2.1 "$STAGE/licenses/ffmpeg/COPYING.LGPLv2.1"
cp COPYING.LGPLv2.1 "$STAGE/licenses/COPYING.LGPLv2.1"
if [ -f LICENSE.md ]; then
  cp LICENSE.md "$STAGE/licenses/ffmpeg/LICENSE.md"
fi
cat > "$STAGE/licenses/components/ffmpeg-LGPL-2.1.txt" <<EOF
Component: FFmpeg ${VERSION}
License: LGPL-2.1-only
License text: licenses/ffmpeg/COPYING.LGPLv2.1
Source: ${SOURCE_URL}
SHA256: ${SOURCE_SHA256}
The shared libraries under lib/ are the replaceable FFmpeg objects.
No other LGPL or GPL component is linked into this runtime.
zlib is not linked. System glibc is used dynamically and is not bundled.
EOF

strip --strip-unneeded "$STAGE/bin/ffmpeg" "$STAGE/bin/ffprobe"
find "$STAGE/lib" -type f -name 'lib*.so*' -exec strip --strip-unneeded {} \;

# patchelf is the only source of the literal DT_RPATH.
normalize_rpath() {
  local file rpath actual
  file="$1"
  rpath="$2"
  patchelf --force-rpath --set-rpath "$rpath" "$file"
  actual="$(patchelf --print-rpath "$file")"
  if [ "$actual" != "$rpath" ]; then
    echo "rpath on $file is ${actual}, expected ${rpath}" >&2
    exit 1
  fi
}
normalize_rpath "$STAGE/bin/ffmpeg" '$ORIGIN/../lib'
normalize_rpath "$STAGE/bin/ffprobe" '$ORIGIN/../lib'
while IFS= read -r -d '' file; do
  normalize_rpath "$file" '$ORIGIN'
done < <(find "$STAGE/lib" -type f -name 'lib*.so*' -print0)

export ARTIFACT VERSION SOURCE_URL SOURCE_SHA256 STAGE ARCH ZIG_TARGET ELF_MACHINE
export ZIG_VERSION ZIG_URL ZIG_SHA256 SOURCE_DATE_EPOCH
export RECIPE_COMMIT="${GITHUB_SHA:-unknown}"
export BUILD_RUNNER="${RUNNER_LABEL:-unknown}"
python3 "$ROOT/build/verify.py"

cp "$STAGE/manifest.json" "$DIST/${ARTIFACT}.manifest.json"
# Sorted names, pinned mtime, uid/gid 0. gzip -n omits the gzip name and timestamp.
find "$STAGE" -exec touch -h -d "@${SOURCE_DATE_EPOCH}" {} +
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/bin/ffmpeg" "$STAGE/bin/ffprobe"
tar --sort=name --mtime="@${SOURCE_DATE_EPOCH}" --owner=0 --group=0 --numeric-owner \
  -C "$WORK/stage" -cf - "$ARTIFACT" | gzip -n > "$DIST/${ARTIFACT}.tar.gz"
echo "built $DIST/${ARTIFACT}.tar.gz"
