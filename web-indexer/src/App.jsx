import { useEffect, useMemo, useState } from "react";

const PAGE_SIZE = 25;

function formatDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function formatDuration(seconds) {
  if (seconds == null) return "-";
  return `${seconds.toFixed(1)}s`;
}

function App() {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const pageLabel = useMemo(() => {
    if (total === 0) return "No rows yet";
    const start = offset + 1;
    const end = Math.min(offset + PAGE_SIZE, total);
    return `Showing ${start}-${end} of ${total}`;
  }, [offset, total]);

  async function loadData(nextOffset = offset, nextQuery = query) {
    setLoading(true);
    setError("");
    try {
      const url = new URL("/api/transcripts", window.location.origin);
      url.searchParams.set("limit", String(PAGE_SIZE));
      url.searchParams.set("offset", String(nextOffset));
      if (nextQuery.trim()) {
        url.searchParams.set("q", nextQuery.trim());
      }

      const res = await fetch(url.toString());
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setItems(Array.isArray(data.items) ? data.items : []);
      setTotal(Number(data.total || 0));
      setOffset(Number(data.offset || 0));
    } catch (e) {
      setError(`Failed to load transcripts: ${e.message}`);
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData(0, "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSearchSubmit(event) {
    event.preventDefault();
    setQuery(searchInput);
    loadData(0, searchInput);
  }

  function clearSearch() {
    setSearchInput("");
    setQuery("");
    loadData(0, "");
  }

  function nextPage() {
    const nextOffset = offset + PAGE_SIZE;
    if (nextOffset >= total) return;
    loadData(nextOffset, query);
  }

  function prevPage() {
    const nextOffset = Math.max(0, offset - PAGE_SIZE);
    loadData(nextOffset, query);
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">ConvoIndex / Phase 3</p>
        <h1>Ambient Transcript Timeline</h1>
        <p className="subhead">
          Search conversation history, inspect utterance segments, and review capture quality signals from your local-only pipeline.
        </p>
      </header>

      <section className="controls">
        <form onSubmit={onSearchSubmit} className="searchRow">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search transcript text..."
          />
          <button type="submit">Search</button>
          <button type="button" className="ghost" onClick={clearSearch}>Reset</button>
        </form>

        <div className="statusRow">
          <span>{pageLabel}</span>
          <span>{query ? `Filter: "${query}"` : "Filter: none"}</span>
        </div>

        <div className="pagerRow">
          <button type="button" className="ghost" onClick={prevPage} disabled={offset === 0 || loading}>Newer</button>
          <button type="button" className="ghost" onClick={nextPage} disabled={offset + PAGE_SIZE >= total || loading}>Older</button>
        </div>
      </section>

      {loading && <p className="notice">Loading…</p>}
      {error && <p className="notice error">{error}</p>}

      <main className="timeline">
        {items.map((row) => (
          <article key={row.id} className="card">
            <div className="cardMeta">
              <strong>#{row.id}</strong>
              <span>{row.session_id}</span>
              <span>Segment {row.segment_index}</span>
              <span>{formatDuration(row.duration_seconds)}</span>
            </div>

            <p className="transcript">{row.transcript || "(empty)"}</p>

            <div className="metrics">
              <span>Words: {row.word_count}</span>
              <span>Chars: {row.char_count}</span>
              <span>RMS: {Number(row.avg_rms || 0).toFixed(1)}</span>
              <span>Peak: {row.peak_abs}</span>
              <span>Gain: {row.stt_input_gain}x</span>
              <span>Model: {row.stt_model || "-"}</span>
            </div>

            <div className="timestamps">
              <span>Session start: {formatDate(row.started_at)}</span>
              <span>Segment start: {formatDate(row.segment_started_at)}</span>
              <span>Segment end: {formatDate(row.segment_ended_at)}</span>
              <span>Saved: {formatDate(row.created_at)}</span>
            </div>
          </article>
        ))}
      </main>
    </div>
  );
}

export default App;
