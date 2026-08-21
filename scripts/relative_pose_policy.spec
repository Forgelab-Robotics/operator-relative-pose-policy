# -*- mode: python ; coding: utf-8 -*-
"""Build the relative-pose Policy Node executable."""

from pathlib import Path
import site

from PyInstaller.utils.hooks import collect_all


PROJECT_DIR = Path(SPEC).resolve().parent.parent
SRC_DIR = PROJECT_DIR / "src"


def collect_runtime():
    datas = []
    binaries = []
    hiddenimports = ["pyarrow", "yaml"]

    for package in (
        "dora",
        "forge_tool",
        "forge_msgs",
        "forge_kinematics",
        "pinocchio",
        "eigenpy",
        "coal",
        "cmeel",
    ):
        package_datas, package_binaries, package_hiddenimports = collect_all(
            package,
            include_py_files=True,
        )
        datas.extend(package_datas)
        binaries.extend(package_binaries)
        hiddenimports.extend(package_hiddenimports)

    # Pinocchio's cmeel wheels place their shared objects outside a Python
    # package. Preserve that layout because their ELF RPATHs refer to it.
    for site_dir_text in site.getsitepackages():
        site_dir = Path(site_dir_text)
        cmeel_lib = site_dir / "cmeel.prefix" / "lib"
        if not cmeel_lib.is_dir():
            continue
        for library in cmeel_lib.rglob("*.so*"):
            destination = Path("cmeel.prefix/lib") / library.parent.relative_to(cmeel_lib)
            binaries.append((str(library), str(destination)))

    return (
        list(dict.fromkeys(datas)),
        list(dict.fromkeys(binaries)),
        list(dict.fromkeys(hiddenimports)),
    )


DATAS, BINARIES, HIDDENIMPORTS = collect_runtime()


def analysis(entry, extra_paths=()):
    return Analysis(
        [str(entry)],
        pathex=[str(SRC_DIR), *(str(path) for path in extra_paths)],
        binaries=BINARIES,
        datas=DATAS,
        hiddenimports=HIDDENIMPORTS,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
        optimize=0,
    )


policy = analysis(PROJECT_DIR / "scripts" / "relative_pose_policy_entry.py")
policy_pyz = PYZ(policy.pure)
policy_exe = EXE(
    policy_pyz,
    policy.scripts,
    policy.binaries,
    policy.datas,
    [],
    name="relative_pose_policy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
