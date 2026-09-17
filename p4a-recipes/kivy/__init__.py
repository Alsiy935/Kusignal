from os.path import join
import sys
import packaging.version

from pythonforandroid.recipe import CythonRecipe, Recipe
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


class KivyRecipe(CythonRecipe):
    """Kivy 2.3.1 Android recipe.

    Kivy 2.3.1 contains Cython sources (.pyx). The previous wheel-oriented path did not reliably generate the C
    sources on the Android build host, leaving clang with missing .c files.

    CythonRecipe is the p4a build path intended for Cython packages: it
    explicitly runs the Cython components and then builds/installs them.
    """

    version = "2.3.1"
    url = "https://github.com/kivy/kivy/archive/{version}.zip"
    name = "kivy"

    depends = [("sdl2", "sdl3"), "pyjnius", "setuptools", "android", "libthorvg"]

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

    # The upstream p4a Kivy recipe applies Android source adjustments.
    # We perform the two required source edits directly to avoid fragile
    # line-numbered patch hunks against the Kivy 2.3.1 archive.
    patches = []

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)

        build_dir = self.get_build_dir(arch.arch)

        # Kivy 2.3.1 disables Cython on Android. CythonRecipe needs it
        # enabled so it can generate the C sources from Kivy's .pyx files.
        setup_py = join(build_dir, "setup.py")
        text = open(setup_py, encoding="utf-8").read()
        old = "if platform in ('ios', 'android'):"
        new = "if platform in ('ios',):"
        if old in text:
            text = text.replace(old, new, 1)
        elif new not in text:
            raise RuntimeError("Kivy setup.py Cython Android guard not found")
        open(setup_py, "w", encoding="utf-8").write(text)

        # Python 3.14 compatibility: remove the obsolete ast.Str branch.
        parser_py = join(build_dir, "kivy", "lang", "parser.py")
        p = open(parser_py, encoding="utf-8").read()
        old_block = """                if isinstance(n, ast.Str):
                    # NOTE: required for python3.6
                    yield from cls.get_names_from_expression(n.s)
                else:
                    yield from cls.get_names_from_expression(n.value)"""
        new_block = "                yield from cls.get_names_from_expression(n.value)"
        if old_block in p:
            p = p.replace(old_block, new_block, 1)
            open(parser_py, "w", encoding="utf-8").write(p)
        elif "yield from cls.get_names_from_expression(n.value)" not in p:
            raise RuntimeError("Kivy parser.py AST compatibility block not found")

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

        if "android" in self.ctx.recipe_build_order:
            env["KIVY_ANDROID_LIBS"] = join(
                Recipe.get_recipe("android", self.ctx).get_build_dir(arch.arch),
                "android-build",
            )

        return env


recipe = KivyRecipe()
