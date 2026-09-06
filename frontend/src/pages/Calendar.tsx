/** Catalyst calendar, grouped by how soon each event lands. */
import { useEffect, useState } from "react";
import { api, type CalendarData, type CalendarEntry } from "../lib/api";
import { ErrorBox, ImportancePill, LegalStatusPill, Loading } from "../components/common";

const GROUPS: { key: keyof CalendarData; label: string }[] = [
  { key: "within_24h", label: "Within 24 hours" },
  { key: "within_3d", label: "Within 3 days" },
  { key: "within_7d", label: "Within 7 days" },
  { key: "within_30d", label: "Within 30 days" },
];

export default function CalendarPage() {
  const [data, setData] = useState<CalendarData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.calendar(60).then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading what="calendar" />;

  // Each group is cumulative on the backend; show only what is new at each
  // step so an event is not repeated in four sections.
  const seen = new Set<string>();

  return (
    <>
      {GROUPS.map(({ key, label }) => {
        const entries = (data[key] as CalendarEntry[]).filter((e) => {
          const id = `${e.name}:${e.scheduled_at}`;
          if (seen.has(id)) return false;
          seen.add(id);
          return true;
        });
        if (!entries.length) return null;
        return (
          <div key={key} className="panel cal-group">
            <div className="panel-title">{label}</div>
            {entries.map((e, i) => (
              <div key={i} className="cal-row">
                <span className="mono tiny">
                  {new Date(e.scheduled_at).toLocaleString(undefined, {
                    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                  })}
                </span>
                <span className="pill">{e.category}</span>
                <span>
                  {e.source_url ? (
                    <a href={e.source_url} target="_blank" rel="noreferrer">{e.name}</a>
                  ) : (
                    e.name
                  )}
                  <div className="tiny faint">
                    in {e.hours_until.toFixed(0)}h · {e.assets.join(", ")} ·{" "}
                    <span className={e.certainty === "KNOWN" ? "pos" : "dim"}>{e.certainty}</span>
                    {e.source_name ? ` · ${e.source_name}` : ""}
                  </div>
                </span>
                <ImportancePill importance={e.importance} />
              </div>
            ))}
          </div>
        );
      })}

      {data.recent_regulation.length > 0 && (
        <div className="panel cal-group">
          <div className="panel-title">Recently decided (context, not upcoming)</div>
          {data.recent_regulation.map((e, i) => (
            <div key={i} className="cal-row">
              <span className="mono tiny">
                {new Date(e.scheduled_at).toLocaleDateString()}
              </span>
              {e.legal_status ? <LegalStatusPill status={e.legal_status} /> : <span className="pill">{e.category}</span>}
              <span>
                {e.source_url ? (
                  <a href={e.source_url} target="_blank" rel="noreferrer">{e.name}</a>
                ) : e.name}
              </span>
              <ImportancePill importance={e.importance} />
            </div>
          ))}
        </div>
      )}

      <div className="panel">
        <div className="tiny faint">{data.note}</div>
      </div>
    </>
  );
}
