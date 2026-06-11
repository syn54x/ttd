"""The ttd visual identity: "ledger meets cockpit".

Near-black paper, one saturated amber accent, thin rules instead of boxes.
"""

from textual.theme import Theme

AMBER = "#ffb000"
INK = "#0d0f12"

TTD_DARK = Theme(
    name="ttd-dark",
    primary=AMBER,
    secondary="#7d8590",
    accent=AMBER,
    foreground="#e6e8eb",
    background=INK,
    surface="#14171c",
    panel="#1a1e24",
    boost="#ffb00022",
    warning="#ffcf5c",
    error="#ff5c5c",
    success="#3fcf8e",
    dark=True,
    variables={
        "block-cursor-background": AMBER,
        "block-cursor-foreground": INK,
        "input-selection-background": "#ffb00044",
        "footer-key-foreground": AMBER,
        "datatable--header-cursor": "#ffb00044",
    },
)

TTD_LIGHT = Theme(
    name="ttd-light",
    primary="#b87800",
    secondary="#57606a",
    accent="#b87800",
    foreground="#1c2128",
    background="#fafaf7",
    surface="#f0f0ec",
    panel="#e8e8e2",
    warning="#9a6700",
    error="#cf222e",
    success="#1a7f37",
    dark=False,
    variables={"footer-key-foreground": "#b87800"},
)

# amber intensity ramp for the activity heatmap (empty → hot)
HEAT_RAMP = ["#1a1e24", "#4d3500", "#7d5600", "#b87e00", "#ffb000"]


def heat_level(seconds: int) -> int:
    """Map a day's seconds to a HEAT_RAMP index — shared by every heat visual."""
    if seconds <= 0:
        return 0
    hours = seconds / 3600
    if hours < 2:
        return 1
    if hours < 4:
        return 2
    if hours < 6:
        return 3
    return 4
