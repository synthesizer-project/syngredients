"""
Build parameter files for every grid in the Syndex catalogue.

Reads each grid's metadata from the Syndex API and writes, per incident grid,
a directory holding the incident script's parameter file (incident.yaml) and
one Cloudy parameter file per photoionised grid made from it. The Cloudy file
is named after the part of the Syndex filename following "_cloudy-", so the
Cloudy pipeline names its output as the published grid was named.
manifest.yaml lists every Syndex grid with the files and script that make it.

Usage:
    python build_configs.py [--cache <dir>] [--syncretize <dir>]

--cache keeps the downloaded metadata in <dir> so reruns skip the API.
--syncretize is the syncretize checkout, read for the FSPS
variable-IMF templates (default: ../syncretize).
"""

import argparse
import json
import math
import re
import shutil
import time
import urllib.request
from pathlib import Path

import yaml

API = "https://data.synthesizer-project.org/v1"
OUT = Path(__file__).resolve().parent
SPS = "src/syncretize/incident/sps"
AGN = "src/syncretize/incident/blackholes"
FSPS_CONFIGS = OUT.parent / "syncretize" / SPS / "fsps" / "configs"
MSUN_KG = 1.98841586e30

# Cloudy axes, and the parameter file key that makes each one
CLOUDY_AXES = {
    "ionisation_parameters": "ionisation_parameter",
    "hydrogen_densities": "hydrogen_density",
    "column_densities": "stop_column_density",
    "turbulences": "turbulence",
    "metallicities": "metallicities",
}


def fetch(url):
    """GET a JSON document, waiting out Syndex's rate limit."""
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": "syncretize"})
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)
        except (urllib.error.HTTPError, json.JSONDecodeError):
            time.sleep(2**attempt)
    raise RuntimeError(f"Could not fetch {url}")


def load_catalogue(cache):
    """Return every grid dataset with its full metadata."""
    listing = fetch(f"{API}/datasets?data_type=grid&limit=1000")["datasets"]
    datasets = []
    for entry in listing:
        path = cache / f"{entry['name']}.json" if cache else None
        if path and path.exists():
            datasets.append(json.loads(path.read_text()))
            continue
        data = fetch(f"{API}/datasets/{entry['name']}")
        if path:
            path.write_text(json.dumps(data))
        datasets.append(data)
    return datasets


def clean(value):
    """Round away float noise (e.g. 1.7000000000000002 -> 1.7)."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, float):
        return float(f"{value:.10g}")
    return value


def log10(values):
    return [round(math.log10(v), 4) for v in values]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace(".", "p")).strip(
        "-"
    )


def sps_incident(grid, axes):
    """Return (family, script, params) for an SPS incident grid."""
    mp = grid["model_parameters"]
    name = mp["sps_name"]

    if name == "bc03":
        return (
            "bc03",
            f"{SPS}/bc03/generate_incident_grid.py",
            {"isochrones": "Padova2000", "imf_type": mp["imf_type"]},
        )
    if name == "bc03-2016":
        return (
            "bc03-2016",
            f"{SPS}/bc03/generate_incident_grid_2016.py",
            {"variant": mp["sps_variant"], "imf_type": mp["imf_type"]},
        )
    if name == "bpass" and mp["sps_version"] == "2.2.1":
        return (
            "bpass-2.2.1",
            f"{SPS}/bpass/generate_incident_grid_2_2_1.py",
            {"model": mp["original_model_name"], "variant": mp["sps_variant"]},
        )
    if name == "bpass":
        alpha = "axis" if "alpha_enhancement" in axes else mp["alpha"]
        return (
            "bpass-2.3",
            f"{SPS}/bpass/generate_incident_grid_2_3.py",
            {
                "model": mp["original_model_name"],
                "variant": mp["sps_variant"],
                "alpha_enhancement": alpha,
            },
        )
    if name == "fsps" and "variable_imf_parameter" in mp:
        return fsps_variable_imf(mp, axes)
    if name == "fsps":
        params = {"imf_type": mp["imf_type"], "imf_masses": mp["imf_masses"]}
        if mp["imf_type"] == "bpl":
            params["imf_slopes"] = mp["imf_slopes"]
        return "fsps-3.2", f"{SPS}/fsps/generate_incident_grid.py", params
    if name == "maraston13":
        return (
            "maraston13",
            f"{SPS}/maraston/generate_incident_grid_2013.py",
            {"imf_type": mp["imf_type"]},
        )
    if name == "maraston24":
        # Variants are written several ways: "0.40", "Tenc40", "Tenc_0.40"
        variant = mp["sps_variant"]
        digits = re.sub(r"[^0-9]", "", variant)
        return (
            "maraston24",
            f"{SPS}/maraston/generate_incident_grid_2024.py",
            {
                "imf_type": mp["imf_type"],
                "rotation": int(digits) / 100,
                "model_type": "Tenc" if variant.startswith("Tenc") else "Te",
            },
        )
    if name == "yggdrasil":
        populations = {
            (50, 500): "PopIII.1",
            (10, 1, 500): "PopIII.2",
            (0.1, 100): "PopIII_kroupa",
        }
        fcov = re.search(r"fcov_([0-9.]+)", mp["sps_variant"])
        return (
            "yggdrasil",
            f"{SPS}/yggdrasil/generate_incident_grid.py",
            {
                "population": populations[tuple(mp["imf_masses"])],
                # The script's choices are written 0, 0.5 and 1
                "covering_fraction": {"0.5": 0.5, "1": 1}[fcov.group(1)]
                if fcov
                else 0,
            },
        )
    raise ValueError(f"No incident mapping for SPS model {name}")


def fsps_variable_imf(mp, axes):
    """Copy the repository's variable-IMF config with Syndex's axis values."""
    config_name = {
        "high_mass_slope": "variable_high_mass_slope.yaml",
        "slope": "variable_single_slope.yaml",
    }[mp["variable_imf_parameter"]]
    config = yaml.safe_load((FSPS_CONFIGS / config_name).read_text())
    config["model"]["sps_version"] = mp["sps_version"]
    for entry in config["imf"]["slopes"] + config["imf"]["mass_boundaries"]:
        if entry.get("vary_axis"):
            entry["axis"].pop("range", None)
            entry["axis"]["values"] = axes[entry["axis"]["name"]]
    return (
        "fsps-4.0",
        f"{SPS}/fsps/generate_incident_grid_variable_imf.py",
        config,
    )


def agn_incident(grid, axes, stem):
    """Return (family, script, params) for an AGN incident grid."""
    mp = grid["model_parameters"]
    family = mp["family"]
    # Masses are stored in kg, or in Msun (a unit like 1.988e+30*kg)
    masses = axes["masses"]
    if axes["masses_units"] == "kg":
        masses = [m / MSUN_KG for m in masses]
    params = {
        # The script writes <model>.hdf5; some files were renamed after
        # generation, so use the filename rather than the stored name
        "model": stem,
        "log10masses": log10(masses),
        "log10accretion_rates_eddington": log10(
            axes["accretion_rates_eddington"]
        ),
        # Syndex does not record the fixed inclination of isotropic grids;
        # the repository's isotropic parameter files all use 0.5
        "cosine_inclinations": axes.get("cosine_inclinations", 0.5),
    }
    if "spins" in axes:
        params["spins"] = axes["spins"]
    elif family == "relagn":
        # Every fixed-efficiency RELAGN grid uses 0.1 (in its name)
        params["radiative_efficiencies"] = [0.1]
    return family, f"{AGN}/{family}/generate_incident_grid.py", params


def cloudy_params(grid, cloudy_axes):
    """Rebuild a Cloudy parameter file from Syndex's flattened parameters."""
    params = {}
    for key, value in grid["photoionisation_parameters"].items():
        value = None if value == "None" else value
        if key == "alpha":  # older name for alpha_enhancement
            key = "alpha_enhancement"
        if "." in key:
            outer, inner = key.split(".", 1)
            params.setdefault(outer, {})[inner] = value
        else:
            params[key] = value
    # Syndex's cloudy_version can be stale (see the c25.00 corrections)
    params["cloudy_version"] = grid["photoionisation_code_version"]
    for axis, values in cloudy_axes.items():
        params[CLOUDY_AXES[axis]] = values
    return params


class Dumper(yaml.SafeDumper):
    """Write mappings as blocks and lists of numbers or strings inline."""


Dumper.add_representer(
    list,
    lambda dumper, data: dumper.represent_sequence(
        "tag:yaml.org,2002:seq",
        data,
        flow_style=not any(isinstance(v, (dict, list)) for v in data),
    ),
)


def dump(path, header, params):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.dump(
        clean(params),
        Dumper=Dumper,
        sort_keys=False,
        default_flow_style=False,
        width=79,
    )
    comment = "".join(f"# {line}".rstrip() + "\n" for line in header)
    path.write_text(f"{comment}\n{body}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--cache", type=Path, help="metadata cache directory")
    parser.add_argument("--syncretize", type=Path, help="syncretize checkout")
    args = parser.parse_args()
    if args.syncretize:
        global FSPS_CONFIGS
        FSPS_CONFIGS = args.syncretize / SPS / "fsps" / "configs"
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)

    # Everything under sps/ and agn/ is generated; start afresh
    for generated in ("sps", "agn"):
        shutil.rmtree(OUT / generated, ignore_errors=True)

    datasets = load_catalogue(args.cache)
    by_release = {d["current_release"]["release_id"]: d for d in datasets}

    incidents = {}  # incident directory -> manifest entry
    cloudy = []

    def axes_of(grid):
        axes = {a["name"]: clean(a["values"]) for a in grid["axes"]}
        for a in grid["axes"]:
            axes[f"{a['name']}_units"] = a["units"]
        return axes

    def add_incident(grid, axes, syndex_name, filename, notes, user=None):
        """Write incident.yaml (once) and return its directory.

        user names the Cloudy grid needing an unpublished incident grid, used
        to tell apart unpublished incident grids sharing a name.
        """
        stem = filename.removesuffix(".hdf5")
        if grid["grid_type"] == "sps":
            family, script, params = sps_incident(grid, axes)
            family = f"sps/{family}"
        else:
            family, script, params = agn_incident(grid, axes, stem)
            family = f"agn/{family}"
        no_input_dir = family.startswith("agn") or "/fsps/" in script
        directory = f"{family}/{syndex_name or slug(stem)}"
        if directory in incidents and incidents[directory]["params"] != params:
            # Same name, different axes: rename so outputs do not collide
            directory = f"{family}/{user}-incident"
            notes = notes + [
                f"Published under the name {params['model']}, like "
                f"{slug(stem)} which has different axes, so renamed to {user}."
            ]
            params["model"] = user
        if directory not in incidents:
            header = [
                f"Syndex: {syndex_name or 'unpublished (Cloudy input only)'}",
                f"File: {filename}",
                "",
                f"python {script} \\",
                f"    <syngredients>/{directory}/incident.yaml \\",
                "    --grid-dir <grid-dir>"
                + ("" if no_input_dir else " --input-dir <input-dir>"),
                *[f"NOTE: {n}" for n in notes],
            ]
            dump(OUT / directory / "incident.yaml", header, params)
            incidents[directory] = {
                "syndex_name": syndex_name,
                "syndex_filename": filename,
                "script": script,
                "config": f"{directory}/incident.yaml",
                "notes": notes,
                "params": params,
            }
        return directory

    def order(d):
        # Where two unpublished incident grids share a name, the one whose
        # Cloudy grids are named after it keeps the name
        stem = d["current_release"]["file"]["filename"].split("_cloudy-")[0]
        return (not d["name"].startswith(slug(stem)), d["name"])

    for d in sorted(datasets, key=order):
        release = d["current_release"]
        grid = release["grid"]
        filename = release["file"]["filename"]
        axes = axes_of(grid)
        is_cloudy = grid["photoionisation_code"] == "Cloudy"

        if not is_cloudy:
            add_incident(grid, axes, d["name"], filename, [])
            continue

        # Split the axes into the incident grid's and Cloudy's
        incident_axes = dict(axes)
        cloudy_axes = {}
        for a in grid["axes"]:
            agn_metal = (
                grid["grid_type"] == "agn" and a["name"] == "metallicities"
            )
            if a["name"] in CLOUDY_AXES and (
                a["name"] != "metallicities" or agn_metal
            ):
                cloudy_axes[a["name"]] = incident_axes.pop(a["name"])

        notes = []
        if not grid["has_spectra"] and not grid["has_lines"]:
            notes.append(
                "Published with ionising luminosities only (no spectra or "
                "lines)."
            )

        parent = by_release.get(grid["incident_release_id"])
        if parent:
            pgrid = parent["current_release"]["grid"]
            paxes = axes_of(pgrid)
            for k, v in incident_axes.items():
                if k.endswith("_units") or paxes.get(k) == v:
                    continue
                n = sum(a != b for a, b in zip(v, paxes.get(k, [])))
                notes.append(
                    f"Its {k} axis differs from {parent['name']}'s at {n} of "
                    f"{len(v)} points, so it was made from another version of "
                    "that incident grid."
                )
            directory = add_incident(
                pgrid,
                paxes,
                parent["name"],
                parent["current_release"]["file"]["filename"],
                [],
            )
        else:
            stem = filename.split("_cloudy-")[0]
            inc_notes = [
                "Incident grid not in Syndex; rebuilt from the axes of "
                f"{d['name']}."
            ]
            directory = add_incident(
                grid, incident_axes, None, f"{stem}.hdf5", inc_notes, d["name"]
            )

        suffix = filename.removesuffix(".hdf5").split("_cloudy-", 1)[1]
        config = f"{directory}/{suffix}.yaml"
        if any(c["config"] == config for c in cloudy):
            raise ValueError(f"Two grids would share {config}")
        header = [
            f"Syndex: {d['name']}",
            f"File: {filename}",
            f"Incident: {directory}/incident.yaml",
            *[f"NOTE: {n}" for n in notes],
        ]
        dump(OUT / config, header, cloudy_params(grid, cloudy_axes))
        cloudy.append(
            {
                "syndex_name": d["name"],
                "syndex_filename": filename,
                "incident": f"{directory}/incident.yaml",
                "config": config,
                "notes": notes,
            }
        )

    for entry in incidents.values():
        del entry["params"]
    manifest = {
        "incident_grids": list(incidents.values()),
        "cloudy_grids": cloudy,
    }
    (OUT / "manifest.yaml").write_text(
        "# Generated by build_configs.py from the Syndex catalogue; do not "
        "edit.\n" + yaml.safe_dump(manifest, sort_keys=False, width=79)
    )
    print(f"{len(incidents)} incident and {len(cloudy)} Cloudy configs")


if __name__ == "__main__":
    main()
