'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertTriangle, ArrowLeft, FileText, Loader2, MessageCircle, Send, Scale } from 'lucide-react';
import Markdown from '@/components/Markdown';
import ThemeToggle from '@/components/ThemeToggle';
import { api, type DocumentBundle, type DocumentChatMessage, type DocumentConversation } from '@/lib/api';
import { t } from '@/lib/design/tokens';

export default function DocumentChatPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const documentId = params?.id;
  const [bundle, setBundle] = useState<DocumentBundle | null>(null);
  const [conversations, setConversations] = useState<DocumentConversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DocumentChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      if (!documentId) return;
      setLoading(true);
      setError(null);
      try {
        const [documentBundle, convoResult] = await Promise.all([
          api.getDocument(documentId),
          api.listDocumentConversations(documentId),
        ]);
        if (!alive) return;
        setBundle(documentBundle);
        setConversations(convoResult.conversations);
        const first = convoResult.conversations[0];
        if (first) {
          setConversationId(first.id);
          const messageResult = await api.listConversationMessages(first.id);
          if (alive) setMessages(messageResult.messages);
        }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [documentId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, sending]);

  const fileName = bundle?.document.file_name ?? 'Document chat';
  const contextState = useMemo(() => {
    const hasEnglish = Boolean(bundle?.translations?.[0]?.translated_text);
    const hasRaw = Boolean(bundle?.digitizations?.[0]?.content);
    const hasPageJson = Boolean(bundle?.digitizations?.some((digitization) => Array.isArray(digitization.content_json) && digitization.content_json.length > 0));
    const hasMetadata = Boolean(bundle?.extractions?.some((extraction) => Object.keys(extraction.fields ?? {}).length > 0));
    if (hasEnglish) return 'English translation loaded';
    if (hasRaw) return 'Raw extraction loaded';
    if (hasPageJson) return 'Page extraction loaded';
    if (hasMetadata) return 'Legal metadata loaded';
    return 'No context available';
  }, [bundle]);

  async function sendMessage() {
    const text = input.trim();
    if (!documentId || !text || sending) return;
    setSending(true);
    setError(null);
    setInput('');
    const userMessage: DocumentChatMessage = { role: 'user', content: text };
    setMessages((current) => [...current, userMessage]);
    try {
      const response = await api.chatWithDocument(documentId, {
        message: text,
        conversation_id: conversationId,
      });
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, { role: 'assistant', content: response.answer }]);
      if (!conversationId) {
        const convoResult = await api.listDocumentConversations(documentId);
        setConversations(convoResult.conversations);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', gridTemplateColumns: '260px minmax(0, 1fr)', backgroundColor: t.color.bg }}>
      <aside style={{ borderRight: `1px solid ${t.color.border}`, backgroundColor: t.color.surface, display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: t.space.lg, borderBottom: `1px solid ${t.color.border}` }}>
          <div className="flex items-center" style={{ gap: t.space.sm }}>
            <Scale size={19} style={{ color: t.color.accent }} />
            <div>
              <div className="serif" style={{ color: t.color.text, fontSize: 22, fontWeight: t.weight.bold }}>Samajh</div>
              <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, textTransform: 'uppercase' }}>Document chat</div>
            </div>
          </div>
        </div>
        <button
          onClick={() => router.push('/dashboard')}
          className="inline-flex items-center cursor-pointer"
          style={{
            gap: t.space.sm,
            margin: t.space.md,
            padding: `9px ${t.space.sm}`,
            border: `1px solid ${t.color.border}`,
            borderRadius: t.radius.sm,
            backgroundColor: t.color.raised,
            color: t.color.text,
            fontSize: t.size.ui,
          }}
        >
          <ArrowLeft size={15} /> Dashboard
        </button>
        <div style={{ padding: t.space.md, borderTop: `1px solid ${t.color.border}` }}>
          <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, textTransform: 'uppercase', marginBottom: t.space.sm }}>
            Conversations
          </div>
          {conversations.length === 0 ? (
            <div style={{ color: t.color.dim, fontSize: t.size.ui }}>Ask the first question to start a thread.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  onClick={async () => {
                    setConversationId(conversation.id);
                    const result = await api.listConversationMessages(conversation.id);
                    setMessages(result.messages);
                  }}
                  style={{
                    textAlign: 'left',
                    border: `1px solid ${conversation.id === conversationId ? t.color.accent : t.color.border}`,
                    borderRadius: t.radius.sm,
                    backgroundColor: conversation.id === conversationId ? t.color.active : t.color.raised,
                    color: t.color.text,
                    padding: t.space.sm,
                    cursor: 'pointer',
                  }}
                >
                  {conversation.title}
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <header className="flex items-center" style={{ minHeight: 58, padding: `0 ${t.space.lg}`, borderBottom: `1px solid ${t.color.border}`, backgroundColor: t.color.surface }}>
          <FileText size={17} style={{ color: t.color.accent, marginRight: t.space.sm }} />
          <div style={{ minWidth: 0 }}>
            <div className="serif" style={{ color: t.color.text, fontSize: t.size.h2, fontWeight: t.weight.semibold, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {fileName}
            </div>
            <div className="mono" style={{ color: t.color.dim, fontSize: t.size.micro, textTransform: 'uppercase' }}>
              {contextState}
            </div>
          </div>
          <div style={{ marginLeft: 'auto' }}>
            <ThemeToggle />
          </div>
        </header>

        <section style={{ flex: 1, overflow: 'auto', padding: t.space.lg }}>
          {loading ? (
            <State icon={<Loader2 size={17} className="animate-spin" />} text="Loading document chat" />
          ) : error ? (
            <State icon={<AlertTriangle size={17} />} text={error} />
          ) : messages.length === 0 ? (
            <State icon={<MessageCircle size={17} />} text="Ask a question about this filing. Answers stay grounded in the document text." />
          ) : (
            <div style={{ maxWidth: 860, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: t.space.md }}>
              {messages.map((message, index) => (
                <ChatBubble key={`${message.role}-${index}`} message={message} />
              ))}
              {sending && <ChatBubble message={{ role: 'assistant', content: 'Thinking...' }} muted />}
              <div ref={endRef} />
            </div>
          )}
        </section>

        <footer style={{ padding: t.space.md, borderTop: `1px solid ${t.color.border}`, backgroundColor: t.color.surface }}>
          <div className="flex items-center" style={{ maxWidth: 900, margin: '0 auto', gap: t.space.sm }}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Ask about allegations, dates, IPC sections, evidence, or missing facts"
              style={{
                flex: 1,
                minWidth: 0,
                border: `1px solid ${t.color.border}`,
                borderRadius: t.radius.sm,
                backgroundColor: t.color.raised,
                color: t.color.text,
                padding: `${t.space.sm} ${t.space.md}`,
                outline: 0,
                fontSize: t.size.ui,
              }}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || sending}
              className="inline-flex items-center cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                gap: t.space.sm,
                border: 'none',
                borderRadius: t.radius.sm,
                backgroundColor: t.color.accent,
                color: '#0a0a0a',
                padding: `${t.space.sm} ${t.space.md}`,
                fontWeight: t.weight.semibold,
              }}
            >
              {sending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
              Send
            </button>
          </div>
        </footer>
      </main>
    </div>
  );
}

function State({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center" style={{ justifyContent: 'center', gap: t.space.sm, color: t.color.muted, minHeight: 240 }}>
      {icon}
      <span>{text}</span>
    </div>
  );
}

function ChatBubble({ message, muted = false }: { message: DocumentChatMessage; muted?: boolean }) {
  const isUser = message.role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <div
        style={{
          maxWidth: '78%',
          border: `1px solid ${isUser ? t.color.accent : t.color.border}`,
          borderRadius: t.radius.md,
          backgroundColor: isUser ? 'rgba(212, 160, 23, 0.14)' : t.color.raised,
          color: muted ? t.color.dim : t.color.text,
          padding: t.space.md,
          lineHeight: 1.6,
          fontSize: t.size.ui,
        }}
      >
        <Markdown>{message.content}</Markdown>
      </div>
    </div>
  );
}
