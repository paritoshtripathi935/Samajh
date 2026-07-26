'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

/**
 * Render digitised / translated Markdown. remark-gfm gives us tables + strikethrough;
 * rehype-raw renders any inline HTML (some DI output uses HTML tables). `urlTransform`
 * is a pass-through so embedded `data:image/...;base64` scan images render as <img>.
 * Content comes from our own backend (Sarvam), not arbitrary third parties.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        urlTransform={(url) => url}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
