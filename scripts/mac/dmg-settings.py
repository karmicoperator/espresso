# dmgbuild layout for espresso-macOS.dmg: the app on the left, Applications on the right, an arrow
# between them on the background. Paths arrive from package-mac.sh through -D.
import os.path

application = defines["app"]  # noqa: F821  (dmgbuild injects `defines`)
appname = os.path.basename(application)

files = [application]
symlinks = {"Applications": "/Applications"}
icon = defines["volicon"]  # noqa: F821
background = defines["background"]  # noqa: F821

format = "ULFO"          # lzfse; opens on macOS 10.11 and later, the app needs 12
filesystem = "HFS+"

show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
window_rect = ((200, 140), (660, 400))
default_view = "icon-view"
show_icon_preview = False
arrange_by = None
label_pos = "bottom"
text_size = 13
icon_size = 128
icon_locations = {appname: (170, 170), "Applications": (490, 170)}
