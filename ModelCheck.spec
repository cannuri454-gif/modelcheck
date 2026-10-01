# PyInstaller build definition for the Windows development distribution.
from pathlib import Path

a = Analysis(['run.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['matplotlib', 'pytest'], noarchive=False)

# Qt 6 uses Windows' native ICU API. Some Python environments have a different
# icuuc.dll on their dependency search path. Bundling that DLL can shadow the
# system implementation and cause a missing-procedure error at Qt startup.
# Windows 11 is the supported packaging target; use its native ICU instead.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ModelCheck',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ModelCheck')
