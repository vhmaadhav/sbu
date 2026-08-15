"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { Panel, MonoLabel, GlowButton } from "@/components/ui";
import { API, getJSON } from "@/lib/api";

interface Source {
  label: string;
  item_id: number;
  note_id: number | null;
}
interface Card {
  id: number;
  front: string;
  back: string;
  position: number;
}
interface DeckSummary {
  id: number;
  title: string;
  topic: string;
  subject: string | null;
  sources: Source[];
  card_count: number;
  created_at: number;
}
interface Deck extends DeckSummary {
  cards: Card[];
}

// Self-assessment grades. There is no SRS backend, so these simply advance to
// the next card — no fabricated review intervals.
const GRADES: { label: string; color: string }[] = [
  { label: "AGAIN", color: "#f87171" },
  { label: "HARD", color: "#fbbf24" },
  { label: "GOOD", color: "var(--accent)" },
  { label: "EASY", color: "#8ab8f0" },
];

export default function FlashcardsPage() {
  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [cardIndex, setCardIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function openDeck(deckId: number) {
    setLoading(true);
    setError("");
    try {
      const selected = await getJSON<Deck>(`/api/flashcards/${deckId}`);
      setDeck(selected);
      setCardIndex(0);
      setFlipped(false);
    } catch {
      setError("Couldn't load this deck.");
    } finally {
      setLoading(false);
    }
  }

  async function loadDecks() {
    setLoading(true);
    setError("");
    try {
      const saved = await getJSON<DeckSummary[]>("/api/flashcards");
      setDecks(saved);
      if (saved.length) await openDeck(saved[0].id);
      else {
        setDeck(null);
        setLoading(false);
      }
    } catch {
      setError("Couldn't load your flashcards. Is the Study Buddy API running?");
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = await getJSON<DeckSummary[]>("/api/flashcards");
        if (cancelled) return;
        setDecks(saved);
        if (saved.length) {
          const selected = await getJSON<Deck>(`/api/flashcards/${saved[0].id}`);
          if (cancelled) return;
          setDeck(selected);
          setCardIndex(0);
          setFlipped(false);
        }
      } catch {
        if (!cancelled) setError("Couldn't load your flashcards. Is the Study Buddy API running?");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function next() {
    if (!deck?.cards.length) return;
    setCardIndex((i) => (i + 1) % deck.cards.length);
    setFlipped(false);
  }

  async function deleteDeck() {
    if (!deck || !window.confirm(`Delete "${deck.title}"?`)) return;
    await fetch(`${API}/api/flashcards/${deck.id}`, { method: "DELETE" });
    await loadDecks();
  }

  const card = deck?.cards[cardIndex];
  const total = deck?.cards.length ?? 0;
  const pct = total ? Math.round(((cardIndex + 1) / total) * 100) : 0;

  if (!loading && decks.length === 0) {
    return (
      <section className="axscreen" style={{ minHeight: "calc(100vh - 60px)", display: "grid", placeItems: "center", padding: 40 }}>
        <Panel style={{ padding: "48px 40px", maxWidth: 520, textAlign: "center" }}>
          <MonoLabel style={{ display: "block", marginBottom: 14, color: "var(--accent)" }}>NO DECKS YET</MonoLabel>
          <p style={{ margin: "0 0 20px", fontSize: 14, color: "var(--dim)", lineHeight: 1.6 }}>
            Ask Study Buddy to create flashcards and they will appear here automatically.
          </p>
          <Link href="/search?q=Create%2010%20flashcards%20about%20photosynthesis">
            <GlowButton>CREATE FLASHCARDS →</GlowButton>
          </Link>
        </Panel>
      </section>
    );
  }

  return (
    <section
      className="axscreen"
      style={{ display: "grid", gridTemplateColumns: "260px minmax(0, 1fr)", gap: 24, padding: 32, alignItems: "start" }}
    >
      {/* Deck picker */}
      <Panel>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)" }}>
          <MonoLabel>YOUR DECKS</MonoLabel>
        </div>
        <div style={{ maxHeight: "70vh", overflowY: "auto" }}>
          {decks.map((saved) => {
            const on = deck?.id === saved.id;
            return (
              <button
                key={saved.id}
                onClick={() => openDeck(saved.id)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "14px 18px",
                  borderBottom: "1px solid var(--line)",
                  borderLeft: `2px solid ${on ? "var(--accent)" : "transparent"}`,
                  background: on ? "var(--panel2)" : "transparent",
                }}
              >
                <span style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--text)" }}>{saved.title}</span>
                <MonoLabel size={9} spacing="0.14em" dim style={{ marginTop: 5, display: "block" }}>
                  {saved.card_count} CARDS
                </MonoLabel>
              </button>
            );
          })}
        </div>
      </Panel>

      {/* Review */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
        {error && (
          <div style={{ width: "100%", maxWidth: 620, border: "1px solid #f87171", padding: "10px 14px", fontSize: 13, color: "#f87171" }}>
            {error}
          </div>
        )}
        {loading || !deck || !card ? (
          <div style={{ minHeight: 400, display: "grid", placeItems: "center", color: "var(--dim)", fontSize: 14 }}>
            Loading deck…
          </div>
        ) : (
          <>
            <div
              style={{
                width: "100%",
                maxWidth: 620,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <MonoLabel size={11} spacing="0.18em">
                {deck.title.toUpperCase()}
              </MonoLabel>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <MonoLabel size={11} spacing="0.18em">
                  {String(cardIndex + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
                </MonoLabel>
                <button onClick={deleteDeck} style={{ color: "var(--dim)", padding: 4 }} aria-label="Delete deck">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div style={{ width: "100%", maxWidth: 620, height: 2, background: "var(--line)" }}>
              <div style={{ height: 2, background: "var(--accent)", width: `${pct}%`, transition: "width 0.3s" }} />
            </div>

            <button
              onClick={() => setFlipped((f) => !f)}
              style={{
                width: "100%",
                maxWidth: 620,
                minHeight: 300,
                border: `1px solid ${flipped ? "var(--accent)" : "var(--line2)"}`,
                background: "var(--panel)",
                backdropFilter: "var(--blur)",
                WebkitBackdropFilter: "var(--blur)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                textAlign: "center",
                padding: 40,
                gap: 18,
                position: "relative",
                boxShadow: "0 0 40px -22px var(--accent)",
                transition: "border-color 0.3s",
              }}
            >
              <MonoLabel size={10} spacing="0.2em" dim style={{ position: "absolute", top: 14, left: 16 }}>
                {flipped ? "ANSWER" : "QUESTION"}
              </MonoLabel>
              <MonoLabel size={10} spacing="0.2em" dim style={{ position: "absolute", top: 14, right: 16 }}>
                TAP TO FLIP
              </MonoLabel>
              <div style={{ fontSize: 22, fontWeight: 500, lineHeight: 1.5, maxWidth: 480 }}>
                {flipped ? card.back : card.front}
              </div>
            </button>

            <div style={{ display: "flex", gap: 10, width: "100%", maxWidth: 620 }}>
              {GRADES.map((g) => (
                <button
                  key={g.label}
                  onClick={next}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    padding: "12px 0",
                    border: "1px solid var(--line2)",
                    color: g.color,
                    fontFamily: "var(--font-jetbrains-mono), monospace",
                    fontSize: 11,
                    letterSpacing: "0.18em",
                    background: "transparent",
                  }}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
