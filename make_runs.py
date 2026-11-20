"""
Regenerate the grids in the manifest with syncretize's Runner, in waves.

Each grid gets a run directory holding the Runner's run config (run.yaml) and
its work directory:

    <out>/runs/<incident grid>/            an incident-only run
    <out>/runs/<Cloudy grid>/              a Cloudy run on that incident grid
    <out>/grids/                           every grid the runs make

An incident grid is made once, by its own run, and every Cloudy grid made from
it uses it (the Runner's Incident.grid), so a Cloudy run is only written and
submitted once its incident run is done.

Each call prints every run's status and, with --max-active, submits runs
(incident runs first) until that many are under way; call it again as runs
finish to submit the next wave. A run is under way from its submission until
its state file says it is done, so a run that crashed holds its place until
it is resumed (syncretize resume <run>/run.yaml).

Usage:
    python make_runs.py --base <base.yaml> --out <dir> [--max-active N]

The base config (see base_template.yaml) holds the Run settings every run
shares, the Cloudy settings every Cloudy run shares, and the Cloudy build to
use for each Cloudy version. Run it where syncretize is installed (it submits
with "python -m syncretize.runner run"), e.g. a login node with the run's
environment loaded.

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
    """The runs to make, incident runs first.

    Args:
        manifest (dict)
            The manifest (manifest.yaml).

    Returns:
        list of dict
            Each run's "name" (its directory's), "kind" ("incident" or
            "cloudy"), "config" (its syngredients config) and, for an
            incident run, "script", or for a Cloudy run, "incident" (the name
            of the incident run it needs).
    """
    runs = []
    # An incident run is named after its config's directory, which is the
    # grid's Syndex name (or, for an incident grid Syndex doesn't have, the
    # name of the Cloudy grid it was rebuilt from)
    for grid in manifest["incident_grids"]:
        if grid["config"].startswith(RUN_ONLY):
            runs.append(
                {
                    "name": Path(grid["config"]).parent.name,
                    "kind": "incident",
                    "config": grid["config"],
                    "script": grid["script"],
                }
            )
    for grid in manifest["cloudy_grids"]:
        if grid["config"].startswith(RUN_ONLY):
            runs.append(
                {
                    "name": grid["syndex_name"],
                    "kind": "cloudy",
                    "config": grid["config"],
                    "incident": Path(grid["incident"]).parent.name,
                }
            )
    names = [run["name"] for run in runs]
    if len(set(names)) != len(names):
        raise ValueError("Two runs would share a name")
    return runs


def run_config(run, base, out, incident_grid=None):
    """A run's Runner config.

    Args:
        run (dict)
            The run, from plan.
        base (dict)
            The base config.
        out (Path)
            The directory every run and grid goes in.
        incident_grid (str)
            The incident grid a Cloudy run uses.

    Returns:
        dict
            The run config, to write to <out>/runs/<name>/run.yaml.
    """
    config = {
        "Run": {
            **base["Run"],
            "name": run["name"],
            "work_dir": "work",
            "grid_dir": str(out / "grids"),
        }
    }
    if run["kind"] == "incident":
        config["Incident"] = {
            "model": incident_model(run["script"]),
            "config": str(SYNGREDIENTS / run["config"]),
        }
        return config
    cloudy_config = SYNGREDIENTS / run["config"]
    version = load_yaml(cloudy_config)["cloudy_version"]
    if version not in base["executables"]:
        raise ValueError(
            f"{run['name']} needs Cloudy {version}, which the base config's "
            "executables don't give"
        )
    config["Incident"] = {"grid": incident_grid}
    config["Cloudy"] = {
        **base.get("Cloudy", {}),
        "config": str(cloudy_config),
        "executable": base["executables"][version],
    }
    return config


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
    """Write and submit the runs, then print where every run is."""
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
        where, _ = states[run["name"]]
        if where != "waiting" or active >= args.max_active:
            continue
        incident_grid = None
        if run["kind"] == "cloudy":
            # A Cloudy run waits for its incident grid
            incident_where, incident_state = states[run["incident"]]
            if incident_where != "done":
                continue
            incident_grid = incident_state["grid"]
        try:
            config = run_config(run, base, out, incident_grid)
        except ValueError as error:
            # e.g. a Cloudy version with no build yet: the others go on
            print(f"Not submitting {run['name']}: {error}")
            continue
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
            print(f"{run['kind']:8} {state.get('next', ''):9} {run['name']}")
        if where == "waiting" and run["kind"] == "cloudy":
            if states[run["incident"]][0] != "done":
                where = "waiting for incident"
        counts[where] = counts.get(where, 0) + 1
    print(", ".join(f"{n} {where}" for where, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
