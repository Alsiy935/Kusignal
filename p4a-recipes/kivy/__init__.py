from os.path import join
from pathlib import Path
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

    # Apply the upstream Kivy Android source adjustments directly in
    # prebuild_arch instead of relying on fragile line-numbered patch files.
    # This avoids patch rejects when the Kivy archive changes formatting.
    patches = []

    def _fix_kivy_sources(self, arch):
        """Normalize Kivy 2.3.1 sources immediately before wheel build.

        The 2.3.1 source already contains the SDL2 deadlock fix. Some
        p4a/Kivy build combinations can nevertheless leave the declaration
        as ``nogil nogil``. Cython rejects that exact form. Normalize it
        after all recipe preparation/patching and immediately before the
        PyProjectRecipe wheel build.
        """
        build_dir = Path(self.get_build_dir(arch.arch))

        # Python 3.14 compatibility change used by p4a's no-ast-str patch.
        parser_py = build_dir / "kivy" / "lang" / "parser.py"
        if parser_py.exists():
            text = parser_py.read_text(encoding="utf-8")
            old_block = """                if isinstance(n, ast.Str):
                    # NOTE: required for python3.6
                    yield from cls.get_names_from_expression(n.s)
                else:
                    yield from cls.get_names_from_expression(n.value)"""
            new_block = "                yield from cls.get_names_from_expression(n.value)"
            if old_block in text:
                text = text.replace(old_block, new_block, 1)
                parser_py.write_text(text, encoding="utf-8")

        # Never allow the invalid duplicate Cython modifier to reach the
        # wheel build. Keep exactly one ``nogil`` on the SDL declaration.
        source_root = build_dir / "kivy"
        for path in source_root.rglob("*"):
            if path.suffix not in {".pyx", ".pxd", ".pxi"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            fixed = text.replace("nogil nogil", "nogil")
            if fixed != text:
                path.write_text(fixed, encoding="utf-8")

        sdl_pxi = source_root / "lib" / "sdl2.pxi"
        if sdl_pxi.exists():
            text = sdl_pxi.read_text(encoding="utf-8")
            text = text.replace(
                "SDL_GL_SwapWindow(SDL_Window * window) nogil nogil",
                "SDL_GL_SwapWindow(SDL_Window * window) nogil",
            )
            sdl_pxi.write_text(text, encoding="utf-8")

        # Fail early with a precise message instead of a long Cython build
        # if another preparation step reintroduces the duplicate modifier.
        leftovers = []
        for path in source_root.rglob("*"):
            if path.suffix in {".pyx", ".pxd", ".pxi"} and path.is_file():
                text = path.read_text(encoding="utf-8")
                if "nogil nogil" in text:
                    leftovers.append(str(path))
        if leftovers:
            raise RuntimeError("Duplicate Cython 'nogil nogil' remains in: " + ", ".join(leftovers))

    def prebuild_arch(self, arch):
        # Recipe.py dispatches this to prebuild_<arch>; keep the superclass
        # call so the normal p4a preparation remains intact.
        super().prebuild_arch(arch)

    def build_arch(self, arch):
        # This runs after p4a recipe patching and immediately before
        # PyProjectRecipe invokes `python -m build --wheel`.
        self._fix_kivy_sources(arch)
        super().build_arch(arch)


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
