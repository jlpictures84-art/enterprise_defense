[app]
title = Enterprise Defense
package.name = enterprisedefense
package.domain = art.jlpictures84
source.dir = .
source.include_exts = py
version = 1.0

requirements = python3,cython,pygame==2.6.0

orientation = landscape
fullscreen = 1

android.permissions = VIBRATE
android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.build_tools_version = 34.0.0

# Keep SDL audio — pygame.mixer uses it
android.add_gradle_repositories =

[buildozer]
log_level = 2
warn_on_root = 1
