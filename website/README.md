# Static research dashboard

The site is plain HTML, CSS, and JavaScript. It has no server, database, analytics tracker, or third-party JavaScript dependency.

GitHub Actions runs `tools/build_site_data.py` to create `website/data/index.json` from `global/checkpoint.json` and `records/*.json`, then publishes the `website/` directory with GitHub Pages. For a local preview from the repository root:

```bash
python tools/validate_network.py
python tools/build_site_data.py
python -m http.server 8000 --directory website
```

Open `http://localhost:8000`. Do not open `index.html` directly because browsers restrict local JSON fetches.
