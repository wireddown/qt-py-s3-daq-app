# Legacy DAQ application

## Structure

```mermaid
graph LR
    Host(🐍 PC Host)
    JeeNode-1([⚙️ JeeNode])
    JeeNode-2([⚙️ JeeNode])

    subgraph Lab Bench
        Host<==>|USB-UART|JeeNode-1
    end

    subgraph Centrifuge
        JeeNode-2
    end

    JeeNode-2<-.->|433 MHz📡|JeeNode-1
```

- A Python program on the **PC Host** interfaces with a **JeeNode** to log and plot data
  - [InfiniteSerialReadP_V4.py](./InfiniteSerialReadP_V4.py)
- A **JeeNode** wirelessly relays commands and data with a **JeeNode** inside the centrifuge
  - [PCBv5Reader_CRB.ino](./PCBv5Reader_CRB.ino)
- A **JeeNode** inside the centrifuge uses battery power and a custom PCB for sensor IO
  - [PCBv5Centrifuge_CRB.ino](PCBv5Centrifuge_CRB.ino)

## Python setup

### Quick start

```pwsh
# Refresh available Python versions
pyenv update

# Install Python 3.6.8
pyenv install 3.6.8

# Create and enter a new folder
mkdir jeereader
cd jeereader

# Make this folder use Python 3.6.8
pyenv local 3.6.8

# Create and activate a Python virtual environment named '.venv'
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Confirm that the path and Python versions match this venv
python -m pip --version

# Update the installer tools for this venv
python -m pip install --upgrade pip setuptools

# Install the dependencies for the Python program
pip install "pyserial==3.4" "ipython==5.3.0" "matplotlib==2.0.2"

# Run the DAQ System control program
python InfiniteSerialReadP_V4.py
```

### Details

The program also launches with _newer_ versions of some dependencies
- pyserial 3.5
- ipython 7.16.3
- matplotlib 3.2.2

Using the command

```
pip install pyserial ipython "matplotlib==3.2.2"
```

> ℹ️ The program only _imports_ from `IPython` and never _uses_ any classes or functions from the module.
It is possible to **remove** that `import` line and only install  `pyserial` and `matplotlib` into the venv.
>
> With these updates and removals, the minimum environment is
> ```diff
> - from IPython import display
> ```
> ```pwsh
> # Install the newest minimal compatible dependencies
> pip install pyserial "matplotlib==3.2.2"
> ```

### System snapshot

According to the package version list below, this program uses the last 4.x release of [Anaconda 4.4.0](https://repo.anaconda.com/archive/), which is an installation based on [Python 3.6.1](https://www.python.org/downloads/release/python-361/) and [conda 4.3.21](https://github.com/conda/conda/releases/tag/4.3.21).

#### System paths

```
C:\Anaconda3>python -c "import sys; print(sys.executable, sys.path)"

C:\Anaconda3\python.exe
[
    '',
    'C:\\Anaconda3\\python36.zip',
    'C:\\Anaconda3\\DLLs',
    'C:\\Anaconda3\\lib',
    'C:\\Anaconda3',
    'C:\\Anaconda3\\lib\\site-packages',
    'C:\\Anaconda3\\lib\\site-packages\\Sphinx-1.5.6-py3.6.egg',
    'C:\\Anaconda3\\lib\\site-packages\\pyserial-3.4-py3.6.egg',
    'C:\\Anaconda3\\lib\\site-packages\\win32',
    'C:\\Anaconda3\\lib\\site-packages\\win32\\lib',
    'C:\\Anaconda3\\lib\\site-packages\\Pythonwin',
    'C:\\Anaconda3\\lib\\site-packages\\setuptools-27.2.0-py3.6.egg'
]
```

#### Package versions

```
C:\Anaconda3>python -m pip --version

pip 9.0.1 from C:\Anaconda3\lib\site-packages (python 3.6)
```

```
C:\Anaconda3>python -m pip list --verbose

alabaster (0.7.10)
anaconda-client (1.6.3)
anaconda-navigator (1.6.2)
anaconda-project (0.6.0)
asn1crypto (0.22.0)
astroid (1.4.9)
astropy (1.3.2)
Babel (2.4.0)
backports.shutil-get-terminal-size (1.0.0)
beautifulsoup4 (4.6.0)
bitarray (0.8.1)
blaze (0.10.1)
bleach (1.5.0)
bokeh (0.12.5)
boto (2.46.1)
Bottleneck (1.2.1)
cffi (1.10.0)
chardet (3.0.3)
click (6.7)
cloudpickle (0.2.2)
clyent (1.2.2)
colorama (0.3.9)
comtypes (1.1.2)
conda (4.3.21)
contextlib2 (0.5.5)
cryptography (1.8.1)
cycler (0.10.0)
Cython (0.25.2)
cytoolz (0.8.2)
dask (0.14.3)
datashape (0.5.4)
decorator (4.0.11)
distributed (1.16.3)
docutils (0.13.1)
entrypoints (0.2.2)
et-xmlfile (1.0.1)
fastcache (1.0.2)
Flask (0.12.2)
Flask-Cors (3.0.2)
gevent (1.2.1)
greenlet (0.4.12)
h5py (2.7.0)
HeapDict (1.0.0)
html5lib (0.999)
idna (2.5)
imagesize (0.7.1)
ipykernel (4.6.1)
ipython (5.3.0)
ipython-genutils (0.2.0)
ipywidgets (6.0.0)
isort (4.2.5)
itsdangerous (0.24)
jdcal (1.3)
jedi (0.10.2)
Jinja2 (2.9.6)
jsonschema (2.6.0)
jupyter (1.0.0)
jupyter-client (5.0.1)
jupyter-console (5.1.0)
jupyter-core (4.3.0)
lazy-object-proxy (1.2.2)
llvmlite (0.18.0)
locket (0.2.0)
lxml (3.7.3)
MarkupSafe (0.23)
matplotlib (2.0.2)
menuinst (1.4.7)
mistune (0.7.4)
mpmath (0.19)
msgpack-python (0.4.8)
multipledispatch (0.4.9)
navigator-updater (0.1.0)
nbconvert (5.1.1)
nbformat (4.3.0)
networkx (1.11)
nltk (3.2.3)
nose (1.3.7)
notebook (5.0.0)
numba (0.33.0)
numexpr (2.6.2)
numpy (1.12.1)
numpydoc (0.6.0)
odo (0.5.0)
olefile (0.44)
openpyxl (2.4.7)
packaging (16.8)
pandas (0.20.1)
pandocfilters (1.4.1)
partd (0.3.8)
path.py (10.3.1)
pathlib2 (2.2.1)
patsy (0.4.1)
pep8 (1.7.0)
pickleshare (0.7.4)
Pillow (4.1.1)
pip (9.0.1)
ply (3.10)
prompt-toolkit (1.0.14)
psutil (5.2.2)
py (1.4.33)
pycosat (0.6.2)
pycparser (2.17)
pycrypto (2.6.1)
pycurl (7.43.0)
pyflakes (1.5.0)
Pygments (2.2.0)
pylint (1.6.4)
pyodbc (4.0.16)
pyOpenSSL (17.0.0)
pyparsing (2.1.4)
pyserial (3.4)
pytest (3.0.7)
python-dateutil (2.6.0)
pytz (2017.2)
PyWavelets (0.5.2)
pywin32 (220)
PyYAML (3.12)
pyzmq (16.0.2)
QtAwesome (0.4.4)
qtconsole (4.3.0)
QtPy (1.2.1)
requests (2.14.2)
rope-py3k (0.9.4.post1)
scikit-image (0.13.0)
scikit-learn (0.18.1)
scipy (0.19.0)
seaborn (0.7.1)
setuptools (27.2.0)
simplegeneric (0.8.1)
singledispatch (3.4.0.3)
six (1.10.0)
snowballstemmer (1.2.1)
sortedcollections (0.5.3)
sortedcontainers (1.5.7)
sphinx (1.5.6)
spyder (3.1.4)
SQLAlchemy (1.1.9)
statsmodels (0.8.0)
sympy (1.0)
tables (3.2.2)
tblib (1.3.2)
testpath (0.3)
toolz (0.8.2)
tornado (4.5.1)
traitlets (4.3.2)
unicodecsv (0.14.1)
wcwidth (0.1.7)
Werkzeug (0.12.2)
wheel (0.29.0)
widgetsnbextension (2.0.0)
win-unicode-console (0.5)
wrapt (1.10.10)
xlrd (1.0.0)
XlsxWriter (0.9.6)
xlwings (0.10.4)
xlwt (1.2.0)
zict (0.1.2)
```

## Resources

- JeeNode
  - https://web.archive.org/web/20200503024000/https://jeelabs.net/projects/hardware/wiki/jeenode
  - https://github.com/bswe/JeeNode/tree/master
