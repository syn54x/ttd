# TUI tour: cycle the six screens, then the quick-log modal.
# Runs against the seeded demo DB (see `just docs-gifs`).

Output docs/pages/assets/gifs/tui-tour.gif

Set FontSize 15
Set Width 1100
Set Height 650
Set Padding 8

Env TTD_DB_PATH "/tmp/ttd-vhs.db"
Env TTD_CONFIG_DIR "/tmp/ttd-vhs-config"

Hide
Type "uv run ttd"
Enter
Sleep 4s
Show

Sleep 2.5s
Type "2"
Sleep 2.5s
Type "3"
Sleep 2.5s
Type "4"
Sleep 2.5s
Type "5"
Sleep 2.5s
Type "6"
Sleep 2.5s
Type "1"
Sleep 1.5s

Type "l"
Sleep 1s
Type@90ms "yesterday 9-11:30"
Sleep 3s
Escape
Sleep 1.5s

Type "q"
Sleep 1s
