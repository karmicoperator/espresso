"use client";

import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

type MarkdownContentProps = {
  content: string;
  className?: string;
};

/**
 * Renders markdown content with LaTeX math support.
 * 
 * Supports:
 * - Standard markdown (bold, italic, lists, etc.)
 * - Inline math with $...$ or \(...\)
 * - Block math with $$...$$ or \[...\]
 * - Auto-detection of common LaTeX patterns
 */
export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  // Pre-process content to convert and detect LaTeX patterns
  const processedContent = preprocessLatex(content);

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Style paragraphs
          p: ({ children }) => (
            <p className="mb-4 last:mb-0">{children}</p>
          ),
          // Style strong text
          strong: ({ children }) => (
            <strong className="font-semibold text-white">{children}</strong>
          ),
          // Style emphasis
          em: ({ children }) => (
            <em className="italic text-white/90">{children}</em>
          ),
          // Style inline code
          code: ({ children, className }) => {
            // Check if this is a code block (has language class) vs inline code
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return (
                <code className="block overflow-x-auto rounded-lg bg-black/30 px-4 py-3 text-sm text-blue-200/90">
                  {children}
                </code>
              );
            }
            return (
              <code className="rounded bg-white/10 px-1.5 py-0.5 text-sm text-blue-200/90">
                {children}
              </code>
            );
          },
          // Style code blocks
          pre: ({ children }) => (
            <pre className="mb-4 overflow-x-auto rounded-xl bg-black/25 ring-1 ring-white/10">
              {children}
            </pre>
          ),
          // Style unordered lists
          ul: ({ children }) => (
            <ul className="mb-4 ml-4 list-disc space-y-1 last:mb-0">{children}</ul>
          ),
          // Style ordered lists
          ol: ({ children }) => (
            <ol className="mb-4 ml-4 list-decimal space-y-1 last:mb-0">{children}</ol>
          ),
          // Style list items
          li: ({ children }) => (
            <li className="text-white/70">{children}</li>
          ),
          // Style headers (rarely used in section content but just in case)
          h1: ({ children }) => (
            <h1 className="mb-3 text-xl font-semibold text-white">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-3 text-lg font-semibold text-white">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 text-base font-semibold text-white">{children}</h3>
          ),
          // Style blockquotes
          blockquote: ({ children }) => (
            <blockquote className="mb-4 border-l-2 border-blue-400/50 pl-4 italic text-white/60 last:mb-0">
              {children}
            </blockquote>
          ),
          // Style links
          a: ({ children, href }) => (
            <a
              href={href}
              className="text-blue-400 underline decoration-blue-400/30 hover:decoration-blue-400"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Pre-process content to normalize LaTeX delimiters and detect math patterns.
 */
function preprocessLatex(content: string): string {
  let processed = content;
  
  // Convert \( ... \) to $ ... $ for inline math
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => `$${math}$`);
  
  // Convert \[ ... \] to $$ ... $$ for display math
  processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => `$$${math}$$`);
  
  // Auto-detect and wrap common LaTeX patterns that aren't already wrapped
  // Only do this for content that doesn't already have $ delimiters
  if (!processed.includes('$')) {
    processed = wrapLatexPatterns(processed);
  }
  
  return processed;
}

/**
 * Detect and wrap LaTeX-like patterns in plain text.
 * This handles content where equations were extracted but not marked up.
 */
function wrapLatexPatterns(content: string): string {
  let result = content;
  
  // Pattern for LaTeX commands that indicate math content
  // Matches things like \text{...}, \frac{...}, \sqrt{...}, etc.
  const latexCommandPattern = /\\(?:text|frac|sqrt|sum|prod|int|lim|log|ln|sin|cos|tan|exp|max|min|sup|inf|mathbb|mathcal|mathbf|mathrm|left|right|cdot|times|div|pm|mp|leq|geq|neq|approx|equiv|subset|supset|in|notin|forall|exists|partial|nabla|infty|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|omega|phi|psi|pi|rho|tau|chi|eta|zeta|xi|kappa|nu|vec|hat|bar|tilde|dot|ddot|overline|underline)(?:\{[^}]*\}|\b)/g;
  
  // Pattern for subscripts/superscripts (common in math)
  const subSupPattern = /\b([A-Za-z])_\{?([^}\s]+)\}?|\b([A-Za-z])\^?\{?([^}\s]+)\}?/g;
  
  // Pattern for display-style equations (usually standalone lines with operators)
  const displayEquationPattern = /^(.+(?:=|\\approx|\\equiv|\\leq|\\geq).+)$/gm;
  
  // Check if content has LaTeX commands
  const hasLatexCommands = latexCommandPattern.test(result);
  
  if (hasLatexCommands) {
    // Wrap sequences containing LaTeX commands as inline math
    // This is a simplified approach - wrap whole "math-looking" segments
    result = result.replace(
      /([A-Za-z0-9\s]*\\[a-z]+(?:\{[^}]*\}|\[[^\]]*\])*[A-Za-z0-9_^{}\s\\]*)+/g,
      (match) => {
        // Don't double-wrap
        if (match.startsWith('$') || match.startsWith('\\(')) {
          return match;
        }
        // Check if it looks like an equation (has operators)
        const isDisplayMath = /[=<>]/.test(match) && match.length > 20;
        return isDisplayMath ? `\n\n$$${match.trim()}$$\n\n` : `$${match.trim()}$`;
      }
    );
  }
  
  return result;
}
