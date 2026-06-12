# Natural-language logging: several expression forms + one ambiguous rejection.
# Runs against the seeded demo DB (see `just docs-gifs`).

Output docs/pages/assets/gifs/log-parsing.gif

Set FontSize 15
Set Width 1100
Set Height 600
Set Padding 16

Env TTD_DB_PATH "/tmp/ttd-vhs.db"
Env TTD_CONFIG_DIR "/tmp/ttd-vhs-config"

Hide
Type "alias ttd='uv run ttd' && clear"
Enter
Sleep 2s
Show

Type@40ms "ttd log 'today 3pm to 4:30pm' -p api-rewrite -n 'code review'"
Sleep 500ms
Enter
Sleep 2.5s

Type@40ms "ttd log 'yesterday 2h30m' -p design-system"
Sleep 500ms
Enter
Sleep 2.5s

Type@40ms "ttd log 'monday 6pm for 2h' -p mobile-app -n 'release prep'"
Sleep 500ms
Enter
Sleep 2.5s

Type@40ms "ttd log '6 to 8' -p api-rewrite"
Sleep 500ms
Enter
Sleep 5s
