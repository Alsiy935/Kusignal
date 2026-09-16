from pythonforandroid.recipe import PyProjectRecipe


class PandasRecipe(PyProjectRecipe):
    version = "2.3.3"
    url = "https://github.com/pandas-dev/pandas/releases/download/v{version}/pandas-{version}.tar.gz"

    depends = [
        "numpy",
        "python-dateutil",
        "pytz",
    ]

    hostpython_prerequisites = [
        "versioneer[toml]",
        "numpy>=2.0",
        "Cython>=3,<4",
        "meson>=1.2.3,<2",
        "meson-python>=0.15,<1",
    ]


recipe = PandasRecipe()
