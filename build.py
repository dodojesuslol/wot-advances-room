# Build: python3 build.py        -> dist/EZ_ROOM_<ver>.wotmod      (release: without dev-only files)
#        python3 build.py --dev  -> dist/dev/EZ_ROOM_<ver>.wotmod  (with them, for the own PC)
# .py files under src/res are compiled with python2.7 and shipped as .pyc only.
import os, re, subprocess, sys, zipfile
DEV = '--dev' in sys.argv
# only used by the dev test room (WG replica background), left out of release builds
DEV_ONLY = ('res/gui/maps/icons/ez_room/wgfake/',)
root = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(root, 'src')
ver = re.search(r'<version>(.*?)</version>', open(os.path.join(src, 'meta.xml')).read()).group(1)
outDir = os.path.join(root, 'dist', 'dev') if DEV else os.path.join(root, 'dist')
os.makedirs(outDir, exist_ok=True)
out = os.path.join(outDir, 'EZ_ROOM_%s.wotmod' % ver)
files, dirs = [], set()
for base, _, names in os.walk(os.path.join(src, 'res')):
    for name in sorted(names):
        full = os.path.join(base, name)
        rel = os.path.relpath(full, src).replace(os.sep, '/')
        if name.endswith('.pyc') or (not DEV and rel.startswith(DEV_ONLY)):
            continue
        if name.endswith('.py'):
            dfile = rel[len('res/'):]
            subprocess.check_call(['python2.7', '-c', 'import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], dfile=sys.argv[3], doraise=True)', full, full + 'c', dfile])
            full, rel = full + 'c', rel + 'c'
        files.append((full, rel))
        parts = rel.split('/')[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add('/'.join(parts[:i]) + '/')
with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:
    z.write(os.path.join(src, 'meta.xml'), 'meta.xml')
    for d in sorted(dirs):
        z.writestr(zipfile.ZipInfo(d), b'')
    for full, rel in files:
        z.write(full, rel)
print(out)
