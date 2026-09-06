import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type GlobalMarket } from "../lib/api";
import {
  ErrorBox, ImportancePill, LegalStatusPill, Loading, Unavailable,
  fmtNumber, fmtSigned, signClass,
} from "../components/common";

export default function GlobalMarketPage() {
  const [data, setData] = useState<GlobalMarket | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.global().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="global market view" />;

  return (
    <>
      <div className="panel section">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <div className="panel-title">Risk regime</div>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{data.risk_regime}</div>
            <div className="small dim">
              Average medium-term conviction{" "}
              <span className={`mono ${signClass(data.average_conviction)}`}>
                {fmtSigned(data.average_conviction, 1)}
              </span>
            </div>
          </div>
          <div className="row" style={{ gap: 24 }}>
            {data.assets.map((a) => (
              <Link key={a.asset} to={`/asset/${a.asset}`} style={{ color: "inherit" }}>
                <div style={{ textAlign: "right" }}>
                  <div className="small dim">{a.asset}</div>
                  <div className="mono">{fmtNumber(a.price, a.asset === "SOL" ? 2 : 0)}</div>
                  <div className={`mono tiny ${signClass(a.change_24h_pct)}`}>
                    {fmtSigned(a.change_24h_pct, 2, "%")}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-title">ETF flows</div>
          <table>
            <tbody>
              {Object.entries(data.etf ?? {}).map(([asset, v]: any) => (
                <tr key={asset}>
                  <td className="mono">{asset}</td>
                  {v.available === false ? (
                    <td colSpan={3} className="unavailable tiny">{v.reason}</td>
                  ) : (
                    <>
                      <td className={`num ${signClass(v.latest_total)}`}>{fmtSigned(v.latest_total, 1, " M$")}</td>
                      <td className={`num tiny ${signClass(v.ma_5d)}`}>5d {fmtSigned(v.ma_5d, 1)}</td>
                      <td className="tiny dim">{v.streak_days} {v.streak_direction ?? ""}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <div className="panel-title">Stablecoin liquidity</div>
          {data.liquidity?.available ? (
            <>
              <div className="kv"><span>Regime</span><span className="pill">{data.liquidity.regime}</span></div>
              <div className="kv"><span>Total supply</span><span>{fmtNumber(data.liquidity.total_supply, 2, " $")}</span></div>
              <div className="kv"><span>Change 7d</span>
                <span className={signClass(data.liquidity.change_7d_pct)}>
                  {fmtSigned(data.liquidity.change_7d_pct, 2, "%")}
                </span>
              </div>
            </>
          ) : <Unavailable reason={data.liquidity?.unavailable_reason} />}
        </div>

        <div className="panel">
          <div className="panel-title">Macro</div>
          {data.macro?.available ? (
            <>
              <div className="kv"><span>Risk appetite</span><span>{data.macro.risk_appetite}</span></div>
              <div className="kv"><span>Dollar</span><span>{data.macro.dollar_trend}</span></div>
              <div className="kv"><span>Rates</span><span>{data.macro.rates_trend}</span></div>
              <table style={{ marginTop: 8 }}>
                <tbody>
                  {Object.entries(data.macro.metrics ?? {}).slice(0, 8).map(([k, v]: any) => (
                    <tr key={k}>
                      <td className="dim tiny">{k.replace("macro.", "")}</td>
                      <td className="num">{fmtNumber(v, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : <Unavailable reason={data.macro?.unavailable_reason} />}
        </div>

        <div className="panel">
          <div className="panel-title">Calendar</div>
          {data.calendar?.length ? (
            <table>
              <tbody>
                {data.calendar.slice(0, 10).map((e) => (
                  <tr key={e.id}>
                    <td className="mono tiny">{new Date(e.scheduled_at).toLocaleDateString()}</td>
                    <td>{e.name}</td>
                    <td className="num tiny dim">{e.hours_until?.toFixed(0)}h</td>
                    <td><ImportancePill importance={e.importance} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="dim small">
              No stored event. The macro calendar lives in config/macro_calendar.yaml.
            </div>
          )}
        </div>
      </div>

      <div className="panel section" style={{ marginTop: 14 }}>
        <div className="panel-title">Regulation</div>
        {data.regulation?.available ? (
          <table>
            <tbody>
              {data.regulation.events?.slice(0, 10).map((e: any, i: number) => (
                <tr key={i}>
                  <td style={{ width: 150 }}><LegalStatusPill status={e.legal_status} /></td>
                  <td className="tiny dim" style={{ width: 90 }}>{e.institution}</td>
                  <td>
                    {e.source_url ? <a href={e.source_url} target="_blank" rel="noreferrer">{e.title}</a> : e.title}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Unavailable reason={data.regulation?.unavailable_reason} />}
      </div>

      {data.geopolitics?.available && (
        <div className="panel section">
          <div className="panel-title">Geopolitical risk</div>
          <div className="row" style={{ gap: 12 }}>
            <span className={`pill ${["HIGH", "EXTREME"].includes(data.geopolitics.level) ? "pill-critical" : "pill-info"}`}>
              {data.geopolitics.level}
            </span>
            <span className="mono small">{data.geopolitics.score?.toFixed(0)}/100</span>
          </div>
          <div className="small" style={{ marginTop: 8 }}>{data.geopolitics.justification}</div>
        </div>
      )}

      {data.rwa && (
        <div className="panel section">
          <div className="panel-title">Tokenisation / RWA</div>
          <table>
            <tbody>
              {Object.entries(data.rwa).slice(0, 10).map(([k, v]: any) => (
                <tr key={k}>
                  <td className="dim">{k.replace("rwa.", "")}</td>
                  <td className="num">{typeof v.value === "number" ? fmtNumber(v.value, 2) : String(v.value)}</td>
                  <td className="tiny faint">{v.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="panel section">
        <div className="panel-title">Recent alerts</div>
        {data.alerts?.length ? (
          <table>
            <tbody>
              {data.alerts.slice(0, 20).map((a, i) => (
                <tr key={i}>
                  <td style={{ width: 90 }}><ImportancePill importance={a.importance} /></td>
                  <td className="mono tiny" style={{ width: 46 }}>{a.asset ?? "—"}</td>
                  <td>
                    {a.title}
                    {a.detail && <div className="tiny faint">{a.detail}</div>}
                  </td>
                  <td className="tiny faint" style={{ width: 130 }}>
                    {new Date(a.triggered_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="dim small">No alert recorded.</div>}
      </div>
    </>
  );
}
