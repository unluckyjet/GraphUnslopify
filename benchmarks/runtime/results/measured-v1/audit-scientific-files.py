"""Read installed scientific distribution files; exclude metadata, caches and scripts."""
import argparse
import hashlib
import importlib.metadata as m
import json
from pathlib import Path
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
result = {'interpreter': sys.executable,
          'interpreter_binary_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
          'scope': __doc__, 'distributions': {}}
for name in 'matplotlib pandas numpy pillow pypdf typing_extensions jsonschema scipy plotly pyarrow python-calamine'.split():
    d = m.distribution(name)
    files = {}
    for f in d.files or []:
        if '..' in f.parts or f.is_absolute() or any(n.endswith('.dist-info') for n in f.parts):
            continue
        if '__pycache__' in f.parts or f.suffix == '.pyc':
            continue
        path = Path(d.locate_file(f))
        if path.is_file():
            raw = path.read_bytes()
            files[str(f)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    assert files, name
    result['distributions'][name] = {'version': d.version, 'files': files}
a.out.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'distributions': len(result['distributions']),
                  'files': sum(len(d['files']) for d in result['distributions'].values())}))
