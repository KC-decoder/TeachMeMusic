# Vendored MusicXML Standards Resources

The versioned directories beside this notice contain unmodified `schema/`
trees exported from the official W3C Music Notation Community Group repository:

<https://github.com/w3c-cg/musicxml>

`source-revisions.json` records the exact release tag or draft commit for each
directory. `manifest.json` records the SHA-256 digest of every vendored file.
Runtime code must use these local resources and must not fetch schemas from the
network.

## Licence review

| Version | Governing notice retained with the resources |
|---|---|
| 1.0, 1.1 | MusicXML Document Type Definition Public License 1.02 in each `schema/license.html` |
| 2.0 | MusicXML Document Type Definition Public License 2.0 in `2.0/schema/license.html` |
| 3.0 | MusicXML Public License 3.0 in `3.0/schema/license.html` |
| 3.1 | W3C Community Final Specification Agreement notice embedded in the schema files |
| 4.0 | W3C Community Final Specification Agreement notice embedded in the schema files |
| 4.1 draft | W3C Community Contributor License Agreement notice embedded in the schema files |

The older MusicXML public licences grant permission to use, copy, modify, and
distribute subject to retaining their required notices. TeachMeMusic retains
the complete upstream licence files and does not modify the vendored resources.
The 3.1 and 4.0 final resources retain their W3C Final Specification Agreement
notices; the moving 4.1 work is pinned to one exact contributor-licensed
snapshot and clearly labelled draft.

The vendored `xml.xsd` and `xlink.xsd` files retain their own embedded W3C
copyright and licence notices. No licence from these resources is asserted to
cover TeachMeMusic source code. The TeachMeMusic project licence remains a
separate unresolved project decision.

This record is an engineering provenance and notice review, not legal advice.
