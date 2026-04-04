[app]
title = Enterprise Defense
package.name = enterprisedefense
package.domain = art.jlpictures84
source.dir = .
source.include_exts = py
version = 1.0

requirements = python3,pygame

# Pin p4a to 2024.01.21 — uses Python 3.11 which has longintrepr.h (3.13 removed it)
p4a.branch = v2024.01.21

orientation = landscape
fullscreen = 1

android.permissions = VIBRATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.build_tools_version = 33.0.2

# Keep SDL audio — pygame.mixer uses it
android.add_gradle_repositories =

[buildozer]
log_level = 2
warn_on_root = 1
