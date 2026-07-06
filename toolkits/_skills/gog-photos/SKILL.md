---
name: gog-photos
description: "Select/download the user's Google Photos to disk via gog Picker API (--client personal). Use for any 'my photos' / 'photos from my phone' request."
---

# Google Photos (gog Picker)

Get user-selected Google Photos onto disk: the user picks visually, gog downloads just those.

## Always use `--client personal`

gog's default/bundled client CANNOT use the Picker API - it's disabled on gog's shared GCP project (226446030355). A dedicated project + Desktop OAuth client is registered as gog client `personal` (creds: `~/Library/Application Support/gogcli/credentials-personal.json`). Every photo command needs `--client personal`.

If auth fails (`insufficient scopes` / token expired), re-auth:
```
gog auth add k.zarzycki@gmail.com --client personal --services photospicker
```

## Flow

1. Create: `gog photos picker create --client personal --json` -> `session.id` + `session.pickerUri`
2. Hand the user `pickerUri` to open and select photos (optionally open it for them in Brave).
3. Check: `gog photos picker get <id> --client personal --json` -> `mediaItemsSet: true` when done. (Or block: `picker wait <id> --client personal`.)
4. List: `gog photos picker list <id> --client personal --json` -> items with `id`, `mediaFile.filename`, `mimeType`.
5. Download each: `gog photos picker download <id> <mediaItemId> --client personal --out <path>`

## Notes

- Sessions expire (~7 days; see `expireTime`).
- gog defaults to the `personal` client once this is set up - pass `--client default` for Gmail/Tasks commands.
- Deep reference: `~/dev/kb/personal/wiki/tools/gog-vs-gws.md`.
