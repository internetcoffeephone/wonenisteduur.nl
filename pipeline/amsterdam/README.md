# Amsterdam: grondwaarde, parkeren en een OZB-verschuiving

Pipeline behind `/amsterdam/` on wonenisteduur.nl. Work in progress; full
documentation follows with the report pages.

```bash
export AMS_CACHE=/path/to/cache   # optional, default ./cache (gitignored)
uv run 01_fetch.py                # downloads (BAG bulk is ~7.8 GB)
uv run 02_prepare.py              # parse and clip to Amsterdam
uv run 03_land.py                 # A: land price per buurt
```
