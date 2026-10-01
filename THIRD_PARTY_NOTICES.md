# Third-Party Dependency Notices

TeachMeMusic itself is licensed under the MIT License; see [`LICENSE`](LICENSE).
The following packages are resolved by the DEV-004 Task 7J-R6 development
locks. They are not copied into this source repository. Anyone distributing a
bundle that includes them must retain the applicable upstream licence and
notice files.

| Package | Locked version | Licence reported by upstream distribution |
|---|---:|---|
| ast-serialize | 0.11.2 | MIT |
| iniconfig | 2.3.0 | MIT |
| librt | 0.15.0 | MIT |
| lxml | 6.1.3 | BSD-3-Clause; see its bundled `LICENSES.txt` for included components |
| lxml-stubs | 0.5.1 | Apache-2.0 |
| mypy | 2.3.1 | MIT; its distribution also retains typeshed notices |
| mypy-extensions | 1.1.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pathspec | 1.1.1 | MPL-2.0 |
| pluggy | 1.6.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.1.1 | MIT |
| Ruff | 0.16.9 | MIT |
| SaxonC-HE (`saxonche`) | 12.9.0 | MPL-2.0; see Saxonica's licence terms and third-party notices |
| setuptools | 84.0.0 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |

The authoritative licence text is the one shipped with or published for the
exact upstream artifact. In particular, the `saxonche` wheel does not declare
its licence in Python package metadata; Saxonica identifies SaxonC-HE as the
open-source Home Edition under MPL-2.0:
<https://www.saxonica.com/html/license/terms.html>.

## DEV-005 Browser Proof Lock

The `web/package-lock.json` artifact hash-locks the packages used by the
Task 5B.1 headless notation proof. `npm ci --omit=optional` installs the
following runtime dependency graph; optional native packages are not required
or installed for the proof.

| Package | Locked version | Licence reported by upstream distribution |
|---|---:|---|
| opensheetmusicdisplay | 2.1.3 | BSD-3-Clause |
| @types/vexflow | 1.2.42 | MIT |
| jszip | 3.10.1 | MIT OR GPL-3.0-or-later; TeachMeMusic uses it under MIT |
| lie | 3.3.0 | MIT |
| immediate | 3.0.6 | MIT |
| pako | 1.0.11 | MIT AND Zlib |
| readable-stream | 2.3.8 | MIT |
| core-util-is | 1.0.3 | MIT |
| inherits | 2.0.4 | ISC |
| isarray | 1.0.0 | MIT |
| process-nextick-args | 2.0.1 | MIT |
| safe-buffer | 5.1.2 | MIT |
| string_decoder | 1.1.1 | MIT |
| util-deprecate | 1.0.2 | MIT |
| setimmediate | 1.0.5 | MIT |
| loglevel | 1.9.2 | MIT |
| typescript-collections | 1.3.3 | MIT |
| vexflow | 1.2.93 | MIT |
| playwright | 1.60.0 | Apache-2.0 |
| playwright-core | 1.60.0 | Apache-2.0 |

This inventory records engineering due diligence and is not legal advice.

## DEV-005 Task 5C Application Locks

ADR-0006 authorizes the following exact direct selections for the local
application shell. Four PEP 751 artifacts lock the 32-package Python graph for
CPython 3.12/3.13 on macOS ARM64 and Linux x86-64. `web/package-lock.json`
locks the 183-package npm graph, including platform-optional build packages.

| Direct package | Selected version | Licence reported by upstream distribution |
|---|---:|---|
| fastapi | 0.141.1 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx (development) | 0.28.1 | BSD-3-Clause |
| react | 19.3.0 | MIT |
| react-dom | 19.3.0 | MIT |
| @vitejs/plugin-react | 6.1.1 | MIT |
| typescript | 6.0.3 | Apache-2.0 |
| vite | 8.3.1 | MIT |
| vitest | 5.0.2 | MIT |
| jsdom | 30.1.1 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| @testing-library/jest-dom | 7.0.1 | MIT |

New Python transitive packages are locked as follows:

| Transitive package | Locked version | Licence reported by upstream distribution |
|---|---:|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| click | 8.5.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |

Every npm lock entry reports an upstream licence. The graph includes MIT,
MIT-0, ISC, BSD-2-Clause, BSD-3-Clause, Apache-2.0, MPL-2.0, BlueOak-1.0.0,
CC0-1.0, Zlib, and declared dual/multiple-licence packages. The locked JSZip
release is used under MIT. The lock retains the precise package-level licence
fields and integrity hashes; a bundled distribution must retain all applicable
licence and notice files.

On 2026-09-26, clean installs of every Python lock passed `pip check` and the
complete repository suite in their named runtimes. `pip-audit==2.10.1`
reported no known vulnerabilities across the four Python locks. A clean
`npm ci`, `npm audit --omit=optional`, Vitest run, and production build also
passed with no known npm vulnerabilities. This inventory records engineering
due diligence and is not legal advice.

## DEV-005 Task 5E Audio Runtime and Piano Samples

Task 5E adds the exact `tone==15.1.22` browser runtime under ADR-0006. The npm
lock now contains 210 package entries excluding the root and additionally
locks Tone's runtime graph:

| Package | Locked version | Licence reported by upstream distribution |
|---|---:|---|
| tone | 15.1.22 | MIT |
| standardized-audio-context | 25.3.77 | MIT |
| automation-events | 7.1.19 | MIT |
| tslib | 2.8.1 | 0BSD |

The application includes 30 MP3 files from **Salamander Grand Piano V3** by
Alexander Holm, licensed under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The files are the
compact sample set distributed by the official Tone.js sampler example. Their
individual SHA-256 digests, attribution, and upstream location are recorded in
[`web/public/audio/salamander/manifest.json`](web/public/audio/salamander/manifest.json)
and the adjacent README. `TEST-APP-AUDIO-001` verifies the complete local file
set and every digest. The application does not fetch samples from a CDN at
runtime.

On 2026-09-26, `npm audit --omit=optional` reported zero known vulnerabilities
after the audio dependency was added. This inventory records engineering due
diligence and is not legal advice.
