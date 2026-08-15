# Extension icons

Custom icons are optional. `manifest.json` intentionally omits `icons` and
`action.default_icon`, so Chrome can load the unpacked extension using its
default placeholder without any files in this directory.

If branded assets are added later, provide 16, 32, 48, and 128 pixel PNG files
and update the manifest in the same reviewed change. Do not declare paths before
the corresponding files exist.
