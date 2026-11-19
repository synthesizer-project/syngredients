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
    --config-file <syngredients>/sps/bc03/bc03-2003-padova2000-chabrier03-0p1-100/incident.yaml \
    --grid-dir <grid-dir> --input-dir <input-dir>
```

Incident YAMLs use syncretize's Model/Constants/Axes/Sampling format, with
`Model.grid_name` set to the published filename. Pass a Cloudy YAML to the
Cloudy scripts as `--cloudy-paramfile <path>`.
