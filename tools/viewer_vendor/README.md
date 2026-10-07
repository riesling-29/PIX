# PIX offline layout dependency

The viewer ships the unmodified browser bundle from `elkjs` **0.12.0**. It loads
locally, so opening a generated viewer does not fetch code from a CDN. Python
installation does not require Node or npm. ELK computes geometry; PIX's viewer
owns domain semantics and rendering.

To reproduce the checked-in files with Node and npm:

```powershell
cd tools/viewer_vendor
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd run vendor
npm.cmd run check
```

On non-Windows systems use `npm`. Installation is pinned by `package-lock.json`
and the registry integrity hash. `vendor.cjs` additionally checks fixed SHA256
digests of both the bundle and the license before copying anything. It is not
an automatic update mechanism: updating the dependency requires reviewing and
changing the version, lockfile, hashes, provenance, and rerunning layout tests.

The package's license expression is `EPL-2.0 OR GPL-3.0-or-later`; PIX distributes
the unmodified bundle under EPL-2.0 and includes its full license. Release source
and artifact hashes are recorded in `assets/vendor/provenance.json`.

Run the actual ELK regression tests from the PIX root:

```powershell
node --test tests/viewer/test_layout.cjs
```
