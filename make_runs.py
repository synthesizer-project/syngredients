"""
Regenerate the grids in the manifest with syncretize's Runner, in waves.

Each incident grid gets one run, which makes the incident grid and then every
Cloudy grid made from it (one Cloudy section of the run each):

    <out>/runs/<incident grid>/run.yaml    the run's config
    <out>/runs/<incident grid>/work/       its work directory
    <out>/grids/                           every grid the runs make

Each call prints the runs under way and how many runs are where and, with
--max-active, submits runs until that many are under way; call it again as
runs finish to submit the next wave. A run is under way from its submission
until its state file says it is done, so a run that crashed holds its place
until it is resumed (syncretize resume <run>/run.yaml).

Usage:
    python make_runs.py --base <base.yaml> --out <dir> [--max-active N]

The base config (see base_template.yaml) holds the Run settings every run
shares, the Cloudy settings every Cloudy section shares, and the Cloudy build
to use for each Cloudy version; a Cloudy grid whose version has no build is
left out of its run (and said so). Run it where syncretize is installed (it
submits with "python -m syncretize.runner run"), e.g. a login node with the
runs' environment loaded.

The AGN grids are left out for now: only the grids under sps/ are run.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

SYNGREDIENTS = Path(__file__).resolve().parent

#: The part of each manifest config path the grids to run sit under
RUN_ONLY = "sps/"


def load_yaml(path):
    """Load a YAML file (None when it doesn't exist).

    Args:
        path (Path)
            The file.

    Returns:
        dict or None
            Its contents.
    """
    try:
        with open(path) as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        return None


def incident_model(script):
    """The Runner's Incident.model for an incident script.

    Args:
        script (str)
            The script's path in syncretize, e.g.
            src/syncretize/incident/sps/bc03/generate_incident_grid.py.

    Returns:
        str
            Its path under src/syncretize/incident, without .py, e.g.
            sps/bc03/generate_incident_grid.
    """
    return script.removeprefix("src/syncretize/incident/").removesuffix(".py")


def plan(manifest):
    """The runs to make: one per incident grid, with its Cloudy grids.

    Args:
        manifest (dict)
            The manifest (manifest.yaml).

    Returns:
        list of dict
            Each run's "name" (its incident config's directory: the grid's
            Syndex name or, for an incident grid Syndex doesn't have, the
            Cloudy grid it was rebuilt from), "script" and "config" (the
            incident grid's) and "cloudy" (the configs of the Cloudy grids
            made from it).
    """
    runs = {}
    for grid in manifest["incident_grids"]:
        if grid["config"].startswith(RUN_ONLY):
            runs[grid["config"]] = {
                "name": Path(grid["config"]).parent.name,
                "script": grid["script"],
                "config": grid["config"],
                "cloudy": [],
            }
    for grid in manifest["cloudy_grids"]:
        if grid["config"].startswith(RUN_ONLY):
            runs[grid["incident"]]["cloudy"].append(grid["config"])
    return list(runs.values())


def run_config(run, base, out):
    """A run's Runner config.

    Args:
        run (dict)
            The run, from plan.
        base (dict)
            The base config.
        out (Path)
            The directory every run and grid goes in.

    Returns:
        (dict, list of str)
            The run config, to write to <out>/runs/<name>/run.yaml, and the
            Cloudy grids left out for want of a Cloudy build.
    """
    config = {
        "Run": {
            **base["Run"],
            "name": run["name"],
            "work_dir": "work",
            "grid_dir": str(out / "grids"),
        },
        "Incident": {
            "model": incident_model(run["script"]),
            "config": str(SYNGREDIENTS / run["config"]),
        },
    }
    left_out = []
    sections = 0
    for path in run["cloudy"]:
        cloudy_config = SYNGREDIENTS / path
        version = load_yaml(cloudy_config)["cloudy_version"]
        if version not in base["executables"]:
            left_out.append(f"{path} (Cloudy {version})")
            continue
        # The Runner's Cloudy sections: Cloudy, Cloudy2, ...
        sections += 1
        config["Cloudy" if sections == 1 else f"Cloudy{sections}"] = {
            **base.get("Cloudy", {}),
            "config": str(cloudy_config),
            "executable": base["executables"][version],
        }
    return config, left_out


def status(run_dir):
    """Where a run is, from its state file.

    Args:
        run_dir (Path)
            The run's directory.

    Returns:
        (str, dict)
            "waiting" (not submitted), "active" or "done", and its state.
    """
    state = load_yaml(run_dir / "work" / "state.yaml") or {}
    if not state:
        return "waiting", state
    return ("done" if state.get("next") == "done" else "active"), state


def submit(run_dir):
    """Submit a run with the Runner.

    Args:
        run_dir (Path)
            The run's directory, holding run.yaml.
    """
    subprocess.run(
        [sys.executable, "-m", "syncretize.runner", "run", "run.yaml"],
        cwd=run_dir,
        check=True,
    )


def main():
    """Write and submit the runs, then print where they are."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", required=True, help="The base config")
    parser.add_argument(
        "--out", required=True, help="Directory the runs and grids go in"
    )
    parser.add_argument(
        "--max-active",
        type=int,
        default=0,
        help="Submit runs until this many are under way (default: none)",
    )
    args = parser.parse_args()

    base = load_yaml(Path(args.base))
    out = Path(args.out).resolve()
    runs = plan(load_yaml(SYNGREDIENTS / "manifest.yaml"))
    states = {run["name"]: status(out / "runs" / run["name"]) for run in runs}
    active = sum(where == "active" for where, _ in states.values())

    for run in runs:
        if states[run["name"]][0] != "waiting" or active >= args.max_active:
            continue
        config, left_out = run_config(run, base, out)
        for grid in left_out:
            print(f"{run['name']}: leaving out {grid}, which has no build")
        run_dir = out / "runs" / run["name"]
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "run.yaml", "w") as file:
            yaml.safe_dump(config, file, sort_keys=False)
        submit(run_dir)
        states[run["name"]] = status(run_dir)
        active += 1

    # The runs under way, with the stage each runs next, then how many runs
    # are where
    counts = {}
    for run in runs:
        where, state = states[run["name"]]
        if where == "active":
            print(f"{state.get('next', ''):9} {run['name']}")
        counts[where] = counts.get(where, 0) + 1
    print(", ".join(f"{n} {where}" for where, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
