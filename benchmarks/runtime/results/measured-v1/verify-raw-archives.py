"""Verify published raw files/counts without executing archived figure programs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--results', type=Path, required=True)
p.add_argument('--oversize', type=Path)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
sha = lambda b: hashlib.sha256(b).hexdigest()
meta = json.loads((a.results / 'verification.json').read_text())
for archive in meta['archives']:
    raw = (a.results / archive['path']).read_bytes()
    assert len(raw) == archive['bytes'] and sha(raw) == archive['sha256']
checked, files, maps = Counter(), 0, 0
for mode in ['formal', 'smoke']:
    data = json.loads((a.results / (mode + '-results.json')).read_text())
    for section in ['native', 'direct']:
        for arm in sorted({r['arm'] for r in data[section]}):
            with zipfile.ZipFile(a.results / f'{mode}-{section}-{arm}-raw.zip') as z:
                names = z.namelist()
                assert len(names) == len(set(names))
                for group in [r for r in data[section] if r['arm'] == arm]:
                    prefix = f"{group['case']}/{section}/{arm}/"
                    for record in group['records']:
                        retained = prefix + f"retained/{record['generation']}/"
                        for name, digest in record['artifacts'].items():
                            assert sha(z.read(retained + name)) == digest
                            files += 1
                        report = json.loads(z.read(retained + 'figure.report.json'))
                        assert report['exit_code'] == record['exit_code']
                        assert report['status'] == record['status']
                        assert report['script']['sha256'] == sha(z.read(retained + 'figure.py'))
                        expected_meta = data['native_probe' if section == 'native' else 'direct_probe']['graphunslopify_version']
                        assert report['environment']['installed_optional_versions']['graphunslopify'] == expected_meta
                        checked[(mode, str(record['exit_code']))] += 1
                    if section == 'native':
                        for kind in ['edit', 'diagnostic']:
                            actual = Counter()
                            for name in names:
                                if name.startswith(prefix + 'session/runs/') and name.endswith(f'/figure.{kind}-map.json'):
                                    raw = z.read(name)
                                    actual[sha(raw)] += 1
                                    mapping = json.loads(raw)
                                    if mapping.get('image'):
                                        image = str(Path(name).parent / mapping['image']['name'])
                                        assert mapping['image']['sha256'] == sha(z.read(image))
                                    maps += 1
                            assert actual == Counter(r['map_hashes'][kind] for r in group['records'])
assert sum(checked.values()) == 1260
proof = {'scope': __doc__, 'actual_archive_count': len(meta['archives']),
         'actual_retained_file_hashes': files, 'actual_native_maps': maps,
         'actual_reports': {f'{mode}-strict{code}': value for (mode, code), value in checked.items()},
         'actual_total_reports': sum(checked.values())}
if a.oversize:
    recovered = {}
    for arm in ['accepted-inline', 'default-shared']:
        with zipfile.ZipFile(a.results / f'formal-native-{arm}-raw.zip') as z:
            for name in z.namelist():
                digest = sha(z.read(name))
                assert name not in recovered or recovered[name] == digest
                recovered[name] = digest
    with zipfile.ZipFile(a.oversize) as z:
        for name in z.namelist():
            assert recovered[name] == sha(z.read(name))
        proof['oversize_intermediate_members_all_recovered'] = len(z.namelist())
    proof['oversize_intermediate_bytes'] = a.oversize.stat().st_size
    proof['oversize_intermediate_sha256'] = sha(a.oversize.read_bytes())
a.out.write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(proof, indent=2))
