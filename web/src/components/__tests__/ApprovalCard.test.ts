import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ApprovalCard from '../ApprovalCard.vue'

describe('ApprovalCard', () => {
  it('emits only the selected decision with the server interrupt id', async () => {
    const wrapper = mount(ApprovalCard, {
      props: {
        interrupt: {
          interruptId: 'interrupt-1',
          kind: 'decision',
          summary: '创建采购订单',
        },
      },
    })

    await wrapper.get('[data-testid="approve"]').trigger('click')

    expect(wrapper.emitted('decide')).toEqual([
      [{ interruptId: 'interrupt-1', decision: 'approve' }],
    ])
  })
})
