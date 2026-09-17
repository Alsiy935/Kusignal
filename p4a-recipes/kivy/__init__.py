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

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        build_dir = self.get_build_dir(arch.arch)

        # Kivy 2.3.1 disables Cython on Android in setup.py. p4a must
        # generate the C sources before compiling the Android extensions.
        setup_py = join(build_dir, "setup.py")
        text = open(setup_py, encoding="utf-8").read()
        old = "if platform in ('ios', 'android'):"
        new = "if platform in ('ios',):"
        if old in text:
            text = text.replace(old, new, 1)
        elif new not in text:
            raise RuntimeError("Kivy setup.py Cython Android guard not found")
        open(setup_py, "w", encoding="utf-8").write(text)

        # Python 3.14 removed the old ast.Str compatibility behaviour used
        # by this Kivy release. Apply the same source change as p4a's patch.
        parser_py = join(build_dir, "kivy", "lang", "parser.py")
        if Path(parser_py).exists():
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

        # Apply the Android SDL2 deadlock fix from the upstream recipe.
        window_pyx = join(build_dir, "kivy", "core", "window", "_window_sdl2.pyx")
        if Path(window_pyx).exists():
            w = open(window_pyx, encoding="utf-8").read()
            old_swap = "        SDL_GL_SwapWindow(self.win)"
            new_swap = "        with nogil:\n            SDL_GL_SwapWindow(self.win)"
            if old_swap in w:
                w = w.replace(old_swap, new_swap, 1)
                open(window_pyx, "w", encoding="utf-8").write(w)
            elif new_swap not in w:
                raise RuntimeError("Kivy _window_sdl2.pyx SDL_GL_SwapWindow call not found")

        sdl_pxi = join(build_dir, "kivy", "lib", "sdl2.pxi")
        if Path(sdl_pxi).exists():
            p = open(sdl_pxi, encoding="utf-8").read()
            old_decl = "cdef void SDL_GL_SwapWindow(SDL_Window * window)"
            new_decl = "cdef void SDL_GL_SwapWindow(SDL_Window * window) nogil"
            if old_decl in p:
                p = p.replace(old_decl, new_decl, 1)
                open(sdl_pxi, "w", encoding="utf-8").write(p)
            elif new_decl not in p:
                raise RuntimeError("Kivy sdl2.pxi SDL_GL_SwapWindow declaration not found")


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
