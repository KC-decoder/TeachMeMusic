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

This inventory records engineering due diligence and is not legal advice.
