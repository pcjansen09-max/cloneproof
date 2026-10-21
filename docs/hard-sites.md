# Why copies of modern sites break, and what cloneproof does about it

Saving a web page used to mean saving HTML. Today most sites are programs that build their own URLs, check their own
files and sometimes refuse to talk to a browser they do not like. Scores marked * come from a second tool built on the same copy engine (a team OS), measured with cloneproof; the rest are
from cloneproof itself. Everything below is a real failure we hit on a real site
while stress-testing `cloneproof capture`, with the fix. Each fix has a test that failed before it.

| what went wrong | seen on | what cloneproof does |
|---|---|---|
| The site answers a headless browser with **HTTP 403** and a challenge page. Playwright announces itself as `HeadlessChrome`. The tool saves the challenge page and "succeeds" with two files. | hark.com | Presents itself as an ordinary Chrome (same version, no "Headless"). If the main page still answers 4xx/5xx, or is a short "Just a moment" page, it stops with a clear message instead of saving nothing. `--user-agent`, `--chrome` and `--headed` for harder cases. This does not solve a CAPTCHA or log in for you. |
| **Relative URLs with a query string** (`news.css?v=3`) are never rewritten, so the mirror has no styles. | Hacker News (score 41) | Every reference is resolved against the file it appears in before it is matched. |
| `&amp;` inside a `href` does not match the URL that was saved. | Wikipedia (score 19) | HTML entities are decoded before matching. |
| No `charset`: `–` shows as `â€“`. | Hacker News | `<meta charset="utf-8">` is added when the page has none. |
| **Redirect to another host** (`example.nl` to `www.example.nl`): everything is saved under the wrong root. | delta-design.nl | The host you end up on becomes the site root. |
| **Next.js streams its data** as length-prefixed rows in inline scripts. Changing a URL inside changes the length and React dies with `Connection closed`. | delta-design.nl | Those script blocks are left byte for byte as the server sent them. |
| Path-like strings **inside JavaScript** (`"/."`, `"../"`) resolve to the start page and get replaced, which breaks the script. | figma.com | Inside code, only references to real files are rewritten, never anything that resolves to a folder or the page itself. |
| `//# sourceMappingURL=...` begins with `//#`, and Python's `urljoin` turns that into the file itself. The script gets its own path pasted into a comment. | github.com | Protocol-relative addresses need a host name; `//`, `//#` and the like are comments. |
| `integrity="sha384-..."`: a rewritten file no longer matches its hash and is blocked. | webflow.com (18.6 to 88.1*) | Integrity attributes are removed from mirrored HTML. |
| Import maps: `"react": "assets/react.js"` is a bare module name to the browser and is blocked. | github.com | Relative paths always start with `./` or `../`. |
| `new URL("https://...")` throws on a relative path, and many sites call it with a full address. | figma.com (6.9 to 73.8*) | In code, rewritten addresses stay absolute on a placeholder host. The built-in server swaps in the real host when it serves the file. |
| Webpack sets its **public path** (`"https://cdn.x.com/assets/"`) and appends file names later. The folder address is not in the list of saved files. | github.com | Folder addresses point to the local folder. |
| Files that are only requested at run time (lazy images, `srcset` candidates, posters, CSS backgrounds, 3D models). | Tailwind, Bruno Simon | A second pass wakes every lazy image and harvests what the DOM refers to; a "heal" pass opens the mirror, collects what 404s and fetches exactly that. |
| A response that **never ends** (a stream) holds the whole capture. | resend.com (a copier built on the same code hung for 15+ minutes) | Waits for in-flight responses are capped and the rest is cancelled. |
| A mirror that is **saved wrong and nobody notices**: an error page was stored during a bad moment. | Linear (10.8 once) | After saving, the mirror is opened and its visible text is compared with the live page, with one automatic retry. |
| A pinned or infinite page makes the scroll loop run forever. | vercel.com (a run hung; scroll loop suspected) | Scroll loops are capped, every step has a hard timeout. |
| A path from a URL escapes the mirror folder (`..%2Fx`). | review finding | Paths are normalised; nothing is ever written outside the folder. |

## Still hard

- **Content that appears only after a click, a login or a long scroll** is not there. The measurement tells you what is
  missing; the mirror does not fabricate it.
- **A/B variants and rotating content** (hark.com shows a different layout and video per visit) make a live comparison
  score low even when the copy is faithful. The noise mask covers small changes, not a different page.
- **GPU-heavy 3D** needs `--wait` and sometimes `--chrome`. Without a GPU, software rendering can take minutes.
- **Real bot walls** (an actual CAPTCHA) need a human once. Open the site in your own browser, then pass the cookie with
  `--header "Cookie: ..."`.

Only mirror sites you own or may copy. The content belongs to its authors.
