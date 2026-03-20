# partviz

Convert OPAL H5 phase-space output into ParaView `.vtp` files plus a `.pvd` collection file.

## Features

- Reads OPAL step groups named like `Step#0` or `0`
- Writes one VTP file per step
- Writes a ParaView collection file (`<prefix>.pvd`)
- Supports parallel export with `--workers`

## Installation

### Local editable install

```bash
python -m pip install -e .
```

### Install from GitHub

```bash
python -m pip install "git+https://github.com/<your-username>/partviz.git"
```

## Usage

After install, use the CLI entrypoint:

```bash
partviz-convert Drift-IP.h5 --output-dir paraview --prefix bunch --workers 4
```

You can also run via module:

```bash
python -m partviz Drift-IP.h5 --output-dir paraview --prefix bunch --workers 4
```

Backward-compatible script usage still works:

```bash
python convert-h5.py Drift-IP.h5 --output-dir paraview --prefix bunch --workers 4
```

## CLI Options

- `input` (optional): input OPAL H5 file (default: `Drift-IP.h5`)
- `--output-dir`: output directory for `.vtp` and `.pvd` files (default: `paraview`)
- `--prefix`: output filename prefix (default: `bunch`)
- `--workers`: number of worker processes (default: `1`)

## Development

Run directly from source:

```bash
python -m partviz --help
```

## Output

A typical run creates:

- `paraview/bunch_step00000.vtp`
- `paraview/bunch_step00001.vtp`
- `...`
- `paraview/bunch.pvd`

Open the `.pvd` file in ParaView for time-series visualization.
