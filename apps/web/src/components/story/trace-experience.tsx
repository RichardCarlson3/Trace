"use client";

import { useRef, useState } from "react";
import {
  AnimatePresence,
  MotionConfig,
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "motion/react";
import { ResearchWorkspace } from "@/components/layout/research-workspace";

const chapters = [
  {
    number: "01 / THE QUESTION",
    title: "One question. A thousand papers.",
    body: "Late at night, one student follows a trail of research that keeps branching.",
    refrain: "the bigger picture",
  },
  {
    number: "02 / THE IDEA",
    title: "What if the links were visible?",
    body: "A single thought turns citations into a map of the ideas behind an idea.",
    refrain: "the connections",
  },
  {
    number: "03 / THE MAP",
    title: "Past and future come into focus.",
    body: "Follow references backward. Follow citing papers forward. See how research grows.",
    refrain: "every direction",
  },
  {
    number: "04 / THE TOOL",
    title: "Give the idea a place to live.",
    body: "The student opens TRACE and turns a paper into a living research network.",
    refrain: "a new way in",
  },
  {
    number: "05 / YOUR TURN",
    title: "Past. Present. Future. One map.",
    body: "Start with a real paper. Follow the connections wherever curiosity leads.",
    refrain: "your own path",
  },
];

function StudentScene({ reduced }: { reduced: boolean }) {
  return (
    <svg
      className="story-art"
      viewBox="0 0 700 520"
      role="img"
      aria-label="Illustration of a student researching at a computer late at night"
    >
      <defs>
        <radialGradient id="screen-glow">
          <stop stopColor="#8274ee" stopOpacity=".56" />
          <stop offset="1" stopColor="#8274ee" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="screen-face" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#34365e" />
          <stop offset="1" stopColor="#171d38" />
        </linearGradient>
        <linearGradient id="window-night" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#111934" />
          <stop offset="1" stopColor="#202546" />
        </linearGradient>
      </defs>
      <rect
        x="43"
        y="47"
        width="208"
        height="215"
        rx="15"
        fill="url(#window-night)"
        stroke="#4c527c"
        strokeWidth="3"
      />
      <path d="M147 47v215M43 154h208" stroke="#4c527c" strokeWidth="5" />
      <circle cx="198" cy="103" r="17" fill="#e4d6a8" opacity=".78" />
      <circle cx="83" cy="86" r="2" fill="#d6d9ff" />
      <circle cx="113" cy="128" r="1.5" fill="#d6d9ff" />
      <circle cx="219" cy="201" r="2" fill="#d6d9ff" />
      <path d="M0 431h700" stroke="#8175b1" strokeWidth="5" />
      <ellipse cx="349" cy="448" rx="300" ry="19" fill="#080b18" opacity=".5" />
      <motion.circle
        cx="346"
        cy="266"
        r="195"
        fill="url(#screen-glow)"
        animate={reduced ? undefined : { opacity: [0.46, 0.9, 0.46] }}
        transition={{ duration: 3.4, repeat: Infinity }}
      />
      <path
        d="M242 361h235l-19 65H260z"
        fill="#34334e"
        stroke="#77749c"
        strokeWidth="3"
      />
      <rect
        x="220"
        y="156"
        width="277"
        height="208"
        rx="19"
        fill="#111529"
        stroke="#8f89b9"
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
        fill="#aa9ef4"
        opacity=".75"
      />
      <rect x="261" y="224" width="177" height="6" rx="3" fill="#747ea9" />
      <rect x="261" y="241" width="149" height="6" rx="3" fill="#747ea9" />
      <rect x="261" y="258" width="160" height="6" rx="3" fill="#747ea9" />
      <circle cx="287" cy="303" r="7" fill="#b3a3ff" />
      <circle cx="355" cy="291" r="7" fill="#95a8f7" />
      <circle cx="422" cy="312" r="7" fill="#b3a3ff" />
      <path d="M293 303l55-12m14 1 53 18" stroke="#9e99da" strokeWidth="3" />
      <path
        d="M347 365v23m-57 0h115"
        stroke="#77749c"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path
        d="M526 433v-94c0-69 22-112 73-112s64 44 64 112v94"
        fill="#342b50"
        stroke="#8b76b5"
        strokeWidth="3"
      />
      <motion.g
        animate={reduced ? undefined : { rotate: [-2, 2, -2] }}
        transition={{ duration: 4.2, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "594px 258px" }}
      >
        <circle cx="594" cy="215" r="43" fill="#c69c8d" />
        <path
          d="M554 211c-2-50 24-74 57-68 36 5 47 39 33 73-17-15-23-26-26-42-17 27-42 33-64 37z"
          fill="#29243e"
        />
      </motion.g>
      <motion.path
        d="M548 329c-45 10-53 42-85 67l-29-7"
        fill="none"
        stroke="#c69c8d"
        strokeWidth="19"
        strokeLinecap="round"
        animate={reduced ? undefined : { rotate: [0, -3, 0] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "548px 329px" }}
      />
      <path d="M491 431c-12-25-17-50-15-72l82-39 83 22 16 89" fill="#342b50" />
      <path d="M68 409h114l-9 20H76z" fill="#5f658c" />
      <path d="M82 393h99l-5 16H76z" fill="#a185ae" />
      <motion.g
        animate={reduced ? undefined : { y: [0, -7, 0], rotate: [0, 1, 0] }}
        transition={{ duration: 4.5, repeat: Infinity }}
      >
        <rect
          x="86"
          y="293"
          width="94"
          height="75"
          rx="5"
          transform="rotate(-10 86 293)"
          fill="#e2d8d2"
        />
        <path
          d="M101 310l53-9m-50 21 47-8m-44 20 55-9"
          stroke="#898ba7"
          strokeWidth="3"
        />
      </motion.g>
      <path d="M85 458h104m-52-25v25" stroke="#756e98" strokeWidth="4" />
      <motion.g
        className="story-bulb"
        animate={reduced ? undefined : { y: [0, -7, 0], rotate: [-3, 3, -3] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
        style={{ transformOrigin: "594px 80px" }}
      >
        <circle cx="594" cy="80" r="54" fill="#f5ce74" opacity=".08" />
        <path
          d="M594 38c-24 0-39 18-39 38 0 17 10 25 18 34 4 4 7 11 7 17h28c0-6 3-13 7-17 8-9 18-17 18-34 0-20-15-38-39-38z"
          fill="#d0b4a3"
          stroke="#f3ddb8"
          strokeWidth="3"
        />
        <path
          d="M580 127h28m-25 9h22m-19 8h16"
          stroke="#f3ddb8"
          strokeWidth="5"
          strokeLinecap="round"
        />
      </motion.g>
      <text x="84" y="488" fill="#aca9d1" fontSize="15" letterSpacing="3">
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
}: {
  x: number;
  y: number;
  title: string;
  small?: boolean;
  active?: boolean;
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
        fill={small ? "#29294c" : "#3c315f"}
        stroke={small ? "#a9a3e4" : "#d2b9ff"}
        strokeWidth="2.5"
      />
      <circle
        cx={x}
        cy={y}
        r={small ? 57 : 82}
        fill="none"
        stroke="#aa8cff"
        opacity=".16"
        strokeWidth="2"
      />
      <text
        x={x}
        y={y + 5}
        textAnchor="middle"
        fill="#f6f2ff"
        fontSize={small ? "14" : "16"}
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
  const duration = reduced ? 0 : 0.9;
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
          <path d="M0 0L10 5L0 10z" fill="#b8adf7" />
        </marker>
      </defs>
      <circle cx="350" cy="260" r="214" fill="#6c58b8" opacity=".045" />
      <motion.path
        d="M292 219 C238 150 207 145 177 144"
        fill="none"
        stroke="#a6a0e8"
        strokeWidth="3"
        markerEnd="url(#story-arrow)"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: showPast ? 1 : 0, opacity: showPast ? 1 : 0 }}
        transition={{ duration }}
      />
      <motion.path
        d="M291 302 C230 360 211 371 178 373"
        fill="none"
        stroke="#a6a0e8"
        strokeWidth="3"
        markerEnd="url(#story-arrow)"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: showPast ? 1 : 0, opacity: showPast ? 1 : 0 }}
        transition={{ duration, delay: reduced ? 0 : 0.16 }}
      />
      <motion.path
        d="M525 143 C470 147 442 183 410 221"
        fill="none"
        stroke="#8ddbc9"
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
        stroke="#8ddbc9"
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
          fill="#1a1b34"
          stroke="#8c7dc3"
        />
        <text
          x="350"
          y="408"
          textAnchor="middle"
          fill="#b9a9fc"
          fontSize="12"
          letterSpacing="2"
        >
          CITATION EVIDENCE
        </text>
        <text x="350" y="433" textAnchor="middle" fill="#f2eeff" fontSize="15">
          What does this connection mean?
        </text>
      </motion.g>
      <text
        x="350"
        y="32"
        textAnchor="middle"
        fill="#858ba9"
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
    stiffness: 115,
    damping: 30,
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
    [1, 1.05, 1.16, 1.16, 1.2, 3.7],
  );
  const roomOpacity = useTransform(
    progress,
    [0, 0.26, 0.35, 0.48, 0.58, 0.72, 0.82],
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
    [0.45, 0.45, 0.85, 2.8, 7],
  );
  const screenOpacity = useTransform(
    progress,
    [0, 0.59, 0.68, 0.81, 0.9],
    [0, 0, 1, 1, 0],
  );
  const finaleOpacity = useTransform(progress, [0, 0.83, 0.91], [0, 0, 1]);
  const finaleScale = useTransform(progress, [0, 0.84, 1], [0.8, 0.8, 1]);
  const copyOpacity = useTransform(progress, [0, 0.65, 0.81], [1, 1, 0]);

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
          <StudentScene reduced={reduced} />
          <motion.div
            className="story-idea-glow"
            style={reduced ? { opacity: 0 } : { opacity: bulbGlow }}
            aria-hidden="true"
          />
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
            <span className="story-terminal-label">RESEARCH, CONNECTED</span>
            <span className={`story-typed${active >= 3 ? " is-typing" : ""}`}>
              TRACE<span className="story-caret">_</span>
            </span>
            <span className="story-terminal-subtitle">
              See where every idea leads.
            </span>
          </div>
        </motion.div>
        <motion.div
          className={`story-finale${active === 4 ? " is-active" : ""}`}
          style={
            reduced
              ? { opacity: 1, scale: 1 }
              : { opacity: finaleOpacity, scale: finaleScale }
          }
        >
          <div className="story-finale-orbit" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
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
            <span aria-hidden="true">◎</span> TRACE
          </span>
          <button className="story-skip" onClick={onExplore}>
            Skip to graph <span aria-hidden="true">↗</span>
          </button>
        </header>
        <motion.div
          className="story-narration"
          style={reduced ? { opacity: 0 } : { opacity: copyOpacity }}
          aria-live="polite"
        >
          <span className="story-chapter">{chapter.number}</span>
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: reduced ? 0 : 28 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: reduced ? 0 : -18 }}
              transition={{ duration: reduced ? 0.01 : 0.42 }}
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
          <span>
            {active === 4 ? "THE MAP IS YOURS" : "SCROLL TO FOLLOW THE STORY"}
          </span>
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
