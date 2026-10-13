import { describe, expect, it } from 'vitest'

import { isSiteNavigationItemActive, siteNavigationItems } from './SiteSidebar'

describe('site navigation', () => {
  it('资料百科指向合并后的装备入口', () => {
    expect(
      siteNavigationItems.find((item) => item.label === '资料百科'),
    ).toMatchObject({
      href: '/wiki/equipment',
      activePrefix: '/wiki',
    })
  })

  it('所有百科路径高亮资料百科且不误判攻略路径', () => {
    const wikiItem = siteNavigationItems.find(
      (item) => item.label === '资料百科',
    )

    expect(wikiItem).toBeDefined()

    if (wikiItem === undefined) {
      return
    }

    expect(
      [
        '/v/mm2r-099/wiki/equipment',
        '/v/mm2r-099/wiki/vehicles',
        '/v/mm2r-099/wiki/main-cannons/universe-cannon',
      ].every((pathname) =>
        isSiteNavigationItemActive(pathname, 'mm2r-099', wikiItem),
      ),
    ).toBe(true)
    expect(
      isSiteNavigationItemActive('/v/mm2r-099/guides', 'mm2r-099', wikiItem),
    ).toBe(false)
  })
})
