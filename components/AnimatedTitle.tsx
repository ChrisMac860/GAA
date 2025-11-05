"use client";
import { useEffect, useMemo, useState } from "react";

const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

export default function AnimatedTitle({ text }: { text: string }) {
  const [display, setDisplay] = useState<string>(text);
  const [phase, setPhase] = useState<"scramble" | "final">("scramble");
  const letters = useMemo(() => text.split(""), [text]);

  useEffect(() => {
    let start = performance.now();
    const duration = 700; // ms
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const revealed = Math.floor(t * letters.length);
      const scrambled = letters.map((ch, i) => (i < revealed ? ch : CHARS[Math.floor(Math.random() * CHARS.length)]));
      setDisplay(scrambled.join(""));
      if (t < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        setDisplay(text);
        setPhase("final");
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [letters, text]);

  return (
    <div className="panel px-3 py-2">
      <h1
        className="text-2xl font-extrabold tracking-tight sm:text-3xl text-black"
        aria-label={text}
      >
        <span aria-hidden>{display}</span>
      </h1>
    </div>
  );
}
