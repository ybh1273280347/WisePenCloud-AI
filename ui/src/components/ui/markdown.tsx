import type { ComponentPropsWithoutRef } from "react";
import { memo, useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { mermaid } from "@streamdown/mermaid";
import { createMathPlugin } from "@streamdown/math";
import "katex/dist/katex.min.css";
import { cn } from "../../lib/utils";

type MarkdownProps = {
  children: string;
  className?: string;
  isStreaming?: boolean;
};

const math = createMathPlugin({
  singleDollarTextMath: false,
});

const plugins = { code, mermaid, math };
const STREAMING_RENDER_INTERVAL_MS = 80;

const components = {
  blockquote({ children, ...props }: ComponentPropsWithoutRef<"blockquote">) {
    return (
      <blockquote
        {...props}
        className="my-4 rounded-r-lg border-l-[3px] border-l-sky-600 bg-sky-50/40 p-4 pl-5 text-gray-800 not-italic shadow-sm"
      >
        {children}
      </blockquote>
    );
  },
} as const;

function useStreamingText(value: string, isStreaming = false) {
  const [visibleText, setVisibleText] = useState(value);
  const latestTextRef = useRef(value);
  const timerRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    latestTextRef.current = value;

    if (!isStreaming) {
      if (timerRef.current !== undefined) {
        window.clearTimeout(timerRef.current);
        timerRef.current = undefined;
      }
      return;
    }

    if (timerRef.current !== undefined) {
      return;
    }

    timerRef.current = window.setTimeout(() => {
      timerRef.current = undefined;
      setVisibleText(latestTextRef.current);
    }, STREAMING_RENDER_INTERVAL_MS);
  }, [isStreaming, value]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== undefined) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, []);

  return isStreaming ? visibleText : value;
}

function MarkdownComponent({ children, className, isStreaming }: MarkdownProps) {
  const visibleText = useStreamingText(children, isStreaming);

  return (
    <Streamdown
      className={cn("markdown-body", className)}
      components={components}
      controls={!isStreaming}
      isAnimating={false}
      lineNumbers={!isStreaming}
      mode={isStreaming ? "streaming" : "static"}
      parseIncompleteMarkdown={!isStreaming}
      plugins={isStreaming ? undefined : plugins}
    >
      {visibleText}
    </Streamdown>
  );
}

export const Markdown = memo(MarkdownComponent);
