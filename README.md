# syngredients

Parameter files that regenerate every grid in the
[Syndex catalogue](https://synthesizer-project.org/syndex) with the scripts in
[syncretize](https://github.com/synthesizer-project/syncretize).
They are generated from the catalogue's metadata; do not edit them by hand. To
regenerate them after the catalogue changes, run:

```
python build_configs.py [--cache <dir>] [--syncretize <dir>]
```

`--syncretize` is a syncretize checkout (default `../syncretize`),
read for the FSPS variable-IMF templates.

## Running a grid

Script paths in the headers and the manifest are relative to the
syncretize checkout; `<syngredients>` is this repository. For example,
from syncretize:

```
python src/syncretize/incident/sps/bc03/generate_incident_grid.py \
    <syngredients>/sps/bc03/bc03-2003-padova2000-chabrier03-0p1-100/incident.yaml \
    --grid-dir <grid-dir> --input-dir <input-dir>
```

## Layout

```
manifest.yaml                    every grid, with its script and files
sps/<model>/<incident grid>/
    incident.yaml                incident grid parameters
    <cloudy suffix>.yaml         one per Cloudy grid made from it
agn/<model>/<incident grid>/     the same for AGN models
```

Incident grid directories are named after their Syndex name. A Cloudy file is
named after the part of the Syndex filename following `_cloudy-`
(for example `c23.01-sps.yaml`), because the Cloudy pipeline names its output
`<incident>_cloudy-<parameter file name>.hdf5`. Each Cloudy file holds the full
parameter set, so no `--cloudy-paramfile-extra` is needed.

`manifest.yaml` has two lists. Run the `incident_grids` first, then the
`cloudy_grids`; each Cloudy entry names the incident config it needs. The
header of each YAML gives the command that runs it.

Five incident grids were only ever used as Cloudy inputs and are not in Syndex.
Their parameters come from the incident axes of the Cloudy grids made from them.

## Known differences from the published grids

These come from the catalogue metadata and are recorded as `notes` in the
manifest and as `NOTE` lines in the YAML headers:

- The 10 BC03 2016 Cloudy grids were made from an earlier version of their
  incident grids. The first age was 1e5 yr, not the current 1 yr.
- The QSOSED test grid `qsosed-cloudy-agn-test` was published with the same
  filename as `qsosed-test-agn-cloudy-c23p01`, but its incident grid has two
  inclinations, not three. Its incident model is renamed to
  `qsosed-cloudy-agn-test` so the two outputs do not collide.
- Three grids were published with ionising luminosities only (no spectra or
  lines). Their notes say which ones.

Some things Syndex doesn't record, so these files assume them:

- Isotropic QSOSED grids use `cosine_inclinations: 0.5`, the value in the
  isotropic parameter files in syncretize.
- Fixed-efficiency RELAGN grids use `radiative_efficiencies: [0.1]`, as in
  their names.
- FSPS uses whatever libraries it was compiled with: MIST and MILES for the
  3.2 grids, MIST and C3K (low resolution) for the 4.0 grids.

Some scripts name their output differently from the published file. Examples
are `bc03_chabrier03-0.1,100` (published as
`bc03-2003-padova00_chabrier03-0.1,100`), FSPS `mist-miles` with masses
`1.0,120.0` (published as `mistmiles` with `1,120`), and Maraston 2024
`Tenc00` (one grid was published as `Tenc_0.00`). Several Cloudy grids were
also renamed after they were made.

The Cloudy scripts still read parameter files from a `params/` directory
relative to where they run. They need to accept a path before these files can
be used directly.
