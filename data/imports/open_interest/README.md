Place open-interest CSV files here, then run `make import-oi`.

Format:

```csv
date,asset,open_interest_usd
2024-01-15,BTC,18420000000
2024-01-16,BTC,18755000000
```

See `docs/data-imports.md` for the full specification.
Blank values are treated as missing data, never as zero.
