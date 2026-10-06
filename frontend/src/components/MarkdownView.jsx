import ReactMarkdown from "react-markdown";

const components = {
  h1: ({ children }) => <h2 className="mb-2 mt-6 text-lg font-semibold text-gray-900 first:mt-0">{children}</h2>,
  h2: ({ children }) => <h3 className="mb-2 mt-5 text-base font-semibold text-gray-900 first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1 mt-4 text-sm font-semibold text-gray-900">{children}</h4>,
  p: ({ children }) => <p className="mb-3 text-sm leading-relaxed text-gray-700">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-gray-700">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 text-sm text-gray-700">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
};

export default function MarkdownView({ content }) {
  return <ReactMarkdown components={components}>{content}</ReactMarkdown>;
}