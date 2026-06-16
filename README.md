# Introduction-to-Programming-with-Python---LSN-0104---FINAL-PROJECT

# FIFA World Cup 2026 Tournament Simulator

#### Video Demo: (https://youtu.be/_WyXKzuBnBA)

#### Description:

The FIFA World Cup 2026 Tournament Simulator is a Flask-based web application that lets you simulate the entire 2026 FIFA World Cup — all 104 matches — using real team data, official group draw rules, and Elo-based match probabilities derived from actual FIFA rankings.

At the start, you choose between two modes: use the official groups drawn in December 2025, or generate a completely randomized draw that respects real FIFA seeding rules (4 pots of 12 teams, confederation limits per group, and host country placement). Either way, you get all 48 qualified teams with their real FIFA points used as match ratings.

**Group Stage**

The group stage covers 12 groups of 4 teams (A through L), each playing a full round-robin over 3 matchdays — 72 matches total. You can simulate one match at a time or simulate an entire matchday across all groups at once. Standings update live after every result, including a ranking of all 12 third-place teams to determine which 8 advance. A projected Round-of-32 bracket at the bottom of the page updates as results come in, giving you a live preview of the likely knockout matchups.

**Knockout Stage**

Once the group stage is complete, the bracket is built automatically using the official 2026 seeding structure: group winners from groups A, B, C, D, G, H, I, and J are each randomly assigned one of the 8 qualifying third-place teams; their runners-up cross-pair with each other (2A vs 2B, 2C vs 2D, 2G vs 2H, 2I vs 2J); and groups E, F, K, and L follow a special cross-pairing (1E vs 2F, 1F vs 2E, 1K vs 2L, 1L vs 2K).

The bracket is displayed as a two-sided wall chart, converging from both halves toward the center where the Final and 3rd-place match are shown. Every round — Round of 32 through the Final — is visible from the start with TBD placeholders that fill in as matches are simulated. Penalty shootouts are resolved automatically for knockout draws and displayed in `(H)h-a(A)` format. The 3rd-place match must be simulated before the Final.

**Results**

When the tournament ends, a results page displays the champion, runner-up, third and fourth place finishers, and a breakdown of every team sorted by the round they were eliminated. A single button resets everything for a new tournament.

**Match Simulation**

Matches are simulated using an Elo-style win probability formula (`p = 1 / (1 + 10^(Δrating / 350))`), adjusted for draws and knockout pressure. Scorelines are generated consistent with the decided outcome, with goal margins that scale to the rating gap — a 600-point mismatch can produce scorelines like 5-1 or 6-0, while an upset produces a tight margin.

**Project Structure**

- `project.py` — Flask app, all core logic functions, and routes
- `teams.py` — Hardcoded data for all 48 qualified teams (FIFA rank, rating, pot, confederation, flag)
- `test_project.py` — 15 pytest tests covering simulation math, standings, draw rules, and bracket seeding
- `requirements.txt` — `flask`, `pytest`
- `templates/` — Jinja2 HTML templates (`layout.html`, `setup.html`, `group_preview.html`, `groups.html`, `bracket.html`, `results.html`)
- `static/` — `style.css`, `script.js`, `LOGO.png`

---

#### AI Disclaimer

Claude AI (by Anthropic) was used throughout this project as a development aid. During the design and planning phase, I used Claude in conversation to brainstorm the project concept, think through the tournament structure and simulation logic, and work through questions I had about Python, Flask, and overall architecture. It helped me reason through problems and explore ideas — similar to how one might use a knowledgeable study partner.

During implementation, I used Claude's agent mode inside VS Code to assist with specific parts of the codebase where I needed more hands-on help — particularly the CSS styling and layout (including the wall-chart bracket design and color palette), the HTML templates, and the small amount of JavaScript used for scroll animations and the IntersectionObserver. All core Python logic, project structure decisions, and final design choices were my own.
