from pathlib import Path
import re


TOP_LEVEL_LEXICAL = re.compile(r"^(?:const|let)\s+([A-Za-z_$][\w$]*)\b", re.MULTILINE)


def test_dashboard_classic_scripts_do_not_redeclare_top_level_lexicals():
    """Classic browser scripts share one global lexical scope.

    A duplicated top-level `const` across tower.js/motion.js/dashboard.js
    prevents the entire later script from executing, leaving tabs and
    connectivity controls inert.
    """
    root = Path(__file__).resolve().parents[2]
    scripts = [
        root / "web" / "dist" / "tower.js",
        root / "web" / "dist" / "motion.js",
        root / "web" / "dist" / "dashboard.js",
    ]

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        for name in TOP_LEVEL_LEXICAL.findall(text):
            if name in seen:
                duplicates.append(f"{name}: {seen[name]} and {script.name}")
            else:
                seen[name] = script.name

    assert duplicates == []


def test_status_bar_has_iteration_stage_target():
    """The dashboard needs a separate target for long-running iteration stages."""
    root = Path(__file__).resolve().parents[2]
    html = (root / "web" / "dist" / "index.html").read_text(encoding="utf-8")
    js = (root / "web" / "dist" / "dashboard.js").read_text(encoding="utf-8")

    assert 'id="iter-stage"' in html
    assert "function updateIterationDisplay" in js
