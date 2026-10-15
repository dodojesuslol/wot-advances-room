# Browser preview of the room UI: mock Gameface engine/model, rem = px, img:// -> extracted game files.
# usage: python3 -I preview.py <src gameface dir> <extracted game root> <data.json> <out.html> [click selector]
import json, sys
src, res, datafile, out = sys.argv[1:5]
click = sys.argv[5] if len(sys.argv) > 5 else ''
css = open(src + '/style.css').read().replace('img://', 'file://' + res + '/')
js = open(src + '/app.js').read().replace('img://', 'file://' + res + '/')
data = json.load(open(datafile))
html = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
@font-face { font-family: Warhelios; src: url(file://%(res)s/gui/gameface/fonts/Warhelios-Regular.ttf); }
@font-face { font-family: Warhelios; font-weight: bold; src: url(file://%(res)s/gui/gameface/fonts/Warhelios-Bold.ttf); }
html { font-size: 1px; }
%(css)s</style></head><body><div id="root"></div><script>
window.onerror = function (m, f, l) { document.body.insertAdjacentHTML('afterbegin', '<div style="position:fixed;z-index:9;background:red;color:#fff;font-size:20px">JS ERROR: ' + m + ' line ' + l + '</div>'); };
window.model = { data: %(data)s, dev: "", onAction: function (a) { console.log(JSON.stringify(a)); } };
window.engine = { whenReady: Promise.resolve(), on: function () {} };
window.viewEnv = { addDataChangedCallback: function () {} };
</script><script>%(js)s</script><script>
engine.whenReady.then(function () {}).then(function () { var s = %(click)s; if (s) s.split('|').forEach(function (q) { var el = document.querySelector(q); if (!el) { window.onerror('no element for ' + q, '', 0); return; } el.click(); }); });
</script></body></html>''' % {'res': res, 'css': css, 'js': js, 'click': json.dumps(click),
                               'data': json.dumps(json.dumps(data).replace('img://', 'file://' + res + '/'))}
open(out, 'w').write(html)
