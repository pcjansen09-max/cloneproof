---
name: listings-cloneproof
description: Waar cloneproof (MCP/Playwright/skill-tool) vermeld kan worden via GitHub-PR of -issue; regels, cijfers en uitsluitingen per lijst, gemeten 2026-10-20
metadata:
  type: reference
---

Gemeten 2026-10-20 (gh api). cloneproof toen: 0 sterren, aangemaakt 2026-10-19, niet op PyPI.

Kansrijk:
- chatmcp/mcpso (mcp.so): issue "Submit MCP Server: naam (pakket)", wordt binnen 1-3 dagen door idoubi gelist en gesloten. Geen leeftijdseis.
- TheJambo/awesome-testing: PR, sectie Visual Testing, `- [Naam](url) - Beschrijving.` (punt verplicht). 60/100 laatste gesloten PR's gemerged.
- Jenqyang/Awesome-AI-Agents: PR, regel eindigt op shields stars-badge, achteraan de sectie toevoegen; anti-reclame. 49/100 gemerged.
- punkpeye/awesome-mcp-servers: PR, alfabetisch, MAAR bot eist Glama-listing + score-badge (Glama-login, Dockerfile in Glama). Eigenaar = Glama (gekleurd). 33/100 gemerged. Agent-PR's: 🤖🤖🤖 achter titel.
- mxschmitt/awesome-playwright: PR, Utils alfabetisch; ~1 op 5 gemerged.
- mojoaxel/awesome-regression-testing: PR a-z, punt verplicht; 1 merge in 3 mnd, wachtrij loopt op.

Uitgesloten: hesreallyhim/awesome-claude-code (>=14 dagen oud of 100 sterren, alleen web-issueformulier door mens, geen PR/gh), lorien/awesome-web-scraping (repo <1 maand en AI/MCP verboden), VoltAgent/awesome-agent-skills (geen nieuwe skills), ComposioHQ + BehiSecc awesome-claude-skills (0 merges van vreemden), travisvn (stil sinds 04-2026), wong2 (geen PR's, alleen website), appcypher (archived), modelcontextprotocol/servers (geen communitylijst meer, verwijst naar registry), jamesmurdza/awesome-ai-devtools (0 merges).
Officiele MCP Registry: kan met alleen GitHub via .mcpb op GitHub Release of ghcr.io OCI; PyPI vereist mcp-name in README.

Tip: search-API van GitHub geeft snel secondary rate limit; tel merges via `repos/X/pulls?state=closed&per_page=100`.
