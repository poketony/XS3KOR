"""Publish one fully validated result without truncating the previous result."""

import os
from pathlib import Path


def validate_outputs(paths, inputs=(), overwrite=True):
    """Reject collisions for the whole batch before publishing its first file."""
    inputs = tuple(Path(path) for path in inputs)
    protected_paths = {path.resolve() for path in inputs}
    protected_ids = {(path.stat().st_dev, path.stat().st_ino) for path in inputs}
    output_paths, output_ids = set(), set()
    for value in paths:
        path = Path(value)
        resolved = path.resolve()
        if resolved in protected_paths or resolved in output_paths:
            raise ValueError(f'Output aliases an input or another output: {path}')
        output_paths.add(resolved)
        if path.with_name(path.name+'.pending').exists():
            raise FileExistsError(f'Inspect interrupted output: {path}.pending')
        if path.exists():
            if not overwrite:
                raise FileExistsError(f'Extraction never overwrites existing files: {path}')
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            if identity in protected_ids or identity in output_ids:
                raise ValueError(f'Output aliases an input or another output: {path}')
            output_ids.add(identity)


def write_output(path, data, inputs=(), overwrite=True):
    path = Path(path)
    for source in inputs:
        source = Path(source)
        if path.resolve() == source.resolve() or (
            path.exists() and source.exists() and path.samefile(source)
        ):
            raise ValueError(f"Output would overwrite an input: {path}")
    if not overwrite:
        with path.open("xb") as stream:
            stream.write(data)
        return
    pending = path.with_name(path.name + ".pending")
    # A pending file left by an interrupted write is evidence, not disposable input.
    with pending.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)
