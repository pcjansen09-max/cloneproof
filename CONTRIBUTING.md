# Contributing

Bug reports with a public URL are the most useful thing you can send: the issue list in `report.json` shows
whether the weak spot is the mirror or the measurement.

```bash
git clone https://github.com/pcjansen09-max/cloneproof && cd cloneproof
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" && python -m playwright install chromium
python -m pytest -q        # unit tests are instant, fixture tests launch a browser (about 80 s)
```

Ground rules: measurements must be explainable (every issue names the element and the values), a vertical
shift is blamed once, and nothing may special-case a specific site. Add a test with a small local page in
`tests/fixtures` for every scoring change.
