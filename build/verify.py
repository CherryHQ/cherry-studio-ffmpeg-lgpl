#!/usr/bin/env python3
"""Fail closed unless the staged runtime meets the LGPL shared-runtime gates."""
import json
import os
import re
import subprocess
import sys

stage = os.environ["STAGE"]
arch = os.path.basename(stage).rsplit("-", 1)[-1]
version = os.environ["VERSION"]
elf_machine = os.environ["ELF_MACHINE"]
source_url = os.environ["SOURCE_URL"]
source_sha = os.environ["SOURCE_SHA256"]
recipe = os.environ.get("RECIPE_COMMIT", "unknown")

binaries = [os.path.join(stage, "bin", name) for name in ("ffmpeg", "ffprobe")]
allowed_needed = {
    "libc.so.6",
    "libm.so.6",
    "libdl.so.2",
    "libpthread.so.0",
    "librt.so.1",
    "ld-linux-x86-64.so.2",
    "ld-linux-aarch64.so.1",
}
forbidden_needed = re.compile(r"lib(x264|x265|xvid|fdk|postproc|mp3lame|soxr|twolame|gnutls|ssl|crypto)")
glibc_ceiling = (2, 28)
glibcxx_ceiling = (3, 4, 25)


def run(args, env=None):
    return subprocess.check_output(args, env=env, stderr=subprocess.STDOUT, universal_newlines=True)


def fail(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


def version_tuple(text):
    return tuple(int(part) for part in text.split("."))


def readelf(path, flag):
    return run(["readelf", flag, path])


def dynamic_tags(path):
    text = readelf(path, "-d")
    tags = {}
    for line in text.splitlines():
        match = re.search(r"\((?P<tag>[A-Z_]+)\)\s+.*\[(?P<value>.*)\]", line)
        if match:
            tags.setdefault(match.group("tag"), []).append(match.group("value"))
    return tags


def needed(path):
    return dynamic_tags(path).get("NEEDED", [])


def assert_elf(path):
    header = readelf(path, "-h")
    if "ELF64" not in header:
        fail(path + " is not ELF64")
    if elf_machine not in header:
        fail(path + " machine is not " + elf_machine)
    if "DYN" not in header and "EXEC" not in header:
        fail(path + " is not a dynamic ELF")


def assert_glibc(path):
    text = readelf(path, "-V")
    observed = None
    for match in re.finditer(r"GLIBC_(\d+\.\d+)", text):
        current = version_tuple(match.group(1))
        if current > glibc_ceiling:
            fail(path + " requires GLIBC_" + match.group(1))
        if observed is None or current > observed:
            observed = current
    for match in re.finditer(r"GLIBCXX_(\d+\.\d+\.\d+)", text):
        if version_tuple(match.group(1)) > glibcxx_ceiling:
            fail(path + " requires GLIBCXX_" + match.group(1))
    return observed


def assert_rpath(path, required):
    tags = dynamic_tags(path)
    if "RUNPATH" in tags:
        fail(path + " has DT_RUNPATH; AppImage LD_LIBRARY_PATH would override it")
    rpath = ":".join(tags.get("RPATH", []))
    parts = rpath.split(":")
    if required not in parts:
        fail(path + " RPATH is " + rpath + ", expected " + required)
    if any(part.startswith("/") for part in parts):
        fail(path + " RPATH contains an absolute path: " + rpath)


def assert_config(path):
    output = run([path, "-version"], env=clean_env())
    if "--disable-gpl" not in output or "--disable-nonfree" not in output or "--disable-version3" not in output:
        fail(path + " configuration is missing the LGPL-2.1 disables")
    for forbidden in ("--enable-gpl", "--enable-nonfree", "--enable-version3", "--enable-libx264", "--enable-libx265"):
        if re.search(r"(^|\s)" + re.escape(forbidden) + r"(\s|$)", output):
            fail(path + " configuration contains " + forbidden)
    return output


def clean_env():
    env = {"PATH": "/usr/bin:/bin", "LANG": "C"}
    return env


libs = []
for dirpath, _, filenames in os.walk(os.path.join(stage, "lib")):
    for name in filenames:
        if ".so" in name:
            libs.append(os.path.join(dirpath, name))
if not libs:
    fail("no shared libraries staged")

needed_by_binary = {}
glibc_observed = (2, 0)
for binary in binaries:
    assert_elf(binary)
    assert_rpath(binary, "$ORIGIN/../lib")
    observed = assert_glibc(binary)
    if observed and observed > glibc_observed:
        glibc_observed = observed
    deps = needed(binary)
    needed_by_binary[os.path.relpath(binary, stage)] = deps
    for dep in deps:
        if forbidden_needed.search(dep):
            fail(binary + " links forbidden library " + dep)
        if dep.startswith("libav") or dep.startswith("libsw"):
            continue
        if dep not in allowed_needed:
            fail(binary + " links unexpected library " + dep)

for lib in libs:
    if os.path.islink(lib):
        continue
    assert_elf(lib)
    assert_rpath(lib, "$ORIGIN")
    observed = assert_glibc(lib)
    if observed and observed > glibc_observed:
        glibc_observed = observed
    for dep in needed(lib):
        if forbidden_needed.search(dep):
            fail(lib + " links forbidden library " + dep)
        if dep.startswith("libav") or dep.startswith("libsw"):
            continue
        if dep not in allowed_needed:
            fail(lib + " links unexpected library " + dep)

config = assert_config(binaries[0])
assert_config(binaries[1])

media = os.path.join(os.environ["STAGE"] + "-media")
os.makedirs(media)
wav = os.path.join(media, "tone.wav")
ppm = os.path.join(media, "frame.ppm")
jpg = os.path.join(media, "frame.jpg")
with open(ppm, "wb") as handle:
    handle.write(b"P6\n2 2\n255\n")
    handle.write(b"\xff\x00\x00\x00\xff\x00\x00\x00\xff\xff\xff\xff")

fake = os.path.join(media, "fake-libs")
os.makedirs(fake)
for dep in needed_by_binary["bin/ffmpeg"]:
    if dep.startswith("libav") or dep.startswith("libsw"):
        with open(os.path.join(fake, dep), "wb") as handle:
            handle.write(b"not an ELF library\n")

hostile = clean_env()
hostile["LD_LIBRARY_PATH"] = fake
hostile["LD_PRELOAD"] = ""
run([binaries[0], "-y", "-f", "s16le", "-ar", "16000", "-ac", "1", "-i", "/dev/zero", "-t", "0.1", wav], env=hostile)
probe = run(
    [binaries[1], "-v", "error", "-print_format", "json", "-show_streams", "-show_format", wav],
    env=hostile,
)
parsed = json.loads(probe)
if parsed["streams"][0]["codec_name"] != "pcm_s16le":
    fail("wav probe did not report pcm_s16le")
run(
    [binaries[0], "-y", "-i", ppm, "-frames:v", "1", "-vf", "scale=2:2", jpg],
    env=hostile,
)
image_probe = json.loads(
    run([binaries[1], "-v", "error", "-print_format", "json", "-show_streams", jpg], env=hostile)
)
if image_probe["streams"][0]["codec_name"] != "mjpeg":
    fail("jpeg probe did not report mjpeg")


def required(name):
    value = os.environ.get(name, "")
    if not value:
        fail("missing " + name)
    return value


zig_version = required("ZIG_VERSION")
zig_url = required("ZIG_URL")
zig_sha = required("ZIG_SHA256")
zig_target = required("ZIG_TARGET")
source_date_epoch = required("SOURCE_DATE_EPOCH")
if not source_date_epoch.isdigit():
    fail("SOURCE_DATE_EPOCH is not an integer")

manifest = {
    "schemaVersion": 1,
    "name": "ffmpeg-lgpl",
    "version": version,
    "arch": arch,
    "elfClass": "ELF64",
    "elfMachine": elf_machine,
    "glibcMax": ".".join(str(part) for part in glibc_ceiling),
    "glibcObserved": ".".join(str(part) for part in glibc_observed),
    "executableRpath": "$ORIGIN/../lib",
    "libraryRpath": "$ORIGIN",
    "rpathType": "RPATH",
    "license": "LGPL-2.1-only",
    "binaries": ["bin/ffmpeg", "bin/ffprobe"],
    "sharedLibraries": sorted(os.path.relpath(path, stage) for path in libs),
    "needed": needed_by_binary,
    "components": [
        {
            "name": "FFmpeg",
            "version": version,
            "license": "LGPL-2.1-only",
            "licenseFile": "licenses/ffmpeg/COPYING.LGPLv2.1",
            "source": source_url,
            "sha256": source_sha,
        }
    ],
    "systemLibraries": sorted(allowed_needed),
    "configure": config,
    "buildRunner": os.environ.get("BUILD_RUNNER", "unknown"),
    "glibcAbiPin": zig_target,
    "buildToolchain": {
        "name": "zig",
        "version": zig_version,
        "url": zig_url,
        "sha256": zig_sha,
        "target": zig_target,
        "shipped": False,
    },
    "sourceDateEpoch": int(source_date_epoch),
    "archive": {
        "format": "tar.gz",
        "sort": "name",
        "mtime": "@" + source_date_epoch,
        "owner": 0,
        "group": 0,
        "numericOwner": True,
        "gzip": "-n",
    },
    "recipeRepository": "https://github.com/CherryHQ/cherry-studio-ffmpeg-lgpl",
    "recipeCommit": recipe,
}
with open(os.path.join(stage, "manifest.json"), "w") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
    handle.write("\n")
with open(os.path.join(stage, "SOURCE.txt"), "w") as handle:
    handle.write(
        "\n".join(
            [
                "FFmpeg " + version,
                "License: LGPL-2.1-only",
                "Source: " + source_url,
                "SHA256: " + source_sha,
                "Build runner: " + os.environ.get("BUILD_RUNNER", "unknown"),
                "Build toolchain: zig " + zig_version + " (not a shipped runtime component)",
                "Build toolchain URL: " + zig_url,
                "Build toolchain SHA256: " + zig_sha,
                "Build toolchain target: " + zig_target,
                "Source date epoch: " + source_date_epoch,
                "Archive: tar --sort=name --mtime=@" + source_date_epoch + " --owner=0 --group=0 --numeric-owner | gzip -n",
                "Recipe: https://github.com/CherryHQ/cherry-studio-ffmpeg-lgpl",
                "Recipe commit: " + recipe,
                "Executable RPATH: $ORIGIN/../lib (DT_RPATH)",
                "Library RPATH: $ORIGIN (DT_RPATH)",
                "glibc ceiling: 2.28",
                "glibc observed: " + manifest["glibcObserved"],
                "Replaceable objects: lib/libav*.so* and lib/libsw*.so*",
                "No GPL-only or nonfree library is configured or linked.",
                "zlib is disabled with --disable-zlib and is not linked.",
                "System libraries are not bundled: libc, libm, libdl, libpthread, librt, and the dynamic linker.",
                "",
            ]
        )
    )
print("verified " + stage)
