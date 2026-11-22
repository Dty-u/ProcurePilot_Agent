import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ThreadList from '../ThreadList.vue'

describe('ThreadList', () => {
  it('selects an existing thread and starts a new one', async () => {
    const wrapper = mount(ThreadList, {
      props: {
        threads: [
          { thread_id: 'thread-1', last_message_at: '2026-09-18T00:00:00Z', message_count: 2 },
        ],
      },
    })

    await wrapper.get('.thread-item').trigger('click')
    await wrapper.get('.new-chat').trigger('click')

    expect(wrapper.emitted('select')).toEqual([['thread-1']])
    expect(wrapper.emitted('create')).toHaveLength(1)
  })
})
