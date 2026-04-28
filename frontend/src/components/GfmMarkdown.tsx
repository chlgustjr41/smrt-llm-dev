/**
 * GfmMarkdown — react-markdown wrapper with inline table rendering.
 *
 * react-markdown alone doesn't parse GFM table syntax without remark-gfm.
 * This component splits the content into prose and table segments, renders
 * prose with <Markdown> and table segments as real <table> elements.
 */
import React from 'react'
import Markdown from 'react-markdown'

// ── Table parser ──────────────────────────────────────────────────────────

type Segment = { type: 'prose'; content: string } | { type: 'table'; content: string }

/** Split raw markdown into alternating prose / table segments. */
function splitTableSegments(md: string): Segment[] {
  const lines = md.split('\n')
  const segments: Segment[] = []
  let proseBuf: string[] = []

  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const next = lines[i + 1] ?? ''
    // Table start: pipe row followed by alignment separator row
    if (/^\|.+\|/.test(line) && /^\|[-| :]+\|/.test(next)) {
      if (proseBuf.length > 0) {
        segments.push({ type: 'prose', content: proseBuf.join('\n') })
        proseBuf = []
      }
      const tableLines: string[] = []
      while (i < lines.length && /^\|/.test(lines[i])) {
        tableLines.push(lines[i])
        i++
      }
      segments.push({ type: 'table', content: tableLines.join('\n') })
    } else {
      proseBuf.push(line)
      i++
    }
  }
  if (proseBuf.length > 0) {
    segments.push({ type: 'prose', content: proseBuf.join('\n') })
  }
  return segments
}

function parseCells(line: string): string[] {
  return line.split('|').slice(1, -1).map((c) => c.trim())
}

function TableBlock({
  content,
  thCls,
  tdCls,
}: {
  content: string
  thCls: string
  tdCls: string
}) {
  const lines = content.split('\n').filter(Boolean)
  if (lines.length < 2) return null
  const headers = parseCells(lines[0])
  const rows = lines.slice(2).map(parseCells) // line 1 is the separator
  return (
    <div className="overflow-x-auto my-2">
      <table className="border-collapse w-full text-[11px]">
        <thead>
          <tr>
            {headers.map((h, i) => (
              <th key={i} className={thCls}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 1 ? 'bg-gray-50/50' : ''}>
              {row.map((cell, ci) => (
                <td key={ci} className={tdCls}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Public component ──────────────────────────────────────────────────────

/**
 * Drop-in replacement for <Markdown> that also renders GFM tables.
 *
 * @param proseClassName  Applied to the wrapping div around each prose segment.
 * @param thClassName     Tailwind classes for <th> cells.
 * @param tdClassName     Tailwind classes for <td> cells.
 */
export function GfmMarkdown({
  children,
  proseClassName = '',
  thClassName = 'border border-gray-300 bg-gray-50 px-2 py-1 text-left font-semibold',
  tdClassName = 'border border-gray-200 px-2 py-1',
}: {
  children: string
  proseClassName?: string
  thClassName?: string
  tdClassName?: string
}) {
  const segments = splitTableSegments(children)
  return (
    <>
      {segments.map((seg, idx) =>
        seg.type === 'table' ? (
          <TableBlock key={idx} content={seg.content} thCls={thClassName} tdCls={tdClassName} />
        ) : seg.content.trim() ? (
          <div key={idx} className={proseClassName}>
            <Markdown>{seg.content}</Markdown>
          </div>
        ) : null,
      )}
    </>
  )
}
