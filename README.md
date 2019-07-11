# autovar
Analysis script for sources with variability in their brightness

## Installation

It is strongly recommended you use python 3 and a virtual environment

Using the [Anaconda](https://www.anaconda.com/download/) distribution of Python:

```bash
conda create -n autovar python=3
source activate autovar
```

The package can be installed with `pip`. From the root of this repo, run:

```bash
cd autovar
pip install .
```

or directly with the setup script

```bash
cd autovar
python setup.py install
```

## Usage

There are a few input options when running the scripts. You can either run the whole analysis at once or the individual stages.

`--ra` *[required parameter]* Right Ascension of the target (in decimal)

`--dec` *[required parameter]* Declination of the target (in decimal)

`--target-file` *[required parameter]*

`--indir` [parameter] Path of directory containing LCO data files. If none is given, autovar assumes the current directory

`--format` [parameter] input file format. If not `fz`, `fits`, or `fit` assumes the input files are photometry files with correct headers. If image files given, code will extra photometry from FITS extension. Defaults to `fz`.

`--full` [boolean flag] Run the whole code. This will run the following steps in this order `stars` > `comparison` > `calc` > `plot`

`--stars` [boolean flag] Step 1: Identify and match stars from each data file

`--comparison` [boolean flag] Step 2: Identify non-varying stars to use for comparisons

`--calc` [boolean flag] Step 3: Calculate the brightness change of the target

`--plot` [boolean flag] Step 4: Produce lightcurve plots

`--detrend` [boolean flag] *optional* Will detrend exoplanet data

`--eebls` [boolean flag] Additional step: EEBLS - box fitting to search for periodic transits

`--clean` [boolean flag] Remove all files except the original data files


### Example Usage

```bash
autovar --ra 154.9083708 --dec -9.8062778 --indir /path/to/your/data --full
```

All the files generated will be stored in the directory you specify in `--indir`

### Tests

If you are developing this package, you will want to run the tests. You will need `pytest` installed and then, from the `autovar` directory within this repo, run:

```bash
pytest
```

To suppress the warning messages use:

```bash
pytest --disable-pytest-warnings
```

You may also want to install this in developer mode

```bash
python setup.py develop
```

## Authors
Written by Michael Fitzgerald. Adapted by [Edward Gomez](@zemogle)
