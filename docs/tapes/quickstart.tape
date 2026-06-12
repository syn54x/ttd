# Quickstart walkthrough: client -> project -> log -> report -> invoice preview.
# Runs against a fresh throwaway DB; regenerate with `just docs-gifs`.

Output docs/pages/assets/gifs/quickstart.gif

Set FontSize 15
Set Width 1100
Set Height 650
Set Padding 16

Env TTD_DB_PATH "/tmp/ttd-vhs-fresh.db"
Env TTD_CONFIG_DIR "/tmp/ttd-vhs-fresh-config"

Hide
Type "alias ttd='uv run ttd' && rm -rf /tmp/ttd-vhs-fresh.db /tmp/ttd-vhs-fresh-config && clear"
Enter
Sleep 3s
Show

Type "ttd client add 'Acme Corp' --rate 150"
Sleep 500ms
Enter
Sleep 2s

Type "ttd project add 'API Rewrite' --client acme-corp"
Sleep 500ms
Enter
Sleep 2s

Type@40ms "ttd log 'today 9am to noon' -p api-rewrite -n 'auth endpoints'"
Sleep 500ms
Enter
Sleep 2.5s

Type "ttd report day"
Sleep 500ms
Enter
Sleep 3s

Type "ttd invoice create --client acme-corp --month $(date +%Y-%m) --dry-run"
Sleep 500ms
Enter
Sleep 5s
