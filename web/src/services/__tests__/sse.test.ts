import { describe, expect, it } from 'vitest'

import { parseSSE } from '../sse'

describe('parseSSE', () => {
  it('combines split chunks and parses token and done envelopes', async () => {
    const chunks = [
      'id: one\nevent: token\ndata: {"event":"token","payload":{"text":"采购',
      '建议"}}\n\nid: two\nevent: done\ndata: {"event":"done","payload":{"interrupted":false}}\n\n',
    ]

    const events = await collect(parseSSE(chunks))

    expect(events).toEqual([
      { event: 'token', payload: { text: '采购建议' } },
      { event: 'done', payload: { interrupted: false } },
    ])
  })
})

async function collect<T>(items: AsyncIterable<T>): Promise<T[]> {
  const result: T[] = []
  for await (const item of items) {
    result.push(item)
  }
  return result
}
