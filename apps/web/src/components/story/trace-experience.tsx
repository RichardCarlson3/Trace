"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import {
  AnimatePresence,
  MotionConfig,
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";
import { ResearchWorkspace } from "@/components/layout/research-workspace";

const chapters = [
  {
    number: "01 / THE QUESTION",
    title: "Too many papers.",
    body: "One late night. One question. Endless tabs.",
    refrain: "the bigger picture",
  },
  {
    number: "02 / THE IDEA",
    title: "A spark of an idea.",
    body: "What if every citation became a visible path?",
    refrain: "the connections",
  },
  {
    number: "03 / THE MAP",
    title: "Ideas connect.",
    body: "See what came before and what comes next.",
    refrain: "every direction",
  },
  {
    number: "04 / THE TOOL",
    title: "Meet TRACE.",
    body: "Turn a paper into a map.",
    refrain: "a new way in",
  },
  {
    number: "05 / YOUR TURN",
    title: "Past. Present. Future. One map.",
    body: "Start with a paper. Follow the ideas.",
    refrain: "your own path",
  },
];

function StudentScene({
  reduced,
  bulbGlow,
}: {
  reduced: boolean;
  bulbGlow: MotionValue<number>;
}) {
  return (
    <svg
      className="story-art"
      viewBox="0 0 700 520"
      role="img"
      aria-label="Illustration of a student researching at a computer late at night"
    >
      <defs>
        <clipPath id="story-bulb-shape">
          <path d="M594 38c-24 0-39 18-39 38 0 17 10 25 18 34 4 4 7 11 7 17h28c0-6 3-13 7-17 8-9 18-17 18-34 0-20-15-38-39-38z" />
        </clipPath>
        <radialGradient id="screen-glow">
          <stop stopColor="#a18d90" stopOpacity=".56" />
          <stop offset="1" stopColor="#a18d90" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="screen-face" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#282a30" />
          <stop offset="1" stopColor="#17191d" />
        </linearGradient>
        <linearGradient id="window-night" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#17191d" />
          <stop offset="1" stopColor="#1f2126" />
        </linearGradient>
      </defs>
      <rect
        x="43"
        y="47"
        width="208"
        height="215"
        rx="15"
        fill="url(#window-night)"
        stroke="#53565e"
        strokeWidth="3"
      />
      <path d="M147 47v215M43 154h208" stroke="#53565e" strokeWidth="5" />
      <circle cx="198" cy="103" r="17" fill="#e4d6a8" opacity=".78" />
      <circle cx="83" cy="86" r="2" fill="#f5f4f2" />
      <circle cx="113" cy="128" r="1.5" fill="#f5f4f2" />
      <circle cx="219" cy="201" r="2" fill="#f5f4f2" />
      <path d="M0 431h700" stroke="#adaeb0" strokeWidth="5" />
      <ellipse cx="349" cy="448" rx="300" ry="19" fill="#0c0d10" opacity=".5" />
      <motion.circle
        cx="346"
        cy="266"
        r="195"
        fill="url(#screen-glow)"
        animate={reduced ? undefined : { opacity: [0.46, 0.9, 0.46] }}
        transition={{ duration: 3.4, repeat: Infinity }}
      />
      <path
        d="M242 365h235l-19 64H260z"
        fill="#282a30"
        stroke="#999a9e"
        strokeWidth="3"
      />
      <rect
        x="220"
        y="156"
        width="277"
        height="208"
        rx="19"
        fill="#17191d"
        stroke="#adaeb0"
        strokeWidth="5"
      />
      <rect
        x="239"
        y="176"
        width="239"
        height="167"
        rx="8"
        fill="url(#screen-face)"
      />
      <rect
        x="261"
        y="202"
        width="112"
        height="9"
        rx="4.5"
        fill="#bc5361"
        opacity=".8"
      />
      <rect x="261" y="224" width="177" height="6" rx="3" fill="#adaeb0" />
      <rect x="261" y="241" width="149" height="6" rx="3" fill="#adaeb0" />
      <rect x="261" y="258" width="160" height="6" rx="3" fill="#adaeb0" />
      <circle cx="287" cy="303" r="7" fill="#b8b7b6" />
      <circle cx="355" cy="291" r="7" fill="#c45b69" />
      <circle cx="422" cy="312" r="7" fill="#b8b7b6" />
      <path d="M293 303l55-12" stroke="#bc5361" strokeWidth="3" opacity=".8" />
      <path d="M362 292l53 18" stroke="#a18d90" strokeWidth="3" />
      <path
        d="M347 365v63m-54 0h111"
        stroke="#999a9e"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path
        d="M526 433v-94c0-69 22-112 73-112s64 44 64 112v94"
        fill="#282a30"
        stroke="#adaeb0"
        strokeWidth="3"
      />
      <motion.g
        animate={reduced ? undefined : { rotate: [-2, 2, -2] }}
        transition={{ duration: 4.2, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "594px 258px" }}
      >
        <circle cx="594" cy="215" r="43" fill="#c69c8d" />
        <path
          d="M552 203c0-35 17-54 42-54 28 0 46 19 45 54-12-8-21-20-26-33-13 18-32 28-61 33z"
          fill="#1f2126"
        />
      </motion.g>
      <path d="M491 431c-12-25-17-50-15-72l82-39 83 22 16 89" fill="#282a30" />
      <path
        d="M551 321c-22 4-36 22-49 50l27 16c15-21 30-35 47-42z"
        fill="#282a30"
        stroke="#adaeb0"
        strokeWidth="3"
      />
      <motion.g
        animate={reduced ? undefined : { rotate: [0, -1.5, 0] }}
        transition={{ duration: 5.5, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "510px 377px" }}
      >
        <path
          d="M516 379c-18 5-35 17-51 22l-33-10"
          fill="none"
          stroke="#c69c8d"
          strokeWidth="18"
          strokeLinecap="round"
        />
      </motion.g>
      <path d="M67 395h118l-7 34H76z" fill="#adaeb0" />
      <path d="M80 381h100l-4 17H76z" fill="#53565e" />
      <rect
        x="94"
        y="347"
        width="77"
        height="73"
        rx="3"
        transform="rotate(-7 94 347)"
        fill="#e2d8d2"
      />
      <path
        d="M106 361l49-6m-46 18 44-6m-42 18 47-6"
        stroke="#adaeb0"
        strokeWidth="3"
      />
      <path
        d="M69 411h115l-10 20H78z"
        fill="#53565e"
        stroke="#adaeb0"
        strokeWidth="2"
      />
      <path d="M85 458h104m-52-25v25" stroke="#999a9e" strokeWidth="4" />
      <motion.g
        className="story-bulb"
        animate={reduced ? undefined : { y: [0, -7, 0], rotate: [-3, 3, -3] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "594px 80px" }}
      >
        <path
          d="M594 38c-24 0-39 18-39 38 0 17 10 25 18 34 4 4 7 11 7 17h28c0-6 3-13 7-17 8-9 18-17 18-34 0-20-15-38-39-38z"
          fill="#282a30"
          stroke="#f3ddb8"
          strokeWidth="3"
        />
        <motion.circle
          cx="594"
          cy="79"
          r="44"
          fill="#fff0a5"
          clipPath="url(#story-bulb-shape)"
          style={{ opacity: bulbGlow }}
        />
        <path
          d="M580 127h28m-25 9h22m-19 8h16"
          stroke="#f3ddb8"
          strokeWidth="5"
          strokeLinecap="round"
        />
      </motion.g>
      <text x="84" y="488" fill="#e0dedb" fontSize="15" letterSpacing="3">
        1:47 AM
      </text>
    </svg>
  );
}

function MapNode({
  x,
  y,
  title,
  small = false,
  active = true,
  compactLabel = false,
}: {
  x: number;
  y: number;
  title: string;
  small?: boolean;
  active?: boolean;
  compactLabel?: boolean;
}) {
  return (
    <motion.g
      animate={{ opacity: active ? 1 : 0, scale: active ? 1 : 0.75 }}
      transition={{ duration: 0.65, ease: "easeOut" }}
      style={{ transformOrigin: `${x}px ${y}px` }}
    >
      <circle
        cx={x}
        cy={y}
        r={small ? 48 : 69}
        fill={small ? "#1f2126" : "#282a30"}
        stroke={small ? "#b8b7b6" : "#f5f4f2"}
        strokeWidth="2.5"
      />
      <circle
        cx={x}
        cy={y}
        r={small ? 57 : 82}
        fill="none"
        stroke="#bc5361"
        opacity=".3"
        strokeWidth="2"
      />
      <text
        x={x}
        y={y + 5}
        textAnchor="middle"
        fill="#f5f4f2"
        fontSize={compactLabel ? "11" : small ? "14" : "16"}
        fontWeight="700"
      >
        {title}
      </text>
    </motion.g>
  );
}

function NetworkScene({ phase, reduced }: { phase: number; reduced: boolean }) {
  const showPast = phase >= 1;
  const showFuture = phase >= 3;
  const duration = reduced ? 0 : 1.25;
  return (
    <svg
      className="story-art"
      viewBox="0 0 700 520"
      role="img"
      aria-label="Illustrative citation map connecting earlier work, a current paper, and later studies"
    >
      <defs>
        <marker
          id="story-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M0 0L10 5L0 10z" fill="#b8b7b6" />
        </marker>
      </defs>
      <circle cx="350" cy="260" r="214" fill="#ac4050" opacity=".1" />
      <motion.path
        d="M292 219 C238 150 207 145 177 144"
        fill="none"
        stroke="#b8b7b6"
        strokeWidth="3"
        markerEnd="url(#story-arrow)"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: showPast ? 1 : 0, opacity: showPast ? 1 : 0 }}
        transition={{ duration }}
      />
      <motion.path
        d="M291 302 C230 360 211 371 178 373"
        fill="none"
        stroke="#b8b7b6"
        strokeWidth="3"
        markerEnd="url(#story-arrow)"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: showPast ? 1 : 0, opacity: showPast ? 1 : 0 }}
        transition={{ duration, delay: reduced ? 0 : 0.16 }}
      />
      <motion.path
        d="M525 143 C470 147 442 183 410 221"
        fill="none"
        stroke="#bc5361"
        strokeWidth="3"
        markerEnd="url(#story-arrow)"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{
          pathLength: showFuture ? 1 : 0,
          opacity: showFuture ? 1 : 0,
        }}
        transition={{ duration }}
      />
      <motion.path
        d="M527 376 C477 369 443 330 412 301"
        fill="none"
        stroke="#a18d90"
        strokeWidth="3"
        markerEnd="url(#story-arrow)"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{
          pathLength: showFuture ? 1 : 0,
          opacity: showFuture ? 1 : 0,
        }}
        transition={{ duration, delay: reduced ? 0 : 0.16 }}
      />
      <MapNode x={350} y={260} title="This paper" />
      <MapNode x={128} y={138} title="Earlier work" small active={showPast} />
      <MapNode x={129} y={379} title="Foundations" small active={showPast} />
      <MapNode x={572} y={137} title="Later study" small active={showFuture} />
      <MapNode
        x={574}
        y={380}
        title="New questions"
        small
        active={showFuture}
        compactLabel
      />
      <motion.g
        animate={{ opacity: phase === 2 ? 1 : 0, y: phase === 2 ? 0 : 12 }}
        transition={{ duration: 0.4 }}
      >
        <rect
          x="215"
          y="383"
          width="270"
          height="68"
          rx="13"
          fill="#17191d"
          stroke="#8a6b70"
        />
        <text
          x="350"
          y="408"
          textAnchor="middle"
          fill="#b8b7b6"
          fontSize="12"
          letterSpacing="2"
        >
          CITATION EVIDENCE
        </text>
        <text x="350" y="433" textAnchor="middle" fill="#f5f4f2" fontSize="15">
          What does this connection mean?
        </text>
      </motion.g>
      <text
        x="350"
        y="32"
        textAnchor="middle"
        fill="#adaeb0"
        fontSize="12"
        letterSpacing="3"
      >
        ILLUSTRATIVE RESEARCH NETWORK
      </text>
    </svg>
  );
}

function StoryIntro({ onExplore }: { onExplore: () => void }) {
  const storyRef = useRef<HTMLDivElement>(null);
  const [scene, setScene] = useState(0);
  const reduced = useReducedMotion() ?? false;
  const { scrollYProgress } = useScroll({
    target: storyRef,
    offset: ["start start", "end end"],
  });
  const progress = useSpring(scrollYProgress, {
    stiffness: 90,
    damping: 31,
    restDelta: 0.001,
  });
  useMotionValueEvent(scrollYProgress, "change", (value) => {
    const next =
      value < 0.17
        ? 0
        : value < 0.35
          ? 1
          : value < 0.57
            ? 2
            : value < 0.79
              ? 3
              : 4;
    setScene((current) => (current === next ? current : next));
  });
  const active = reduced ? 4 : scene;
  const chapter = chapters[active];
  const roomScale = useTransform(
    progress,
    [0, 0.17, 0.34, 0.54, 0.65, 0.79],
    [1, 1.05, 1.16, 1.16, 1.2, 2.25],
  );
  const roomOpacity = useTransform(
    progress,
    [0, 0.26, 0.35, 0.48, 0.58, 0.67, 0.74],
    [1, 1, 0, 0, 1, 1, 0],
  );
  const roomX = useTransform(progress, [0, 0.58, 0.79], [0, 0, "-30%"]);
  const bulbGlow = useTransform(
    progress,
    [0, 0.12, 0.22, 0.31],
    [0, 0.15, 1, 1],
  );
  const thoughtScale = useTransform(
    progress,
    [0, 0.16, 0.31, 0.48, 0.59],
    [0.15, 0.4, 1.15, 1.42, 2.1],
  );
  const thoughtOpacity = useTransform(
    progress,
    [0, 0.16, 0.25, 0.49, 0.58],
    [0, 0, 1, 1, 0],
  );
  const screenScale = useTransform(
    progress,
    [0, 0.57, 0.67, 0.79, 0.89],
    [0.45, 0.45, 0.85, 1.65, 2.4],
  );
  const screenOpacity = useTransform(
    progress,
    [0, 0.59, 0.68, 0.78, 0.86],
    [0, 0, 1, 1, 0],
  );
  const finaleOpacity = useTransform(progress, [0, 0.8, 0.9], [0, 0, 1]);
  const finaleScale = useTransform(progress, [0, 0.8, 1], [0.86, 0.86, 1]);
  const copyOpacity = useTransform(progress, [0, 0.58, 0.66], [1, 1, 0]);

  return (
    <motion.div
      ref={storyRef}
      className={`story-shell${reduced ? " is-reduced" : ""}`}
      exit={{ opacity: 0, scale: reduced ? 1 : 1.75 }}
      transition={{ duration: reduced ? 0.12 : 0.75, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="story-sticky">
        <div className="story-sky" aria-hidden="true" />
        <motion.div
          className="story-room"
          style={
            reduced
              ? { opacity: 0 }
              : { scale: roomScale, opacity: roomOpacity, x: roomX }
          }
        >
          <StudentScene reduced={reduced} bulbGlow={bulbGlow} />
        </motion.div>
        <motion.div
          className="story-thought"
          style={
            reduced
              ? { opacity: 0 }
              : { scale: thoughtScale, opacity: thoughtOpacity }
          }
          aria-hidden="true"
        >
          <div className="story-thought-bubble">
            <NetworkScene phase={active >= 2 ? 3 : 1} reduced={reduced} />
          </div>
        </motion.div>
        <motion.div
          className="story-computer"
          style={
            reduced
              ? { opacity: 0 }
              : { scale: screenScale, opacity: screenOpacity }
          }
          aria-hidden="true"
        >
          <div className="story-computer-chrome">
            <span />
            <span />
            <span />
          </div>
          <div className="story-computer-screen">
            <span className="story-terminal-label">RESEARCH CONNECTED</span>
            <span className={`story-typed${active >= 3 ? " is-typing" : ""}`}>
              TRACE<span className="story-caret">_</span>
            </span>
          </div>
        </motion.div>
        <motion.div
          className={`story-finale${active === 4 ? " is-active" : ""}`}
          aria-hidden={active !== 4}
          style={
            reduced
              ? { opacity: 1, scale: 1 }
              : { opacity: finaleOpacity, scale: finaleScale }
          }
        >
          <svg
            className="story-finale-orbit"
            viewBox="0 0 100 100"
            aria-hidden="true"
          >
            <circle className="story-orbit-track" cx="50" cy="50" r="48" />
            <circle className="story-orbit-dot" cx="50" cy="2" r="1.1" />
            <circle className="story-orbit-dot" cx="95.65" cy="35.17" r="1.1" />
            <circle
              className="story-orbit-dot story-orbit-dot-cyan"
              cx="78.21"
              cy="88.83"
              r="1.1"
            />
            <circle className="story-orbit-dot" cx="21.79" cy="88.83" r="1.1" />
            <circle className="story-orbit-dot" cx="4.35" cy="35.17" r="1.1" />
          </svg>
          <span className="story-finale-eyebrow">PAST · PRESENT · FUTURE</span>
          <h1>Every idea has a path.</h1>
          <p>
            Start with a paper. Find the connections that move research forward.
          </p>
          <button
            className="story-enter"
            onClick={onExplore}
            tabIndex={active === 4 ? 0 : -1}
          >
            Explore now <span aria-hidden="true">↗</span>
          </button>
        </motion.div>
        <header className="story-nav">
          <span className="story-brand">
            <Image
              className="story-brand-mark"
              src="/utrace-logo.png"
              width={1385}
              height={1136}
              alt="TRACE"
            />
          </span>
          <button className="story-skip" onClick={onExplore}>
            Skip to graph <span aria-hidden="true">↗</span>
          </button>
        </header>
        <motion.div
          className="story-narration"
          style={reduced ? { opacity: 0 } : { opacity: copyOpacity }}
          aria-hidden={active === 4}
        >
          <span className="story-chapter-spacer" aria-hidden="true" />
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: reduced ? 0 : 28 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: reduced ? 0 : -18 }}
              transition={{ duration: reduced ? 0.01 : 0.65 }}
            >
              <h2>{chapter.title}</h2>
              <p>{chapter.body}</p>
            </motion.div>
          </AnimatePresence>
          <div className="story-refrain">
            <strong>Explore now</strong>
            <span> {chapter.refrain}.</span>
          </div>
        </motion.div>
        <div
          className="story-progress"
          aria-label={`Story chapter ${active + 1} of 5`}
        >
          {chapters.map((item, index) => (
            <span
              key={item.number}
              className={index <= active ? "is-active" : ""}
            />
          ))}
        </div>
        <div className="story-bottom">
          <span aria-hidden="true">{active === 4 ? "✦" : "↓"}</span>
        </div>
      </div>
    </motion.div>
  );
}

export function TraceExperience() {
  const [entered, setEntered] = useState(false);
  function returnToStory() {
    setEntered(false);
    requestAnimationFrame(() =>
      window.scrollTo({ top: 0, behavior: "instant" }),
    );
  }
  return (
    <MotionConfig reducedMotion="user">
      <div className={`trace-experience${entered ? " is-exploring" : ""}`}>
        <div className="experience-graph">
          {entered && <ResearchWorkspace onHome={returnToStory} />}
        </div>
        <AnimatePresence>
          {!entered && (
            <StoryIntro key="story" onExplore={() => setEntered(true)} />
          )}
        </AnimatePresence>
      </div>
    </MotionConfig>
  );
}
