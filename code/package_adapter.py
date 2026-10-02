"""Convert deterministic Python package prefixes to term-tree sets."""
import argparse
import hashlib
import io
import json
import tokenize
from pathlib import Path
import python_adapter
from telemetry import Recorder, TelemetryError, atomic_json


def count(root):
    todo = [root]
    n = 0
    while todo:
        node = todo.pop()
        n += 1
        todo.extend(node[1])
    return n


def convert(source_root, representation, target_nodes=None, ident='package', rec=None):
    rec = rec or Recorder()
    source_root = Path(source_root).resolve(strict=True)
    if representation not in ('compact', 'fielded'):
        raise ValueError('unknown representation')
    if target_nodes is not None and target_nodes <= 0:
        raise ValueError('target_nodes must be positive')
    files = sorted((p for p in source_root.rglob('*.py') if p.is_file()),
                   key=lambda p: p.relative_to(source_root).as_posix())
    files = [p for p in files if not any(x.startswith('.') or x == '__pycache__'
                                       for x in p.relative_to(source_root).parts)]
    roots, ranks, entries, buckets = [], {}, [], {}
    nodes = 0
    for path in files:
        relative = path.relative_to(source_root).as_posix()
        entry = {'path': relative, 'status': 'PENDING'}
        entries.append(entry)
        try:
            # Reject resolved paths outside the source root.
            path.resolve(strict=True).relative_to(source_root)
            with rec.span('package_file_conversion'):
                raw = path.read_bytes()
                entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                coding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                adapted = python_adapter.adapt(raw.decode(coding), representation)
                root = adapted['roots'][0]
                if python_adapter.decode(root, representation) != adapted['python_ast_dump']:
                    raise ValueError('AST roundtrip mismatch')
                for symbol, meta in adapted['metadata'].items():
                    arity = meta['rank']
                    if symbol in ranks and ranks[symbol] != arity:
                        raise ValueError('cross-file ranked alphabet collision')
                    ranks[symbol] = arity
                digest = hashlib.sha256(json.dumps(root, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
                # Use exact equality within each hash bucket.
                root_index = next((i for i in buckets.get(digest, []) if roots[i] == root), None)
                file_nodes = count(root)
                if root_index is None:
                    root_index = len(roots)
                    roots.append(root)
                    buckets.setdefault(digest, []).append(root_index)
                    nodes += file_nodes
                entry.update(status='INCLUDED', source_encoding=coding, root_index=root_index,
                             root_sha256=digest, file_nodes=file_nodes,
                             ast_dump_sha256=hashlib.sha256(adapted['python_ast_dump'].encode()).hexdigest())
        except Exception as error:
            if isinstance(error, TelemetryError):
                raise
            entry.update(status='CONVERSION_FAILED', error=type(error).__name__+': '+str(error))
            return None, {'status': 'CONVERSION_FAILED', 'files': entries, 'planned_files': len(files),
                          'failed_path': relative, 'representation': representation,
                          'unattempted_files': [p.relative_to(source_root).as_posix() for p in files[len(entries):]]}
        if target_nodes is not None and nodes >= target_nodes:
            break
    if not entries:
        return None, {'status': 'NO_SOURCE_FILES', 'files': [], 'planned_files': 0}
    reached = target_nodes is None or nodes >= target_nodes
    manifest = {'status': 'PREPARED' if reached else 'SIZE_NOT_REACHED', 'files': entries,
                'planned_files': len(files), 'included_files': len(entries), 'unique_roots': len(roots),
                'nodes': nodes, 'target_nodes': target_nodes, 'target_reached': reached,
                'representation': representation,
                'unattempted_files': [p.relative_to(source_root).as_posix() for p in files[len(entries):]],
                'contract': 'Literal ordered AST SET. File-to-root mapping is auxiliary, excluded from charged objective; source bytes/comments are not reconstructed.'}
    return {'id': ident, 'roots': roots, 'ranks': ranks, 'nodes': nodes,
            'representation': representation, 'file_root_mapping': entries}, manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source_root'); p.add_argument('output')
    p.add_argument('--representation', choices=['compact', 'fielded'], required=True)
    p.add_argument('--target-nodes', type=int)
    args = p.parse_args()
    output = Path(args.output)
    if output.exists() or output.with_suffix('.manifest.json').exists():
        raise FileExistsError('preserve prior preparation outputs')
    rec = Recorder(output.with_suffix('.phase.json'))
    rec.group('prepare', 300)
    with rec.span('package_conversion'):
        case, manifest = convert(args.source_root, args.representation, args.target_nodes, output.stem, rec)
        if case:
            atomic_json(output, case)
    manifest['telemetry'] = rec.result()
    atomic_json(output.with_suffix('.manifest.json'), manifest)
    print(json.dumps({k: v for k, v in manifest.items() if k not in ('files', 'telemetry')}))
    if case is None:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
