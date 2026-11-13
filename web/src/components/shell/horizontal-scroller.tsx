"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface HorizontalScrollerProps {
  children: React.ReactNode;
  className?: string;
}

function edgesFor(element: HTMLElement) {
  const max = element.scrollWidth - element.clientWidth;
  const overflow = max > 4;
  return {
    overflow,
    left: overflow && element.scrollLeft > 4,
    right: overflow && max - element.scrollLeft > 4,
  };
}

export function HorizontalScroller({ children, className = "" }: HorizontalScrollerProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ overflow: false, left: false, right: false });

  const update = useCallback(() => {
    const element = scrollerRef.current;
    if (!element) return;
    setEdges(edgesFor(element));
  }, []);

  useEffect(() => {
    update();
    const element = scrollerRef.current;
    if (!element) return;
    element.addEventListener("scroll", update, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(element);
    if (element.firstElementChild) observer?.observe(element.firstElementChild);
    window.addEventListener("resize", update);
    return () => {
      element.removeEventListener("scroll", update);
      observer?.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [update, children]);

  const scrollByDirection = (direction: -1 | 1) => {
    const element = scrollerRef.current;
    if (!element) return;
    const amount = Math.max(180, Math.round(element.clientWidth * 0.7)) * direction;
    if (typeof element.scrollBy === "function") {
      element.scrollBy({ left: amount, behavior: "smooth" });
    } else {
      element.scrollLeft += amount;
    }
    window.requestAnimationFrame(update);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      scrollByDirection(-1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      scrollByDirection(1);
    }
  };

  return (
    <div className="flex min-w-0 items-center gap-2">
      <button
        type="button"
        aria-label="Défiler vers la gauche"
        disabled={!edges.left}
        onClick={() => scrollByDirection(-1)}
        className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#0076FF]/40 bg-[#0076FF]/10 text-[#0076FF] shadow-xs disabled:cursor-not-allowed disabled:opacity-35 dark:text-[#00D4FF]"
      >
        <ChevronLeft className="h-5 w-5" aria-hidden="true" />
      </button>
      <div
        ref={scrollerRef}
        tabIndex={0}
        onKeyDown={onKeyDown}
        className={`min-w-0 flex-1 overflow-x-auto scroll-smooth scrollbar-none focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0076FF] ${className}`}
      >
        {children}
      </div>
      <button
        type="button"
        aria-label="Défiler vers la droite"
        disabled={!edges.right}
        onClick={() => scrollByDirection(1)}
        className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#0076FF]/40 bg-[#0076FF]/10 text-[#0076FF] shadow-xs disabled:cursor-not-allowed disabled:opacity-35 dark:text-[#00D4FF]"
      >
        <ChevronRight className="h-5 w-5" aria-hidden="true" />
      </button>
    </div>
  );
}
