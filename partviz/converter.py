import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import re
from pathlib import Path

import h5py
import numpy as np
from vtk import vtkCellArray, vtkPoints, vtkPolyData, vtkXMLPolyDataWriter
from vtk.util.numpy_support import numpy_to_vtk


def parse_step_keys(h5_file):
    step_items = []
    for key in h5_file.keys():
        match = re.match(r"^Step#(\d+)$", key)
        if match:
            step_items.append((key, int(match.group(1))))
            continue

        if key.isdigit():
            step_items.append((key, int(key)))

    return sorted(step_items, key=lambda item: item[1])


def to_1d_array(group, name):
    return np.asarray(group[name][()]).reshape(-1)


def get_scalar_attr(group, attr_name, default_value):
    if attr_name not in group.attrs:
        return default_value

    value = np.asarray(group.attrs[attr_name]).reshape(-1)
    if value.size == 0:
        return default_value
    return float(value[0])


def add_point_data(polydata, name, values):
    vtk_array = numpy_to_vtk(values.astype(np.float64, copy=False), deep=1)
    vtk_array.SetName(name)
    polydata.GetPointData().AddArray(vtk_array)


def write_step_vtp(step_group, output_file):
    x = to_1d_array(step_group, "x")
    y = to_1d_array(step_group, "y")
    z = to_1d_array(step_group, "z")

    n_particles = len(x)
    if not (len(y) == n_particles and len(z) == n_particles):
        raise ValueError("x, y, z arrays have different lengths")

    coordinates = np.column_stack((x, y, z)).astype(np.float64, copy=False)

    points = vtkPoints()
    points.SetData(numpy_to_vtk(coordinates, deep=1))

    verts = vtkCellArray()
    for particle_id in range(n_particles):
        verts.InsertNextCell(1)
        verts.InsertCellPoint(particle_id)

    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetVerts(verts)

    for field in ("px", "py", "pz", "q", "sp", "bin"):
        if field in step_group:
            field_values = to_1d_array(step_group, field)
            if len(field_values) == n_particles:
                add_point_data(polydata, field, field_values)

    writer = vtkXMLPolyDataWriter()
    writer.SetFileName(str(output_file))
    writer.SetInputData(polydata)
    writer.SetDataModeToBinary()
    if writer.Write() != 1:
        raise RuntimeError(f"Failed to write {output_file}")

    return n_particles


def export_step(input_file, output_file, output_name, step_key, step_number):
    with h5py.File(input_file, "r") as h5_file:
        step_group = h5_file[step_key]
        required_fields = {"x", "y", "z"}
        if not required_fields.issubset(step_group.keys()):
            return {
                "ok": False,
                "step_key": step_key,
                "error": "missing one of x/y/z",
            }

        particle_count = write_step_vtp(step_group, output_file)
        timestep = get_scalar_attr(step_group, "TIME", float(step_number))

    return {
        "ok": True,
        "step_key": step_key,
        "step_number": step_number,
        "output_name": output_name,
        "particle_count": particle_count,
        "timestep": timestep,
    }


def write_pvd_file(pvd_file, entries):
    lines = [
        "<?xml version=\"1.0\"?>",
        "<VTKFile type=\"Collection\" version=\"0.1\" byte_order=\"LittleEndian\">",
        "  <Collection>",
    ]

    for timestep, filename in entries:
        lines.append(f"    <DataSet timestep=\"{timestep:.16g}\" part=\"0\" file=\"{filename}\"/>")

    lines.extend([
        "  </Collection>",
        "</VTKFile>",
        "",
    ])
    pvd_file.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert OPAL H5 phase-space output to ParaView VTP files.")
    parser.add_argument("input", nargs="?", default="Drift-IP.h5", help="Input OPAL H5 file")
    parser.add_argument("--output-dir", default="paraview", help="Directory for VTP and PVD outputs")
    parser.add_argument("--prefix", default="bunch", help="Prefix for generated output files")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel worker processes (default: 1)")
    args = parser.parse_args(argv)

    if args.workers < 1:
        print("--workers must be >= 1")
        return 1

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {input_path}")
    with h5py.File(input_path, "r") as h5_file:
        steps = parse_step_keys(h5_file)
        if not steps:
            print("No OPAL step groups found (expected keys like Step#0 or 0).")
            return 1

    print(f"Found {len(steps)} steps. Writing VTP files to: {output_dir}")
    print(f"Using {args.workers} worker process(es).")

    jobs = []
    for step_key, step_number in steps:
        output_name = f"{args.prefix}_step{step_number:05d}.vtp"
        output_file = output_dir / output_name
        jobs.append((
            str(input_path),
            str(output_file),
            output_name,
            step_key,
            step_number,
        ))

    results = []
    if args.workers == 1:
        for job in jobs:
            try:
                result = export_step(*job)
            except Exception as exc:
                result = {
                    "ok": False,
                    "step_key": job[3],
                    "error": str(exc),
                }

            if result["ok"]:
                print(f"  Wrote {result['output_name']} ({result['particle_count']} particles)")
            else:
                print(f"Skipping {result['step_key']}: {result['error']}")
            results.append(result)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_step = {
                executor.submit(export_step, *job): (job[3], job[4])
                for job in jobs
            }

            for future in as_completed(future_to_step):
                step_key, step_number = future_to_step[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "ok": False,
                        "step_key": step_key,
                        "step_number": step_number,
                        "error": str(exc),
                    }

                if result["ok"]:
                    print(f"  Wrote {result['output_name']} ({result['particle_count']} particles)")
                else:
                    print(f"Skipping {result['step_key']}: {result['error']}")
                results.append(result)

    pvd_entries = []
    successful_results = sorted(
        (result for result in results if result["ok"]),
        key=lambda result: result["step_number"],
    )
    for result in successful_results:
        pvd_entries.append((result["timestep"], result["output_name"]))

    if not pvd_entries:
        print("No VTP files were written.")
        return 1

    pvd_file = output_dir / f"{args.prefix}.pvd"
    write_pvd_file(pvd_file, pvd_entries)
    print(f"Created ParaView collection: {pvd_file}")
    return 0
