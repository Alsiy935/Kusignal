from os.path import join
import sys
import packaging.version

from pythonforandroid.recipe import PyProjectRecipe, Recipe
from pythonforandroid.toolchain import current_directory, shprint


def get_kivy_version(recipe, arch):
    with current_directory(join(recipe.get_build_dir(arch.arch), "kivy")):
        return shprint(
            __import__("sh").Command(sys.executable),
            "-c",
            "import _version; print(_version.__version__)",
        )


def is_kivy_affected_by_deadlock_issue(recipe=None, arch=None):
    return packaging.version.parse(str(get_kivy_version(recipe, arch))) < packaging.version.Version("2.2.0.dev0")


def is_kivy_less_than_3(recipe=None, arch=None):
    return packaging.version.parse(str(get_kivy_version(recipe, arch))) < packaging.version.Version("3.0.0.dev0")


class KivyRecipe(PyProjectRecipe):
    version = "2.3.1"
    url = "https://github.com/kivy/kivy/archive/{version}.zip"
    name = "kivy"

    depends = [("sdl2", "sdl3"), "pyjnius", "setuptools", "android", "libthorvg"]

    # Kivy needs these runtime packages. Pin charset-normalizer to the pure
    # Python release so p4a does not try to install the incompatible cp314
    # Android wheel from 3.5.x.
    python_depends = [
        "certifi",
        "chardet",
        "charset-normalizer==3.4.9",
        "idna",
        "requests",
        "urllib3",
        "filetype",
    ]

    hostpython_prerequisites = ["cython>=0.29.1,<=3.0.12"]

    patches = [
        ("sdl-gl-swapwindow-nogil.patch", is_kivy_affected_by_deadlock_issue),
        ("use_cython.patch", is_kivy_less_than_3),
        ("no-ast-str.patch", is_kivy_less_than_3),
    ]

    @property
    def need_stl_shared(self):
        return "sdl3" in self.ctx.recipe_build_order

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["LDFLAGS"] = env["LDFLAGS"] + " -L{} ".format(
            self.ctx.get_libs_dir(arch.arch) +
            " -L{} ".format(self.ctx.libs_dir) +
            " -L{}".format(join(self.ctx.bootstrap.build_dir, "obj", "local", arch.arch))
        )
        env["LDSHARED"] = env["CC"] + " -shared"
        env["LIBLINK"] = "NOTNONE"
        env["NDKPLATFORM"] = "NOTNONE"
        if not is_kivy_less_than_3(self, arch):
            env["KIVY_CROSS_PLATFORM"] = "android"
        env["KIVY_THORVG_LIB_DIR"] = self.ctx.get_libs_dir(arch.arch)
        env["KIVY_THORVG_INCLUDE_DIR"] = join(
            Recipe.get_recipe("libthorvg", self.ctx).get_include_dir(arch), "thorvg-1"
        )
        if "sdl2" in self.ctx.recipe_build_order:
            env["USE_SDL2"] = "1"
            env["KIVY_SPLIT_EXAMPLES"] = "1"
            sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
            sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
            env["KIVY_SDL2_PATH"] = ":".join([
                join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include"),
                *sdl2_image_recipe.get_include_dirs(arch),
                *sdl2_mixer_recipe.get_include_dirs(arch),
                join(self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
            ])
        if "sdl3" in self.ctx.recipe_build_order:
            sdl3_mixer_recipe = self.get_recipe("sdl3_mixer", self.ctx)
            sdl3_image_recipe = self.get_recipe("sdl3_image", self.ctx)
            sdl3_ttf_recipe = self.get_recipe("sdl3_ttf", self.ctx)
            sdl3_recipe = self.get_recipe("sdl3", self.ctx)
            env["USE_SDL3"] = "1"
            env["KIVY_SPLIT_EXAMPLES"] = "1"
            env["KIVY_SDL3_PATH"] = ":".join([
                *sdl3_mixer_recipe.get_include_dirs(arch),
                *sdl3_image_recipe.get_include_dirs(arch),
                *sdl3_ttf_recipe.get_include_dirs(arch),
                *sdl3_recipe.get_include_dirs(arch),
            ])
        return env


recipe = KivyRecipe()
