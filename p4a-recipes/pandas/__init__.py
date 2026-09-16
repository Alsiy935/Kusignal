from os.path import join
from pythonforandroid.recipe import MesonRecipe


class PandasRecipe(MesonRecipe):
    version = 'v2.3.3'
    url = 'git+https://github.com/pandas-dev/pandas'
    depends = ['numpy', 'libbz2', 'liblzma']
    hostpython_prerequisites = [
        "versioneer[toml]",
        "numpy>=2.0",
        "Cython<4.0.0a0"
    ]
    patches = ['fix_numpy_includes.patch']
    python_depends = ['python-dateutil', 'pytz']
    need_stl_shared = True

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)

        env['NUMPY_INCLUDES'] = join(
            self.ctx.get_python_install_dir(arch.arch),
            "numpy/_core/include",
        )
        env["PYTHON_INCLUDE_DIR"] = self.ctx.python_recipe.include_root(arch)
        env['LDFLAGS'] += f' -landroid -l{self.stl_lib_name}'

        return env

    def build_arch(self, arch):
        super().build_arch(arch)
        self.restore_hostpython_prerequisites(["cython"])


recipe = PandasRecipe()
