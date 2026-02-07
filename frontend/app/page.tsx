"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { TextGenerateEffect } from "@/components/ui/text-generate-effect";
import { PlaceholdersAndVanishInput } from "@/components/ui/placeholders-and-vanish-input";

function extractArxivId(inputRaw: string): string | null {
  const input = inputRaw.trim();
  if (!input) return null;

  const directNew = input.match(/^\d{4}\.\d{4,5}(v\d+)?$/i);
  if (directNew) return directNew[0];

  const directOld = input.match(/^[a-z-]+(\.[a-z]{2})?\/\d{7}(v\d+)?$/i);
  if (directOld) return directOld[0];

  const urlAbs = input.match(/arxiv\.org\/abs\/([^?\s#]+)/i);
  if (urlAbs?.[1]) return decodeURIComponent(urlAbs[1]).replace(/\/$/, "");

  const urlPdf = input.match(/arxiv\.org\/pdf\/([^?\s#]+?)(?:\.pdf)?$/i);
  if (urlPdf?.[1]) return decodeURIComponent(urlPdf[1]).replace(/\/$/, "");

  return null;
}

const placeholders = [
  "Paste an arXiv URL or ID...",
  "1706.03762 (Attention Is All You Need)",
  "https://arxiv.org/abs/2005.14165",
  "2303.08774 (GPT-4 Technical Report)",
  "1810.04805 (BERT)",
];

// Animated math symbols floating in background
const MathSymbol = ({ 
  symbol, 
  delay, 
  duration, 
  x, 
  y,
  size = "text-2xl"
}: { 
  symbol: string; 
  delay: number; 
  duration: number; 
  x: string; 
  y: string;
  size?: string;
}) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ 
      opacity: [0, 0.15, 0.15, 0],
      y: [20, 0, 0, -20],
    }}
    transition={{ 
      duration, 
      delay, 
      repeat: Infinity,
      repeatDelay: Math.random() * 2
    }}
    className={`absolute ${x} ${y} ${size} font-serif text-[#58c4dd] pointer-events-none select-none`}
  >
    {symbol}
  </motion.div>
);

// Pi creature inspired logo
const PiLogo = () => (
  <motion.div
    whileHover={{ scale: 1.1, rotate: 5 }}
    className="relative"
  >
    <div className="h-12 w-12 rounded-2xl bg-gradient-to-br from-[#58c4dd]/20 to-[#cd8b62]/20 ring-1 ring-[#58c4dd]/30 flex items-center justify-center backdrop-blur-sm">
      <span className="text-2xl font-serif text-[#58c4dd]">π</span>
    </div>
    <motion.div
      animate={{ scale: [1, 1.2, 1] }}
      transition={{ duration: 2, repeat: Infinity }}
      className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-[#58c4dd]/20 to-[#cd8b62]/20 blur-xl -z-10"
    />
  </motion.div>
);

// Geometric background element
const GeometricShape = ({ className }: { className?: string }) => (
  <svg 
    viewBox="0 0 100 100" 
    className={`absolute opacity-[0.03] pointer-events-none ${className}`}
  >
    <circle cx="50" cy="50" r="45" fill="none" stroke="#58c4dd" strokeWidth="0.5" />
    <circle cx="50" cy="50" r="30" fill="none" stroke="#cd8b62" strokeWidth="0.5" />
    <circle cx="50" cy="50" r="15" fill="none" stroke="#58c4dd" strokeWidth="0.5" />
    <line x1="5" y1="50" x2="95" y2="50" stroke="#58c4dd" strokeWidth="0.3" />
    <line x1="50" y1="5" x2="50" y2="95" stroke="#58c4dd" strokeWidth="0.3" />
  </svg>
);

export default function Home() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [touched, setTouched] = useState(false);

  const parsedId = useMemo(() => extractArxivId(value), [value]);
  const canSubmit = Boolean(parsedId);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!parsedId) return;
    router.push(`/abs/${encodeURIComponent(parsedId)}`);
  }

  const features = [
    {
      title: "Parse",
      description: "Extract sections, equations, and figures automatically",
      icon: "∫",
      color: "#58c4dd",
    },
    {
      title: "Analyze",
      description: "AI identifies concepts perfect for visual explanation",
      icon: "∑",
      color: "#cd8b62",
    },
    {
      title: "Animate",
      description: "Generate elegant Manim visualizations",
      icon: "∞",
      color: "#f9c74f",
    },
  ];

  return (
    <main className="min-h-dvh relative overflow-hidden bg-[#1c1c2e]">
      {/* Grid background */}
      <div className="absolute inset-0 grid-3b1b" />
      
      {/* Geometric shapes */}
      <GeometricShape className="w-[600px] h-[600px] -top-40 -right-40" />
      <GeometricShape className="w-[400px] h-[400px] -bottom-20 -left-20" />
      
      {/* Floating math symbols */}
      <MathSymbol symbol="∫" delay={0} duration={8} x="left-[10%]" y="top-[20%]" size="text-4xl" />
      <MathSymbol symbol="∑" delay={1} duration={7} x="right-[15%]" y="top-[30%]" size="text-3xl" />
      <MathSymbol symbol="∂" delay={2} duration={9} x="left-[20%]" y="bottom-[30%]" />
      <MathSymbol symbol="∇" delay={0.5} duration={8} x="right-[25%]" y="bottom-[20%]" size="text-3xl" />
      <MathSymbol symbol="λ" delay={1.5} duration={7} x="left-[5%]" y="top-[60%]" />
      <MathSymbol symbol="θ" delay={2.5} duration={8} x="right-[8%]" y="top-[50%]" />
      <MathSymbol symbol="π" delay={3} duration={9} x="left-[30%]" y="top-[10%]" size="text-xl" />
      <MathSymbol symbol="α" delay={1} duration={7} x="right-[30%]" y="bottom-[40%]" />
      <MathSymbol symbol="β" delay={2} duration={8} x="left-[40%]" y="bottom-[15%]" />
      <MathSymbol symbol="γ" delay={0.8} duration={9} x="right-[40%]" y="top-[15%]" />

      {/* Gradient orbs */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-[#58c4dd]/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[400px] h-[400px] bg-[#cd8b62]/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="relative z-10 mx-auto w-full max-w-6xl px-6 py-8 sm:py-12">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="flex items-center justify-between"
        >
          <div className="flex items-center gap-4">
            <PiLogo />
            <div className="leading-tight">
              <div className="text-lg font-semibold text-[#f4f1eb]">ArXiviz</div>
              <div className="text-sm text-[#58c4dd]/70">
                Mathematical visualizations
              </div>
            </div>
          </div>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="hidden items-center gap-3 sm:flex"
          >
            <div className="flex items-center gap-2 rounded-full bg-[#58c4dd]/10 px-4 py-2 ring-1 ring-[#58c4dd]/20">
              <span className="text-[#58c4dd] text-sm">∴</span>
              <span className="text-sm text-[#f4f1eb]/70">Powered by Manim</span>
            </div>
          </motion.div>
        </motion.header>

        {/* Hero Section */}
        <section className="pt-16 sm:pt-24 pb-8">
          <div className="max-w-4xl mx-auto text-center">
            {/* Decorative line */}
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.8, delay: 0.2 }}
              className="w-24 h-px bg-gradient-to-r from-transparent via-[#58c4dd] to-transparent mx-auto mb-8"
            />

            {/* Main Headline */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.3 }}
            >
              <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tight text-[#f4f1eb]">
                <TextGenerateEffect
                  words="Transform research into"
                  className="inline font-light"
                  duration={0.4}
                />
                <span className="block mt-3">
                  <span className="font-light text-[#58c4dd]">visual</span>
                  {" "}
                  <span className="text-gradient-3b1b font-medium">understanding</span>
                </span>
              </h1>
            </motion.div>

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.9 }}
              className="mt-8 text-lg sm:text-xl text-[#f4f1eb]/60 max-w-2xl mx-auto leading-relaxed font-light"
            >
              Paste any arXiv paper. Watch as we transform complex mathematics 
              into elegant{" "}
              <span className="text-[#58c4dd] font-medium">3Blue1Brown-style</span>{" "}
              animations that make ideas click.
            </motion.p>

            {/* Input Section */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 1.1 }}
              className="mt-12 max-w-xl mx-auto"
            >
              <div className="relative">
                {/* Decorative brackets */}
                <div className="absolute -left-4 top-1/2 -translate-y-1/2 text-3xl text-[#58c4dd]/20 font-light select-none hidden sm:block">
                  [
                </div>
                <div className="absolute -right-4 top-1/2 -translate-y-1/2 text-3xl text-[#58c4dd]/20 font-light select-none hidden sm:block">
                  ]
                </div>
                
                <PlaceholdersAndVanishInput
                  placeholders={placeholders}
                  value={value}
                  onChange={(e) => {
                    setValue(e.target.value);
                    setTouched(true);
                  }}
                  onSubmit={onSubmit}
                  disabled={!canSubmit && touched && value.length > 0}
                />
              </div>

              {/* Status feedback */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.3 }}
                className="mt-4 h-6 text-sm"
              >
                {parsedId ? (
                  <span className="text-[#83c167] flex items-center justify-center gap-2">
                    <span className="text-lg">✓</span>
                    <span>Detected:{" "}</span>
                    <span className="font-mono bg-[#83c167]/10 px-2 py-0.5 rounded">{parsedId}</span>
                  </span>
                ) : touched && value ? (
                  <span className="text-[#cd8b62]">
                    Enter a valid arXiv URL or paper ID
                  </span>
                ) : null}
              </motion.div>
            </motion.div>

            {/* Quick Examples */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 1.4 }}
              className="mt-8 flex flex-wrap items-center justify-center gap-3"
            >
              <span className="text-sm text-[#f4f1eb]/40">Try these:</span>
              {[
                { id: "1706.03762", label: "Transformers", icon: "⊕" },
                { id: "2005.14165", label: "GPT-3", icon: "⊗" },
                { id: "2303.08774", label: "GPT-4", icon: "⊙" },
              ].map((example) => (
                <motion.button
                  key={example.id}
                  whileHover={{ scale: 1.05, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setValue(example.id)}
                  className="group rounded-xl bg-[#58c4dd]/5 px-4 py-2.5 text-sm ring-1 ring-[#58c4dd]/20 transition-all hover:bg-[#58c4dd]/10 hover:ring-[#58c4dd]/40"
                >
                  <span className="text-[#58c4dd] mr-2">{example.icon}</span>
                  <span className="text-[#f4f1eb]/80 font-mono">{example.id}</span>
                  <span className="text-[#f4f1eb]/40 ml-2">({example.label})</span>
                </motion.button>
              ))}
            </motion.div>
          </div>
        </section>

        {/* How It Works */}
        <motion.section
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 1.6 }}
          className="mt-20 sm:mt-28"
        >
          {/* Section divider */}
          <div className="flex items-center gap-4 mb-12">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent to-[#58c4dd]/20" />
            <span className="text-[#58c4dd]/50 text-sm font-mono">// HOW IT WORKS</span>
            <div className="h-px flex-1 bg-gradient-to-l from-transparent to-[#58c4dd]/20" />
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            {features.map((feature, i) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 1.7 + i * 0.1 }}
                whileHover={{ y: -5 }}
                className="group relative"
              >
                <div className="rounded-2xl bg-gradient-to-b from-white/[0.03] to-transparent p-6 ring-1 ring-white/10 hover:ring-[#58c4dd]/30 transition-all duration-300 h-full">
                  {/* Step number */}
                  <div className="flex items-center justify-between mb-4">
                    <span 
                      className="text-4xl font-serif"
                      style={{ color: feature.color }}
                    >
                      {feature.icon}
                    </span>
                    <span className="text-[#f4f1eb]/20 font-mono text-sm">0{i + 1}</span>
                  </div>
                  
                  <h3 className="text-xl font-medium text-[#f4f1eb] mb-2">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-[#f4f1eb]/50 leading-relaxed">
                    {feature.description}
                  </p>

                  {/* Hover glow */}
                  <div 
                    className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                    style={{
                      background: `radial-gradient(circle at 50% 0%, ${feature.color}10, transparent 70%)`,
                    }}
                  />
                </div>
              </motion.div>
            ))}
          </div>

          {/* Connecting lines */}
          <div className="hidden md:flex justify-center items-center gap-4 mt-8">
            <div className="w-20 h-px bg-gradient-to-r from-[#58c4dd]/30 to-[#cd8b62]/30" />
            <span className="text-[#f4f1eb]/20">→</span>
            <div className="w-20 h-px bg-gradient-to-r from-[#cd8b62]/30 to-[#f9c74f]/30" />
            <span className="text-[#f4f1eb]/20">→</span>
            <div className="w-20 h-px bg-[#f9c74f]/30" />
          </div>
        </motion.section>

        {/* Mathematical Quote */}
        <motion.section
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 2 }}
          className="mt-24 text-center"
        >
          <div className="max-w-2xl mx-auto">
            <div className="relative">
              <span className="absolute -top-6 -left-4 text-6xl text-[#58c4dd]/10 font-serif">"</span>
              <p className="text-lg sm:text-xl text-[#f4f1eb]/70 font-light italic leading-relaxed">
                The essence of mathematics is not to make simple things complicated, 
                but to make complicated things simple.
              </p>
              <span className="absolute -bottom-4 -right-4 text-6xl text-[#58c4dd]/10 font-serif rotate-180">"</span>
            </div>
            <p className="mt-6 text-sm text-[#cd8b62]/70">— Stan Gudder</p>
          </div>
        </motion.section>

        {/* Call to Action Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 2.2 }}
          className="mt-20 max-w-2xl mx-auto"
        >
          <div className="relative rounded-3xl overflow-hidden">
            {/* Animated border gradient */}
            <div className="absolute inset-0 bg-gradient-to-r from-[#58c4dd]/20 via-[#cd8b62]/20 to-[#58c4dd]/20 animate-pulse" />
            <div className="relative m-[1px] rounded-3xl bg-[#1c1c2e] p-8">
              <div className="flex items-center gap-4 mb-4">
                <div className="h-12 w-12 rounded-xl bg-[#58c4dd]/10 flex items-center justify-center ring-1 ring-[#58c4dd]/20">
                  <span className="text-2xl">💡</span>
                </div>
                <div>
                  <h3 className="font-semibold text-[#f4f1eb]">Pro Tip</h3>
                  <p className="text-sm text-[#f4f1eb]/50">Works with any arXiv format</p>
                </div>
              </div>
              <p className="text-sm text-[#f4f1eb]/60 leading-relaxed">
                Paste a full URL like{" "}
                <code className="text-[#58c4dd] bg-[#58c4dd]/10 px-2 py-0.5 rounded text-xs font-mono">
                  https://arxiv.org/abs/1706.03762
                </code>
                {" "}or just the paper ID. We handle{" "}
                <code className="text-[#f4f1eb]/70 bg-white/5 px-1.5 py-0.5 rounded text-xs">/abs/</code>,{" "}
                <code className="text-[#f4f1eb]/70 bg-white/5 px-1.5 py-0.5 rounded text-xs">/pdf/</code>, 
                and direct IDs automatically.
              </p>
            </div>
          </div>
        </motion.div>

        {/* Footer */}
        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 2.4 }}
          className="mt-20 flex flex-col items-center justify-between gap-4 border-t border-[#58c4dd]/10 pt-8 text-sm sm:flex-row"
        >
          <div className="flex items-center gap-3 text-[#f4f1eb]/40">
            <motion.span 
              animate={{ rotate: 360 }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              className="text-[#58c4dd]"
            >
              ◈
            </motion.span>
            <span>Visualizing mathematics, one paper at a time</span>
          </div>
          <div className="flex items-center gap-4">
            <a
              className="rounded-lg px-3 py-1.5 text-[#f4f1eb]/50 ring-1 ring-[#58c4dd]/20 transition hover:bg-[#58c4dd]/10 hover:text-[#58c4dd]"
              href="https://arxiv.org"
              target="_blank"
              rel="noreferrer"
            >
              arXiv
            </a>
            <a
              className="rounded-lg px-3 py-1.5 text-[#f4f1eb]/50 ring-1 ring-[#cd8b62]/20 transition hover:bg-[#cd8b62]/10 hover:text-[#cd8b62]"
              href="https://www.manim.community/"
              target="_blank"
              rel="noreferrer"
            >
              Manim
            </a>
            <a
              className="rounded-lg px-3 py-1.5 text-[#f4f1eb]/50 ring-1 ring-[#f9c74f]/20 transition hover:bg-[#f9c74f]/10 hover:text-[#f9c74f]"
              href="https://www.3blue1brown.com/"
              target="_blank"
              rel="noreferrer"
            >
              3Blue1Brown
            </a>
          </div>
        </motion.footer>
      </div>
    </main>
  );
}
