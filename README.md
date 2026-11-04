# syngredients

Parameter files to regenerate every grid in
[Syndex](https://synthesizer-project.org/syndex) with
[syncretize](https://github.com/synthesizer-project/syncretize). They are
generated from Syndex metadata, so don't edit them by hand. Rebuild with:

```
python build_configs.py [--cache <dir>] [--syncretize <dir>]
```

`--cache` keeps the downloaded metadata so reruns skip the API. `--syncretize`
is a syncretize checkout (default `../syncretize`), read for the FSPS
variable-IMF templates.

## Layout

```
manifest.yaml                    every grid: script, config, incident it needs
sps/<model>/<incident grid>/
    incident.yaml                incident grid
    <cloudy suffix>.yaml         one per Cloudy grid made from it
agn/<model>/<incident grid>/     same for AGN
```

Incident directories are named after the grid's Syndex name. Cloudy files are
named after the part of the Syndex filename following `_cloudy-`, because the
Cloudy scripts name their output `<incident>_cloudy-<parameter file name>`.
Each holds the full parameter set, so no `--cloudy-paramfile-extra` is needed.

## Running

Run the manifest's `incident_grids` first, then its `cloudy_grids`; each
Cloudy entry names the incident config it needs. Each incident YAML header
gives its run command, with script paths relative to syncretize. For example:

```
python src/syncretize/incident/sps/bc03/generate_incident_grid.py \
    <syngredients>/sps/bc03/bc03-2003-padova2000-chabrier03-0p1-100/incident.yaml \
    --grid-dir <grid-dir> --input-dir <input-dir>
```

Pass a Cloudy YAML to the Cloudy scripts as `--cloudy-paramfile <path>`.

Five incident grids were only ever used as Cloudy inputs and are not in
Syndex. Their parameters come from the incident axes of the Cloudy grids made
from them.

## Known differences from the published grids

These are also `NOTE` lines in the YAML headers and `notes` in the manifest.

- The 10 BC03 2016 Cloudy grids were made from an earlier version of their
  incident grids, whose first age was 1e5 yr, not the current 1 yr.
- `qsosed-cloudy-agn-test` was published with the same filename as
  `qsosed-test-agn-cloudy-c23p01`, but its incident grid has two inclinations,
  not three. Its incident model is renamed to `qsosed-cloudy-agn-test` so the
  outputs don't collide.
- Three grids were published with ionising luminosities only (no spectra or
  lines).

Syndex doesn't record these, so the files assume them:

- Isotropic QSOSED grids use `cosine_inclinations: 0.5`, as in syncretize's
  isotropic parameter files.
- Fixed-efficiency RELAGN grids use `radiative_efficiencies: [0.1]`, as in
  their names.
- FSPS uses the libraries it was compiled with: MIST and MILES for the 3.2
  grids, MIST and C3K (low resolution) for the 4.0 grids.

Some scripts name their output differently from the published file:
`bc03_chabrier03-0.1,100` (published as
`bc03-2003-padova00_chabrier03-0.1,100`), FSPS `mist-miles` with masses
`1.0,120.0` (published as `mistmiles` with `1,120`), and Maraston 2024
`Tenc00` (one grid published as `Tenc_0.00`). Several Cloudy grids were also
renamed after they were made.
