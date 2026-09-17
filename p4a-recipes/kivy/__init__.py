from os.path import join

from pythonforandroid.recipe import PyProjectRecipe, Recipe
from pythonforandroid.toolchain import current_directory, shprint


class KivyRecipe(PyProjectRecipe):
    version = '2.3.1'
    url = 'https://github.com/kivy/kivy/archive/{version}.zip'
    name = 'kivy'

    depends = [('sdl2', 'sdl3'), 'pyjnius', 'setuptools', 'android', 'libthorvg']

    # Kivy itself declares these runtime dependencies. The important fix is
    # pinning charset-normalizer to 3.4.9: 3.5.x currently resolves to a
    # cp314 Android wheel that p4a cannot install on arm64-v8a.
    python_depends = [
        'certifi',
        'chardet',
        'charset-normalizer==3.4.9',
        'idna',
        'requests',
        'urllib3',
        'filetype',
    ]

    hostpython_prerequisites = ["cython>=0.29.1,<=3.0.12"]

    @property
    def need_stl_shared(self):
        if 'sdl3' in self.ctx.recipe_build_order:
            return True
        return False

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env['LDFLAGS'] = env['LDFLAGS'] + ' -L{} '.format(
            self.ctx.get_libs_dir(arch.arch) +
            ' -L{} '.format(self.ctx.libs_dir) +
            ' -L{}'.format(join(self.ctx.bootstrap.build_dir, 'obj', 'local', arch.arch))
        )
        env['LDSHARED'] = env['CC'] + ' -shared'
        env['LIBLINK'] = 'NOTNONE'
        env['NDKPLATFORM'] = 'NOTNONE'

        self.ctx.recipe_build_order
        if 'sdl2' in self.ctx.recipe_build_order:
            env['USE_SDL2'] = '1'
            env['KIVY_SPLIT_EXAMPLES'] = '1'
            sdl2_mixer_recipe = self.get_recipe('sdl2_mixer', self.ctx)
            sdl2_image_recipe = self.get_recipe('sdl2_image', self.ctx)
            env['KIVY_SDL2_PATH'] = ':'.join([
                join(self.ctx.bootstrap.build_dir, 'jni', 'SDL', 'include'),
                *sdl2_image_recipe.get_include_dirs(arch),
                *sdl2_mixer_recipe.get_include_dirs(arch),
                join(self.ctx.bootstrap.build_dir, 'jni', 'SDL2_ttf'),
            ])

        if 'sdl3' in self.ctx.recipe_build_order:
            sdl3_mixer_recipe = self.get_recipe('sdl3_mixer', self.ctx)
            sdl3_image_recipe = self.get_recipe('sdl3_image', self.ctx)
            sdl3_ttf_recipe = self.get_recipe('sdl3_ttf', self.ctx)
            sdl3_recipe = self.get_recipe('sdl3', self.ctx)
            env['USE_SDL3'] = '1'
            env['KIVY_SPLIT_EXAMPLES'] = '1'
            env['KIVY_SDL3_PATH'] = ':'.join([
                *sdl3_mixer_recipe.get_include_dirs(arch),
                *sdl3_image_recipe.get_include_dirs(arch),
                *sdl3_ttf_recipe.get_include_dirs(arch),
                *sdl3_recipe.get_include_dirs(arch),
            ])

        env['KIVY_THORVG_LIB_DIR'] = self.ctx.get_libs_dir(arch.arch)
        env['KIVY_THORVG_INCLUDE_DIR'] = join(
            Recipe.get_recipe('libthorvg', self.ctx).get_include_dir(arch),
            'thorvg-1'
        )
        return env


recipe = KivyRecipe()
