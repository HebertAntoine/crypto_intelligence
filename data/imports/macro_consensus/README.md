Place consensus CSV files here, then run `make import-consensus`.

```csv
release_time,metric,event_name,actual,consensus,previous,unit
2026-08-12 12:30,macro.cpi,US CPI YoY,3.2,2.9,3.0,pct
2026-09-05 12:30,macro.nonfarm_payrolls,US Nonfarm Payrolls,142,160,155,thousands
```

Required columns: `release_time`, `metric`, `actual`, `consensus`.
Optional: `event_name`, `observation_period`, `previous`, `unit`.

`release_time` is the **publication** time in UTC, not the observation period.

A blank consensus means the surprise cannot be computed for that release. The
system reports `NO_CONSENSUS` rather than estimating one — a fabricated
consensus would produce fabricated surprises.
